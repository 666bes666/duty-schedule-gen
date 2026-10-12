from __future__ import annotations

import re
import unicodedata

_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *[f"com{i}" for i in range(1, 10)],
    *[f"lpt{i}" for i in range(1, 10)],
}


def safe_filenames(names: list[str], suffix: str) -> list[str]:
    if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) is None:
        raise ValueError("Invalid filename suffix")
    result: list[str] = []
    used: set[str] = set()
    for name in names:
        normalized = unicodedata.normalize("NFC", name)
        stem = "".join(
            "_" if ord(char) < 32 or ord(char) == 127 or char in '<>:"/\\|?*' else char
            for char in normalized
        ).strip(" ._")
        stem = stem.encode("utf-8")[:180].decode("utf-8", errors="ignore") or "employee"
        if stem.split(".", 1)[0].casefold() in _RESERVED:
            stem = "employee_" + stem
        candidate = stem + suffix
        counter = 1
        while candidate.casefold() in used:
            counter += 1
            candidate = f"{stem}_{counter}{suffix}"
        used.add(candidate.casefold())
        result.append(candidate)
    return result
