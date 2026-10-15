import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {"gclid", "fbclid", "mc_cid", "mc_eid"}
PRICE_RE = re.compile(r"(?:₹|INR|Rs\.?\s*)\s*([\d,]+(?:\.\d{1,2})?)", re.I)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are accepted")
    host = parts.hostname.lower().removeprefix("www.")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), host, path.rstrip("/") or "/", urlencode(query), ""))


def extract_price(text: str) -> float | None:
    match = PRICE_RE.search(text.replace("\\u20b9", "₹"))
    return float(match.group(1).replace(",", "")) if match else None
