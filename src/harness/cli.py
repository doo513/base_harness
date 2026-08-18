import argparse
from pathlib import Path

from harness import __version__
from harness.config import ConfigError, HarnessConfig, load_harness_config
from harness.core.controller import DirectController, LLMController
from harness.core.runtime import HarnessRuntime
from harness.core.budget import Budget
from harness.core.security import SecurityConfig
from harness.core.sandbox import LocalProcessBackend, LinuxNamespaceSandboxBackend, NetworkPolicy
from harness.core.workspace import WorkspaceContract
from harness.adapters.model import CommandModelAdapter
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
    parser.add_argument("--model-command",
                        help="Local model command: JSON {system,user} on stdin -> Decision JSON on stdout.")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--resume", action="store_true",
                        help="Resume the persisted run in --run-dir instead of creating a new run.")
    parser.add_argument("--task-revision",
                        help="Stable task/input revision recorded in the run manifest.")
    parser.add_argument("--model-revision",
                        help="Stable model/provider revision recorded in the run manifest.")
    parser.add_argument("--require-complete-provenance", action="store_true",
                        help="Fail closed when required reproducibility provenance is missing.")
    parser.add_argument("--sealed-oracle-root",
                        help="Operator-owned acceptance assets outside the actor workspace (software/hackathon).")
    parser.add_argument(
        "--execution-backend",
        choices=["local", "linux-namespace"],
        default="local",
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
    parser.add_argument("--require-oracle-isolation", action="store_true",
                        help="Require the sealed oracle backend to report strong filesystem isolation.")
    args = parser.parse_args()

    try:
        workspace_contract = WorkspaceContract.build(
            args.workspace,
            temp_dir=config.workspace.temp_dir,
            build_dir=config.workspace.build_dir,
            cache_dir=config.workspace.cache_dir,
        )
    except ValueError as exc:
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
            else None
        )
    else:
        execution_backend = LocalProcessBackend(inherit_env=False)
        oracle_backend = execution_backend

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
            acceptance_commands=args.accept_command,
            execution_backend=execution_backend,
            oracle_backend=oracle_backend,
            sealed_oracle_root=args.sealed_oracle_root,
            require_oracle_isolation=args.require_oracle_isolation,
        )
    else:
        profile = SoftwareProfile(
            workspace=args.workspace,
            acceptance_commands=args.accept_command,
            execution_backend=execution_backend,
            oracle_backend=oracle_backend,
            sealed_oracle_root=args.sealed_oracle_root,
            require_oracle_isolation=args.require_oracle_isolation,
        )

    goal = profile.default_goal()
    if args.goal:
        from harness.core.contracts import GoalContract
        goal = GoalContract(
            goal=args.goal,
            acceptance=goal.acceptance,
            constraints=goal.constraints,
            pinned_constraints=goal.pinned_constraints,
        )

    controller = (
        LLMController(CommandModelAdapter(args.model_command))
        if args.model_command
        else DirectController()
    )
    runtime_factory = HarnessRuntime.resume if args.resume else HarnessRuntime
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
        task_revision=args.task_revision,
        model_revision=args.model_revision,
        require_complete_provenance=args.require_complete_provenance,
    )
    state = runtime.run()
    print(f"completed={state.completed} steps={state.step}")
    print(f"run_dir={Path(args.run_dir).resolve()}")


if __name__ == "__main__":
    main()
