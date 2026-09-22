"""Link-safety checks applied to every researched item (critical for airdrops)."""
from urllib.parse import urlparse

SCAM_PHRASES = [
    "seed phrase", "recovery phrase", "private key", "secret phrase",
    "send eth to receive", "send sol to receive", "pay gas to claim", "pay a fee to claim",
    "double your", "validate your wallet", "sync your wallet",
]


def registrable_domain(url: str | None) -> str:
    if not url:
        return ""
    host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def check(info: dict) -> list[str]:
    """Return red flags. Empty list == nothing obviously wrong (NOT a guarantee)."""
    flags = list(info.get("red_flags") or [])
    official = registrable_domain(info.get("official_site"))
    link = info.get("action_link")
    if link:
        if not official:
            flags.append("No official site confirmed — don't click the action link")
        elif registrable_domain(link) != official:
            flags.append(f"Action link domain ({registrable_domain(link)}) ≠ official domain ({official}) — possible phishing")
    blob = " ".join(str(v) for v in info.values()).lower()
    for p in SCAM_PHRASES:
        if p in blob:
            flags.append(f"Mentions '{p}' — classic drainer pattern")
    if str(info.get("legitimacy", "")).lower() == "suspicious":
        flags.append("Research judged this suspicious")
    # de-duplicate, keep order
    seen, out = set(), []
    for f in flags:
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out
