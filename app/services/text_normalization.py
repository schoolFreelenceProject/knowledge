import re
import unicodedata


_HORIZONTAL_SPACE_PATTERN = re.compile(r"[^\S\r\n]+")
_EXCESS_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = (
        normalized.replace("\x0c", "\n")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    normalized = _HORIZONTAL_SPACE_PATTERN.sub(" ", normalized)
    normalized = "\n".join(line.strip() for line in normalized.split("\n"))
    normalized = _EXCESS_BLANK_LINES_PATTERN.sub("\n\n", normalized)
    return normalized.strip()


def normalize_query_text(text: str) -> str:
    return normalize_text(text).replace("\n", " ").strip()
