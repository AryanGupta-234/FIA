from urllib.parse import urlsplit

# Seeded official retailer domains. This list does not verify marketplace sellers.
KNOWN_RETAILERS = {
    "myntra.com": "Myntra",
    "ajio.com": "AJIO",
    "amazon.in": "Amazon India",
    "flipkart.com": "Flipkart",
    "tatacliq.com": "Tata CLiQ",
    "nykaafashion.com": "Nykaa Fashion",
    "meesho.com": "Meesho",
    "decathlon.in": "Decathlon India",
    "hm.com": "H&M",
    "zara.com": "Zara",
    "bewakoof.com": "Bewakoof",
    "libas.in": "Libas",
    "westside.com": "Westside",
    "manyavar.com": "Manyavar",
}


def retailer_name(host: str) -> str | None:
    host = host.lower().split(":")[0].removeprefix("www.")
    for domain, name in KNOWN_RETAILERS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def assess_url(url: str) -> dict:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    known = retailer_name(host)
    https = parsed.scheme.lower() == "https"
    score = 0.15
    reasons = ["Seller identity has not been independently verified"]
    if https:
        score += 0.20
        reasons = ["HTTPS connection is used"]
    if known:
        score += 0.35
        reasons.append(f"Domain matches known retailer: {known}")
    if not host:
        score = 0.0
    score = round(min(score, 0.70), 2)
    label = (
        "Established retailer domain"
        if known and https
        else "HTTPS domain; seller unverified"
        if https
        else "Unverified / insecure domain"
    )
    return {
        "score": score,
        "label": label,
        "reasons": reasons,
        "retailer_name": known,
        "https": https,
        "domain": host,
    }
