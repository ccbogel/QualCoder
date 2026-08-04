from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes


def decode_text_with_best_encoding(import_file: str | Path) -> tuple[str, str]:
    """Decode text bytes using UTF-8 first, then charset-normalizer and fallbacks."""

    path = Path(import_file)
    with open(path, "rb") as sourcefile:
        raw_bytes = sourcefile.read()
    if not raw_bytes:
        return "", "empty"

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    best_match = from_bytes(raw_bytes).best()
    if best_match is not None:
        detected_encoding = best_match.encoding if best_match.encoding else "unknown"
        return str(best_match), detected_encoding

    for encoding in ("cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            pass

    return raw_bytes.decode("utf-8", errors="backslashreplace"), "utf-8(backslashreplace)"