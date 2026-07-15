from config import ATC_MAP

_ATC_MAP_LOWER = {k.lower(): v for k, v in ATC_MAP.items()}


def normalize_antibiotic(name: str) -> tuple[str, str | None]:
    if not name:
        return "", None

    name_lower = name.lower().strip()
    if name_lower in _ATC_MAP_LOWER:
        normalized, atc = _ATC_MAP_LOWER[name_lower]
        return normalized, atc

    return name, None
