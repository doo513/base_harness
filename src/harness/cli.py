import argparse
import os
from pathlib import Path

from harness import __version__
from harness.config import ConfigError, HarnessConfig, load_harness_config
from harness.final_result import persist_final_result
from harness.model_gateway import ModelGateway, ModelGatewayError
from harness.mcp_gateway import MCPError, MCPGateway
from harness.plugin_gateway import PluginError, PluginGateway
from harness.profile_composition import ProfileCompositionError, augment_profile_tools
from harness.project_memory import ProjectMemoryError, ProjectMemoryStore
from harness.task_contracts import EvidenceArtifactTaskProfile
from harness.core.controller import DirectController, LLMController
from harness.core.runtime import HarnessRuntime
from harness.core.budget import Budget
from harness.core.security import SecurityConfig
from harness.core.sandbox import LocalProcessBackend, LinuxNamespaceSandboxBackend, NetworkPolicy
from harness.core.storage import ResumeConflict
from harness.core.workspace import WorkspaceContract
from harness.core.workspace_tools import make_workspace_read_tools
from harness.profiles import CTFProfile, HackathonProfile, SoftwareProfile, DemoProfile


def _load_optional_config() -> HarnessConfig:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config")
    known, _ = bootstrap.parse_known_args()
    if not known.config:
        return HarnessConfig()
    try:
        return load_harness_config(known.config)
    except ConfigError as exc:
        bootstrap.error(str(exc))
        raise AssertionError("argparse.error must terminate")


def _configured_fallbacks(config: HarnessConfig) -> tuple[str, ...]:
    if config.default_model is None:
        return ()
    raw = config.models[config.default_model].options.get("fallback_models", [])
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item for item in raw):
        raise ConfigError("default model options.fallback_models must be a list of model aliases")
    return tuple(raw)


def main():
    config = _load_optional_config()
    security_defaults = dict(config.security)

    parser = argparse.ArgumentParser(description=f"Verified-State Harness v{__version__}")
    parser.add_argument("--config", help="TOML harness configuration file.")
    parser.add_argument("--profile", choices=["demo", "ctf", "hackathon", "software"], default=config.profile)
    parser.add_argument("--run-dir", default=config.run_dir)
    parser.add_argument("--workspace", default=config.workspace.root)
    parser.add_argument("--goal")
    parser.add_argument("--accept-command", action="append", default=[],
                        help="Fixed harness-side acceptance command (software/hackathon). Repeatable.")
    parser.add_argument(
        "--artifact-target",
        default=os.environ.get("HARNESS_TASK_ARTIFACT_TARGET"),
        help="Relative evidence-backed deliverable path. Normally supplied by the conversational task intake layer.",
    )
    parser.add_argument("--model-command",
                        help="Legacy local model command. Overrides configured default_model.")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--resume", action="store_true",
                        help="Resume the persisted run in --run-dir instead of creating a new run.")
    parser.add_argument("--task-revision",
                        help="Stable task/input revision recorded in the run manifest.")
    parser.add_argument("--model-revision",
                        help="Override stable model/provider revision recorded in the run manifest.")
    parser.add_argument("--require-complete-provenance", action="store_true",
                        help="Fail closed when required reproducibility provenance is missing.")
    parser.add_argument("--sealed-oracle-root",
                        help="Operator-owned acceptance assets outside the actor workspace (software/hackathon).")
    parser.add_argument(
        "--execution-backend",
        choices=["local", "linux-namespace"],
        default=str(security_defaults.get("execution_backend", "local")),
        help="Shell execution backend. linux-namespace provides the Stage-02 production sandbox on supported Linux hosts.",
    )
    parser.add_argument(
        "--strict-layout",
        action=argparse.BooleanOptionalAction,
        default=bool(security_defaults.get("strict_layout", False)),
        help="Require run/oracle paths to be outside the actor workspace.",
    )
    parser.add_argument(
        "--strict-tool-isolation",
        action=argparse.BooleanOptionalAction,
        default=bool(security_defaults.get("strict_tool_isolation", False)),
        help="Fail closed unless WRITE/EXTERNAL tools use a positively attested isolation backend.",
    )
    parser.add_argument(
        "--network-policy",
        choices=["allow", "deny"],
        default=str(security_defaults.get("network_policy", "allow")),
    )
    parser.add_argument(
        "--require-sealed-oracle",
        action=argparse.BooleanOptionalAction,
        default=bool(security_defaults.get("require_sealed_oracle", False)),
        help="Reject runtime construction unless the profile uses a sealed completion oracle.",
    )
    parser.add_argument(
        "--require-oracle-isolation",
        action=argparse.BooleanOptionalAction,
        default=bool(security_defaults.get("require_oracle_isolation", False)),
        help="Require every command-based completion oracle to report strong filesystem isolation.",
    )
    args = parser.parse_args()
    acceptance_commands = list(args.accept_command or config.acceptance_commands)

    try:
        workspace_contract = WorkspaceContract.build(
            args.workspace,
            temp_dir=config.workspace.temp_dir,
            build_dir=config.workspace.build_dir,
            cache_dir=config.workspace.cache_dir,
        )
    except ValueError as exc:
        parser.error(str(exc))

    memory_store = None
    memory_retrieval_gateway = None
    if config.memory.enabled:
        try:
            project_id = config.memory.project_id or ProjectMemoryStore.default_project_id(workspace_contract.root)
            memory_store = ProjectMemoryStore(
                config.memory.root,
                project_id=project_id,
                workspace_root=workspace_contract.root,
            )
            memory_retrieval_gateway = memory_store.snapshot_gateway()
        except (ProjectMemoryError, OSError, ValueError) as exc:
            parser.error(str(exc))

    network_policy = NetworkPolicy(args.network_policy)
    if args.execution_backend == "linux-namespace":
        execution_backend = LinuxNamespaceSandboxBackend(network_policy=network_policy)
        oracle_backend = (
            LinuxNamespaceSandboxBackend(
                network_policy=NetworkPolicy.DENY,
                workspace_writable=False,
                read_only_paths=[Path(args.sealed_oracle_root).resolve()],
            )
            if args.sealed_oracle_root
            else LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
        )
    else:
        execution_backend = LocalProcessBackend(inherit_env=False)
        oracle_backend = LocalProcessBackend(inherit_env=False)

    if args.profile == "demo":
        if args.sealed_oracle_root:
            parser.error("--sealed-oracle-root is not supported by demo profile")
        profile = DemoProfile()
    elif args.profile == "ctf":
        if args.sealed_oracle_root:
            parser.error("--sealed-oracle-root is not supported by CTF callable oracle profile")
        profile = CTFProfile(workspace=args.workspace, execution_backend=execution_backend)
    elif args.profile == "hackathon":
        profile = HackathonProfile(
            workspace=args.workspace,
            acceptance_commands=acceptance_commands,
            execution_backend=execution_backend,
            oracle_backend=oracle_backend,
            sealed_oracle_root=args.sealed_oracle_root,
            require_oracle_isolation=args.require_oracle_isolation,
        )
    else:
        profile = SoftwareProfile(
            workspace=args.workspace,
            acceptance_commands=acceptance_commands,
            execution_backend=execution_backend,
            oracle_backend=oracle_backend,
            sealed_oracle_root=args.sealed_oracle_root,
            require_oracle_isolation=args.require_oracle_isolation,
        )

    mcp_gateway = None
    plugin_gateway = None
    extra_tools = {}
    if args.profile != "demo":
        extra_tools.update(make_workspace_read_tools(workspace_contract))

    enabled_mcp = tuple(item for item in config.mcp_servers if item.enabled)
    enabled_plugins = tuple(item for item in config.plugins if item.enabled)
    if args.strict_tool_isolation and (enabled_mcp or enabled_plugins):
        parser.error(
            "mcp-gateway-v1/plugin-gateway-v1 do not provide host-process isolation; "
            "disable those extensions or --strict-tool-isolation"
        )
    try:
        if enabled_mcp:
            mcp_gateway = MCPGateway(enabled_mcp)
            extra_tools.update(mcp_gateway.discover_tools())
        if enabled_plugins:
            plugin_gateway = PluginGateway(enabled_plugins)
            plugin_tools = plugin_gateway.discover_tools()
            collisions = sorted(set(extra_tools) & set(plugin_tools))
            if collisions:
                raise ProfileCompositionError(
                    "MCP/plugin tool collision: " + ", ".join(collisions)
                )
            extra_tools.update(plugin_tools)
        if extra_tools:
            profile = augment_profile_tools(profile, extra_tools)
    except (ConfigError, MCPError, PluginError, ProfileCompositionError) as exc:
        if mcp_gateway is not None:
            mcp_gateway.close()
        parser.error(str(exc))

    if args.artifact_target:
        if args.profile == "demo":
            parser.error("--artifact-target requires a workspace-enabled profile")
        try:
            profile = EvidenceArtifactTaskProfile(profile, artifact_target=args.artifact_target)
        except ValueError as exc:
            parser.error(str(exc))

    goal = profile.default_goal()
    if args.goal:
        from harness.core.contracts import GoalContract
        goal = GoalContract(
            goal=args.goal,
            acceptance=goal.acceptance,
            constraints=goal.constraints,
            pinned_constraints=goal.pinned_constraints,
        )

    gateway = None
    try:
        if args.model_command:
            gateway = ModelGateway.single_command(args.model_command)
        elif config.default_model is not None:
            gateway = ModelGateway(
                models=config.models,
                default_model=config.default_model,
                fallback_models=_configured_fallbacks(config),
            )
    except (ConfigError, ModelGatewayError) as exc:
        if mcp_gateway is not None:
            mcp_gateway.close()
        parser.error(str(exc))

    controller = LLMController(gateway) if gateway is not None else DirectController()
    effective_model_revision = args.model_revision or (gateway.revision if gateway is not None else None)

    runtime_factory = HarnessRuntime.resume if args.resume else HarnessRuntime
    memory_publish_report = None
    try:
        runtime = runtime_factory(
            goal=goal,
            profile=profile,
            controller=controller,
            run_dir=Path(args.run_dir),
            workspace_contract=workspace_contract,
            budget=Budget(hard_max_steps=args.max_steps),
            security_config=SecurityConfig(
                strict_layout=args.strict_layout,
                strict_tool_isolation=args.strict_tool_isolation,
                network_policy=args.network_policy,
                require_sealed_oracle=args.require_sealed_oracle,
            ),
            retrieval_gateway=memory_retrieval_gateway,
            task_revision=args.task_revision,
            model_revision=effective_model_revision,
            require_complete_provenance=args.require_complete_provenance,
        )
        state = runtime.run()
        if memory_store is not None:
            memory_publish_report = memory_store.publish_from_state(
                state,
                source_run_id=runtime.run_id,
            )
    except ResumeConflict as exc:
        action = "use --resume with this run directory" if not args.resume else "check that --run-dir points to the intended persisted run"
        parser.error(f"{exc}; {action}, or choose a fresh --run-dir")
    finally:
        if mcp_gateway is not None:
            mcp_gateway.close()

    final_result_path = persist_final_result(
        args.run_dir,
        state=state,
        workspace=workspace_contract.root,
        artifact_target=args.artifact_target,
    )

    print(f"completed={state.completed} steps={state.step}")
    print(f"run_dir={Path(args.run_dir).resolve()}")
    print(f"final_result={final_result_path}")
    if memory_publish_report is not None:
        print(
            "memory="
            f"published:{len(memory_publish_report['published'])},"
            f"deduplicated:{len(memory_publish_report['deduplicated'])},"
            f"rejected:{len(memory_publish_report['rejected'])}"
        )


if __name__ == "__main__":
    main()
