from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from harness.core.retrieval import RetrievalPolicy

from stage8_probe_support import gateway, runtime, source


def main() -> int:
    policy = RetrievalPolicy(enabled=True)
    items = [
        source(
            f"s{i}",
            "needle " + (chr(65 + i) * 100_000),
            metadata={f"key{j}": "m" * 200 for j in range(8)},
        )
        for i in range(5)
    ]
    raw_source_bytes = sum(len(item.content.encode("utf-8")) for item in items)

    with tempfile.TemporaryDirectory(prefix="vsh-stage8-cost-") as tmp:
        root = Path(tmp)
        rt = runtime(
            root,
            "cost",
            retrieval_gateway=gateway(items),
            retrieval_policy=policy,
        )
        rt._handle_retrieval_request("needle")
        durable_bytes = sum(
            len(rt.artifacts.verified_read_bytes(rt.state.retrieval.items[item_id].content_ref))
            for item_id in rt.state.retrieval.current_item_ids
        )

        samples = []
        context = None
        for _ in range(20):
            started = time.perf_counter()
            context = rt._context()
            samples.append(time.perf_counter() - started)

        retrieval_visible = context["untrusted"]["retrieval"]
        retrieval_visible_json_chars = len(json.dumps(
            retrieval_visible,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ))
        full_context_chars = len(json.dumps(
            context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ))
        stats = context["projection"]["retrieval_stats"]

    passed = (
        durable_bytes <= policy.max_total_content_bytes_per_request
        and stats["visible_preview_chars"] <= policy.max_total_context_preview_chars
        and stats["visible_metadata_chars"] <= policy.max_total_context_metadata_chars
        and retrieval_visible_json_chars < raw_source_bytes
    )
    payload = {
        "stage": "08",
        "probe": "retrieval-cost-rc1",
        "measurement": "serialized_chars_and_verified-byte-read proxy; not token count",
        "source": {
            "candidate_count": len(items),
            "raw_source_bytes": raw_source_bytes,
        },
        "durable": {
            "admitted_item_count": len(items),
            "artifact_bytes": durable_bytes,
            "max_bytes_per_request": policy.max_total_content_bytes_per_request,
        },
        "model_visible": {
            "retrieval_json_chars": retrieval_visible_json_chars,
            "full_context_chars": full_context_chars,
            "preview_chars": stats["visible_preview_chars"],
            "metadata_chars": stats["visible_metadata_chars"],
        },
        "per_projection_integrity_cost": {
            "artifact_bytes_verified": durable_bytes,
            "logical_artifact_reads": len(items),
            "median_wall_seconds": statistics.median(samples),
            "rounds": len(samples),
        },
        "notes": [
            "Current retrieval artifacts are re-verified before each model-visible projection.",
            "The deterministic worst-case byte-read bound is capped by max_total_content_bytes_per_request for the current result snapshot.",
            "Wall time is environment-specific and is not a correctness gate.",
        ],
        "passed": passed,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
