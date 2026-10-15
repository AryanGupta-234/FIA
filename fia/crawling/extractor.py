import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from fia.services.normalize import extract_price


def walk_jsonld(node):
    if isinstance(node, list):
        for child in node:
            yield from walk_jsonld(child)
    elif isinstance(node, dict):
        kind = node.get("@type", [])
        if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
            yield node
        for child in node.values():
            if isinstance(child, (dict, list)):
                yield from walk_jsonld(child)


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
        offers = item.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        try:
            price = float(offers["price"]) if isinstance(offers, dict) and offers.get("price") is not None else None
        except (TypeError, ValueError):
            price = None
        image = item.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        brand = item.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        title = item.get("name") or (soup.title.get_text(" ", strip=True) if soup.title else "Untitled product")
        return {"title": str(title)[:500], "description": str(item.get("description") or "")[:4000],
                "brand": brand, "image_url": urljoin(page_url, image) if isinstance(image, str) else None,
                "price": price, "availability": offers.get("availability") if isinstance(offers, dict) else None,
                "currency": offers.get("priceCurrency", "INR") if isinstance(offers, dict) else "INR",
                "canonical_url": page_url}
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        title = og_title["content"]
    if not title:
        return None
    description = soup.find("meta", attrs={"name": "description"})
    image = soup.find("meta", attrs={"property": "og:image"})
    return {"title": title[:500], "description": description.get("content", "")[:4000] if description else "",
            "image_url": urljoin(page_url, image["content"]) if image and image.get("content") else None,
            "price": extract_price(soup.get_text(" ", strip=True)[:5000]),
            "currency": "INR", "canonical_url": page_url}
