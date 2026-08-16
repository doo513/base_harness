from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from harness.core.storage import ArtifactStore, IntegrityError


def run_probe() -> dict:
    outcomes: dict[str, dict[str, bool]] = {}
    with tempfile.TemporaryDirectory(prefix="vsh-stage8-artifact-") as td:
        root = Path(td)
        store = ArtifactStore(root / "artifacts")

        clean_ref = store.put_json("evidence.json", {"ok": True, "value": "ORIGINAL"})
        outcomes["clean_verified_read"] = {
            "passed": store.verified_read_json(clean_ref) == {"ok": True, "value": "ORIGINAL"}
        }

        clean_path = store.resolve(clean_ref)
        clean_path.write_text(json.dumps({"ok": True, "value": "TAMPERED"}), encoding="utf-8")
        try:
            store.verified_read_bytes(clean_ref)
        except IntegrityError:
            outcomes["tampered_bytes_blocked"] = {"passed": True}
        else:
            outcomes["tampered_bytes_blocked"] = {"passed": False}

        missing_ref = "artifact://" + ("b" * 64) + "_missing.json"
        try:
            store.verified_read_bytes(missing_ref)
        except IntegrityError:
            outcomes["missing_artifact_blocked"] = {"passed": True}
        else:
            outcomes["missing_artifact_blocked"] = {"passed": False}

        try:
            store.verified_read_bytes("artifact://not-addressed")
        except (ValueError, IntegrityError):
            outcomes["malformed_ref_blocked"] = {"passed": True}
        else:
            outcomes["malformed_ref_blocked"] = {"passed": False}

        try:
            store.verified_read_bytes("artifact://" + ("c" * 64) + "_../escape")
        except (ValueError, IntegrityError):
            outcomes["path_escape_blocked"] = {"passed": True}
        else:
            outcomes["path_escape_blocked"] = {"passed": False}

        race_store = ArtifactStore(root / "race-artifacts")
        original = (b"A" * (1024 * 1024)) + (b"B" * 64)
        race_ref = race_store.put_text("large.txt", original.decode("ascii"))
        race_path = race_store.resolve(race_ref)
        replacement = race_path.with_name("replacement.tmp")
        replacement.write_bytes(b"TAMPERED")

        real_read = os.read
        swapped = {"done": False}

        def racing_read(fd: int, size: int) -> bytes:
            chunk = real_read(fd, size)
            if chunk and not swapped["done"]:
                swapped["done"] = True
                os.replace(replacement, race_path)
            return chunk

        os.read = racing_read
        try:
            returned = race_store.verified_read_bytes(race_ref)
        finally:
            os.read = real_read

        same_buffer = swapped["done"] and returned == original
        later_tamper_blocked = False
        try:
            race_store.verified_read_bytes(race_ref)
        except IntegrityError:
            later_tamper_blocked = True
        outcomes["swap_after_first_read_blocked"] = {
            "passed": bool(same_buffer and later_tamper_blocked)
        }

    result = {
        "stage": "08-preflight",
        "probe": "single-buffer-artifact-integrity-v081rc2",
        "outcomes": outcomes,
    }
    result["summary"] = {
        "scenario_count": len(outcomes),
        "all_passed": all(v["passed"] for v in outcomes.values()),
        "unverified_return_buffers": 0 if outcomes["swap_after_first_read_blocked"]["passed"] else 1,
    }
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
