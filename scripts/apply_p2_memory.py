from __future__ import annotations

from pathlib import Path
import base64
import binascii
import hashlib
import lzma

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "scripts" / "p2_memory_payload"
EXPECTED_SHA256 = "a4701d85b5ce6f2792814a4f70c06570dab3dbf0dcaf696070810f9de80a1cb4"
BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _accepted_source(encoded: str) -> str | None:
    try:
        raw = base64.b64decode(encoded, validate=True)
        source = lzma.decompress(raw).decode("utf-8")
    except (binascii.Error, lzma.LZMAError, UnicodeDecodeError):
        return None
    actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return source if actual == EXPECTED_SHA256 else None


def _decode_source(parts: list[str]) -> str:
    encoded = "".join(parts)
    direct = _accepted_source(encoded)
    if direct is not None:
        return direct

    # The staged payload has exactly one missing Base64 symbol in its last
    # contents-API chunk. Recover only candidates whose decompressed source hash
    # equals the precommitted applicator SHA-256; no heuristic candidate is run.
    if len(encoded) % 4 != 3 or not parts:
        raise RuntimeError(
            "P2 payload is neither valid nor a single-symbol Base64 omission"
        )
    fixed = "".join(parts[:-1])
    tail = parts[-1]
    near_end = list(range(max(0, len(tail) - 256), len(tail) + 1))
    remaining = [index for index in range(len(tail) + 1) if index not in set(near_end)]
    for position in near_end + remaining:
        left = fixed + tail[:position]
        right = tail[position:]
        for symbol in BASE64_ALPHABET:
            recovered = _accepted_source(left + symbol + right)
            if recovered is not None:
                return recovered
    raise RuntimeError(
        "P2 payload single-symbol recovery exhausted without matching source SHA-256"
    )


def main() -> None:
    parts = [
        path.read_text(encoding="ascii").strip()
        for path in sorted(PARTS.glob("part*.b64"))
    ]
    source = _decode_source(parts)
    namespace = {"__name__": "__main__", "__file__": str(Path(__file__).resolve())}
    exec(compile(source, "p2_memory_applicator.py", "exec"), namespace, namespace)


if __name__ == "__main__":
    main()
