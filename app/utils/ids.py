import hashlib


def stable_id(prefix: str, *parts: str) -> str:
    raw = "::".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"
