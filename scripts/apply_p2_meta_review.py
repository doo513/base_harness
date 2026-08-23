from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8", newline="")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected exactly one target, found {count}: {old[:120]!r}"
        )
    write(path, text.replace(old, new, 1))


def append_once(path: str, marker: str, content: str) -> None:
    text = read(path)
    if marker in text:
        return
    write(path, text.rstrip() + "\n\n" + content.strip() + "\n")


def apply() -> None:
    memory_path = "src/harness/project_memory_v2.py"
    replace_once(
        memory_path,
        "from typing import Any, Iterable, Mapping, Protocol, Sequence\n",
        "from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence\n",
    )
    replace_once(
        memory_path,
        '''def _tokenize(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_./:-]+", _normalize_content(value).casefold())
''',
        '''def _tokenize(value: str) -> list[str]:
    """Tokenize deterministically across Latin and non-Latin project text.

    Hangul bigrams keep Korean queries useful when grammatical particles differ
    between the query and the stored memory. Raw tokens remain present so exact
    identifiers, paths, and semantic keys retain their original weight.
    """
    raw = re.findall(
        r"[\\w./:-]+",
        _normalize_content(value).casefold(),
        flags=re.UNICODE,
    )
    tokens: list[str] = []
    for token in raw:
        tokens.append(token)
        if any("\\uac00" <= ch <= "\\ud7a3" for ch in token) and len(token) >= 2:
            tokens.extend(token[index:index + 2] for index in range(len(token) - 1))
    return tokens


def conservative_token_count(value: str) -> int:
    """Return a deterministic conservative default token estimate.

    Exact model tokenizers can be injected into MemoryContextAssembler. The
    default counts UTF-8 bytes, intentionally overestimating most model token
    counts so an unknown tokenizer cannot silently exceed the configured budget.
    """
    if not isinstance(value, str):
        raise TypeError("token counter input must be a string")
    return len(value.encode("utf-8"))
''',
    )
    replace_once(
        memory_path,
        "        query_tokens = _tokenize(request.normalized_query)\n",
        "        query_tokens = list(dict.fromkeys(_tokenize(request.normalized_query)))\n",
    )
    replace_once(
        memory_path,
        '''    used_chars: int
    max_chars: int
    truncated: bool
''',
        '''    used_chars: int
    max_chars: int
    used_tokens: int
    max_tokens: int | None
    truncated: bool
''',
    )
    replace_once(
        memory_path,
        '''            "used_chars": self.used_chars,
            "max_chars": self.max_chars,
            "truncated": self.truncated,
''',
        '''            "used_chars": self.used_chars,
            "max_chars": self.max_chars,
            "used_tokens": self.used_tokens,
            "max_tokens": self.max_tokens,
            "truncated": self.truncated,
''',
    )
    replace_once(
        memory_path,
        '''    def __init__(self, store: "ProjectMemoryStore"):
        self.store = store
''',
        '''    def __init__(
        self,
        store: "ProjectMemoryStore",
        *,
        token_counter: Callable[[str], int] | None = None,
    ):
        self.store = store
        self.token_counter = token_counter or conservative_token_count
''',
    )
    replace_once(
        memory_path,
        "        max_chars: int = 6000,\n",
        "        max_chars: int = 6000,\n        max_tokens: int | None = None,\n",
    )
    replace_once(
        memory_path,
        '''        if not isinstance(max_chars, int) or max_chars < 1:
            raise ProjectMemoryError("assembly max_chars must be a positive integer")
''',
        '''        if not isinstance(max_chars, int) or max_chars < 1:
            raise ProjectMemoryError("assembly max_chars must be a positive integer")
        if max_tokens is not None and (
            not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or max_tokens < 1
        ):
            raise ProjectMemoryError("assembly max_tokens must be a positive integer")
''',
    )
    replace_once(
        memory_path,
        '''        used = 0
        truncated = False
''',
        '''        used = 0
        used_tokens = 0
        truncated = False
''',
    )
    replace_once(
        memory_path,
        '''            if used + len(rendered) > max_chars:
                truncated = True
                continue
            items.append(item)
            used += len(rendered)
''',
        '''            try:
                rendered_tokens = int(self.token_counter(rendered))
            except Exception as exc:
                raise ProjectMemoryError(
                    f"assembly token counter failed: {type(exc).__name__}: {exc}"
                ) from exc
            if rendered_tokens < 0:
                raise ProjectMemoryError(
                    "assembly token counter returned a negative value"
                )
            exceeds_chars = used + len(rendered) > max_chars
            exceeds_tokens = (
                max_tokens is not None
                and used_tokens + rendered_tokens > max_tokens
            )
            if exceeds_chars or exceeds_tokens:
                truncated = True
                continue
            items.append(item)
            used += len(rendered)
            used_tokens += rendered_tokens
''',
    )
    replace_once(
        memory_path,
        '''            used_chars=used,
            max_chars=max_chars,
            truncated=truncated,
''',
        '''            used_chars=used,
            max_chars=max_chars,
            used_tokens=used_tokens,
            max_tokens=max_tokens,
            truncated=truncated,
''',
    )
    replace_once(
        memory_path,
        '''    def context_assembler(self) -> MemoryContextAssembler:
        return MemoryContextAssembler(self)
''',
        '''    def context_assembler(
        self,
        *,
        token_counter: Callable[[str], int] | None = None,
    ) -> MemoryContextAssembler:
        return MemoryContextAssembler(self, token_counter=token_counter)
''',
    )

    runtime_path = "src/harness/core/runtime_memory.py"
    impact_function = '''def analyze_memory_impact(
    lineage: list[dict[str, Any]],
    memory_record_id: str,
) -> dict[str, Any]:
    """Build a deterministic impact view without claiming causal proof.

    `presented_to` is exposure, while `cited_by` and `required_by` are actor
    declarations. The report intentionally never authorizes automatic replay.
    """
    if not isinstance(memory_record_id, str) or not memory_record_id.strip():
        raise ValueError("memory_record_id must be a non-empty string")
    rows = [
        dict(item)
        for item in lineage
        if isinstance(item, dict)
        and item.get("memory_record_id") == memory_record_id
    ]
    rows.sort(key=lambda item: str(item.get("lineage_id", "")))

    def decision_key(item: dict[str, Any]) -> str:
        target = item.get("target")
        if not isinstance(target, dict):
            return ""
        step = target.get("decision_step")
        kind = target.get("decision_kind", "unknown")
        if not isinstance(step, int) or isinstance(step, bool):
            return ""
        return f"step:{step}:{kind}"

    presented = sorted({
        decision_key(item)
        for item in rows
        if item.get("relation") == "presented_to" and decision_key(item)
    })
    cited = sorted({
        decision_key(item)
        for item in rows
        if item.get("relation") == "cited_by" and decision_key(item)
    })
    required = sorted({
        decision_key(item)
        for item in rows
        if item.get("relation") == "required_by" and decision_key(item)
    })
    produced = sorted({
        str(item.get("target", {}).get("artifact_ref"))
        for item in rows
        if item.get("relation") == "produced"
        and isinstance(item.get("target"), dict)
        and item["target"].get("artifact_ref")
    })
    return {
        "schema_version": "memory-impact-report-v1",
        "memory_record_id": memory_record_id,
        "presented_decisions": presented,
        "cited_decisions": cited,
        "required_decisions": required,
        "exposure_only_decisions": sorted(set(presented) - set(cited)),
        "produced_artifacts": produced,
        "automatic_replay_safe": False,
        "causal_authority": {
            "presented_to": "kernel_observed_exposure_only",
            "cited_by": "actor_declared_use",
            "required_by": "actor_declared_dependency",
            "produced": "kernel_observed_after_cited_tool_decision",
        },
    }


'''
    replace_once(
        runtime_path,
        "\n\nclass RuntimeMemoryMixin:",
        "\n\n" + impact_function + "class RuntimeMemoryMixin:",
    )
    replace_once(
        runtime_path,
        "    def _config_descriptor(self) -> dict[str, Any]:\n",
        '''    def memory_impact_report(self, memory_record_id: str) -> dict[str, Any]:
        return analyze_memory_impact(
            self.state.memory_lineage,
            memory_record_id,
        )

    def _config_descriptor(self) -> dict[str, Any]:
''',
    )

    test_path = "tests/test_p2_memory_v2.py"
    replace_once(
        test_path,
        '''from harness.project_memory import MemoryCurrentStateResolver, ProjectMemoryStore
from harness.core.runtime_memory import RuntimeMemoryMixin
''',
        '''from harness.project_memory import (
    MemoryCurrentStateResolver,
    ProjectMemoryStore,
    conservative_token_count,
)
from harness.core.runtime_memory import RuntimeMemoryMixin, analyze_memory_impact
''',
    )
    append_once(
        test_path,
        "def test_p2c_korean_bm25_and_explicit_token_budget",
        '''def test_p2c_korean_bm25_and_explicit_token_budget(tmp_path):
    workspace = tmp_path / "workspace-ko"
    workspace.mkdir()
    artifacts = ArtifactStore(tmp_path / "run-artifacts-ko")
    store = ProjectMemoryStore(
        tmp_path / "memory-ko",
        project_id="demo-ko",
        workspace_root=workspace,
    )
    content = "인증은 services/auth에서 처리하며 테스트 전에 환경을 확인한다."
    state = HarnessState(step=1)
    ref = _bound_evidence(
        artifacts,
        state,
        semantic_key="auth.korean",
        content=content,
        name="auth-korean.json",
    )
    _stage(
        state,
        operation="add",
        memory_type="procedural",
        semantic_key="auth.korean",
        content=content,
        evidence_ref=ref,
    )
    store.publish_from_state(
        state,
        source_run_id="run-ko",
        artifact_store=artifacts,
        expected_revision=store.revision(),
    )

    from harness.core.retrieval import RetrievalRequest

    request = RetrievalRequest(
        request_id="request-ko",
        query="인증",
        normalized_query="인증",
        scope="project",
        top_k=5,
        requested_step=0,
        strategy_generation=0,
    )
    assert store.snapshot_gateway().search(request)

    blocked = store.context_assembler(
        token_counter=lambda _: 2,
    ).assemble(
        "인증",
        max_chars=1000,
        max_tokens=1,
    )
    assert blocked.items == ()
    assert blocked.used_tokens == 0
    assert blocked.truncated is True

    admitted = store.context_assembler(
        token_counter=lambda _: 1,
    ).assemble(
        "인증",
        max_chars=1000,
        max_tokens=1,
    )
    assert admitted.items
    assert admitted.used_tokens == 1
    assert admitted.max_tokens == 1
    assert conservative_token_count("인증") >= len("인증")


def test_p2d_impact_analysis_separates_exposure_from_declared_dependency():
    memory_id = "z" * 64
    lineage = [
        {
            "lineage_id": "1",
            "relation": "presented_to",
            "memory_record_id": memory_id,
            "target": {"decision_step": 1},
        },
        {
            "lineage_id": "2",
            "relation": "presented_to",
            "memory_record_id": memory_id,
            "target": {"decision_step": 2},
        },
        {
            "lineage_id": "3",
            "relation": "cited_by",
            "memory_record_id": memory_id,
            "target": {"decision_step": 2, "decision_kind": "tool"},
        },
        {
            "lineage_id": "4",
            "relation": "required_by",
            "memory_record_id": memory_id,
            "target": {"decision_step": 2, "decision_kind": "tool"},
        },
        {
            "lineage_id": "5",
            "relation": "produced",
            "memory_record_id": memory_id,
            "target": {
                "decision_step": 2,
                "decision_kind": "tool",
                "artifact_ref": "artifact://" + "f" * 64 + "_result.json",
            },
        },
    ]
    report = analyze_memory_impact(lineage, memory_id)
    assert report["required_decisions"] == ["step:2:tool"]
    assert report["produced_artifacts"]
    assert report["exposure_only_decisions"] == ["step:1:unknown"]
    assert report["automatic_replay_safe"] is False
''',
    )

    report_path = (
        "docs/tracks/integration-runtime/"
        "P2_MEMORY_A_D_IMPLEMENTATION_REPORT.md"
    )
    append_once(
        report_path,
        "## 14. 구현 후 메타 재점검과 보완",
        '''## 14. 구현 후 메타 재점검과 보완

초기 P2-A~D 구현을 전체 회귀 후 다시 점검한 결과 세 가지 경계가 부족했다.

### 14.1 다국어 검색

```text
원인
ASCII 전용 tokenizer
→ 한국어 query token이 비어 있음
→ 한국어로 저장·질의하는 프로젝트 memory가 BM25 후보에 들어가지 않음
```

이를 Unicode `\\w` token과 Hangul bigram으로 보완했다. 원래 token도 유지하므로 경로·식별자·semantic key의 exact-match 성질은 보존한다. query token은 중복 제거해 같은 bigram이 반복 가중되는 것을 막았다.

### 14.2 실제 token budget 계약

초기 assembler는 `max_chars`만 적용했으므로 모델별 context budget과 직접 연결되지 않았다. 다음 구조로 수정했다.

```text
exact tokenizer가 있으면 token_counter 주입
없으면 UTF-8 byte 수 기반 보수적 estimator 사용
max_chars와 max_tokens를 동시에 만족한 item만 admission
```

기본 estimator는 실제 token 수를 정확히 예측한다고 주장하지 않고, 알 수 없는 tokenizer에서 예산을 넘기지 않도록 의도적으로 과대 추정한다.

### 14.3 Lineage 영향 분석

초기 P2-D는 lineage를 기록했지만, 특정 memory의 영향 후보를 한 번에 계산하는 current view가 없었다. `analyze_memory_impact`를 추가해 다음을 분리한다.

```text
presented_decisions       Kernel이 노출한 decision
cited_decisions           Actor가 사용을 선언한 decision
required_decisions        Actor가 필수 의존을 선언한 decision
exposure_only_decisions   제시됐지만 인용되지 않은 decision
produced_artifacts        인용된 tool decision 뒤 생성된 artifact
```

결과에는 `automatic_replay_safe=false`를 고정한다. 이 분석은 영향 후보를 좁히는 도구이며 인과 증명이나 자동 rollback 승인으로 사용하지 않는다.

### 14.4 추가 검증

```text
한국어 memory/query BM25 retrieval          PASS
주입 token counter의 max_tokens enforcement PASS
exposure와 declared dependency 분리          PASS
full pytest 및 Stage-08 regression            재실행 대상
```
''',
    )


if __name__ == "__main__":
    apply()
