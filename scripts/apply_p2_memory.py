from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import lzma

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "scripts" / "p2_memory_payload"
EXPECTED_SHA256 = "a4701d85b5ce6f2792814a4f70c06570dab3dbf0dcaf696070810f9de80a1cb4"


def main() -> None:
    encoded = "".join(
        path.read_text(encoding="ascii").strip()
        for path in sorted(PARTS.glob("part*.b64"))
    )
    # Contents API transports may omit terminal Base64 padding. Padding is not
    # payload data; the decoded applicator SHA-256 below remains authoritative.
    encoded += "=" * (-len(encoded) % 4)
    source = lzma.decompress(base64.b64decode(encoded)).decode("utf-8")
    actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(
            f"P2 memory applicator hash mismatch: expected={EXPECTED_SHA256}, actual={actual}"
        )
    namespace = {"__name__": "__main__", "__file__": str(Path(__file__).resolve())}
    exec(compile(source, "p2_memory_applicator.py", "exec"), namespace, namespace)


if __name__ == "__main__":
    main()
