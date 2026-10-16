import json
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from fia.services.normalize import extract_price


def walk_jsonld(node):
    if isinstance(node, list):
        for child in node:
            yield from walk_jsonld(child)
    elif isinstance(node, dict):
        kind = node.get("@type", [])
        kinds = [kind] if isinstance(kind, str) else kind
        if "Product" in kinds:
            yield node
        for child in node.values():
            if isinstance(child, (dict, list)):
                yield from walk_jsonld(child)


def _first_image(value, page_url: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    if not isinstance(value, str):
        return None
    resolved = urljoin(page_url, value)
    return resolved if urlsplit(resolved).scheme in {"http", "https"} else None


def _float(value) -> float | None:
    try:
        result = float(str(value).replace(",", ""))
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def _offer_fields(offers) -> dict:
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price_spec = offers.get("priceSpecification") or {}
    if isinstance(price_spec, list):
        price_spec = price_spec[0] if price_spec else {}
    if not isinstance(price_spec, dict):
        price_spec = {}
    price = _float(offers.get("price") or offers.get("lowPrice") or price_spec.get("price"))
    original = _float(
        offers.get("highPrice")
        if offers.get("@type") == "AggregateOffer" and offers.get("highPrice") and not price
        else price_spec.get("strikethroughPrice") or price_spec.get("referencePrice")
    )
    if original is not None and price is not None and original <= price:
        original = None
    discount = round((1 - price / original) * 100, 1) if price and original else None
    return {
        "price": price,
        "original_price": original,
        "discount_percent": discount,
        "currency": str(
            offers.get("priceCurrency") or price_spec.get("priceCurrency") or "INR"
        )[:3].upper(),
        "availability": offers.get("availability"),
        "seller_name": (offers.get("seller") or {}).get("name")
        if isinstance(offers.get("seller"), dict)
        else offers.get("seller"),
        "offer_valid_until": offers.get("priceValidUntil"),
    }


def extract_product(html: str, page_url: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    candidates = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            candidates.extend(walk_jsonld(json.loads(script.string or script.get_text())))
        except (json.JSONDecodeError, TypeError):
            continue
    if candidates:
        item = candidates[0]
        offer = _offer_fields(item.get("offers"))
        brand = item.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        name = item.get("name") or (soup.title.get_text(" ", strip=True) if soup.title else "")
        return {
            "title": str(name or "Untitled product")[:500],
            "description": str(item.get("description") or "")[:4000],
            "brand": str(brand)[:160] if brand else None,
            "image_url": _first_image(item.get("image"), page_url),
            "canonical_url": page_url,
            "offer_label": "Structured product offer" if offer["price"] is not None else None,
            **offer,
        }
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"]
    if not title:
        return None
    description = soup.find("meta", attrs={"name": "description"})
    image = soup.find("meta", attrs={"property": "og:image"})
    price_meta = soup.find("meta", attrs={"property": "product:price:amount"})
    currency_meta = soup.find("meta", attrs={"property": "product:price:currency"})
    price = _float(price_meta.get("content")) if price_meta else extract_price(
        soup.get_text(" ", strip=True)[:5000]
    )
    return {
        "title": title[:500],
        "description": description.get("content", "")[:4000] if description else "",
        "image_url": _first_image(image.get("content"), page_url) if image else None,
        "price": price,
        "currency": currency_meta.get("content", "INR").upper()[:3] if currency_meta else "INR",
        "canonical_url": page_url,
        "offer_label": "Retailer page price" if price is not None else None,
    }
