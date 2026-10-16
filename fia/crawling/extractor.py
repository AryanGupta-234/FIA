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


def _text(value) -> str | None:
    if isinstance(value, list):
        value = next((part for part in value if part not in (None, "")), None)
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or value.get("text")
    if value is None:
        return None
    normalized = " ".join(str(value).split()).strip()
    return normalized[:160] if normalized else None


def _additional_properties(item: dict) -> dict[str, str]:
    raw = item.get("additionalProperty") or []
    entries = raw if isinstance(raw, list) else [raw]
    values = {}
    aliases = {
        "colour": "colour", "color": "colour", "material": "material",
        "fit": "fit", "size": "size_label", "gender": "gender",
        "product type": "product_type", "product_type": "product_type",
    }
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("name") or "").strip().lower()
        target = aliases.get(key)
        value = _text(entry.get("value") or entry.get("valueReference"))
        if target and value:
            values[target] = value
    return values


def _validated_gtin(value) -> str | None:
    parsed = _text(value)
    if not parsed:
        return None
    digits = "".join(character for character in parsed if character.isdigit())
    return digits if len(digits) in {8, 12, 13, 14} else None


def _fashion_fields(item: dict) -> dict:
    audience = item.get("audience") or {}
    if not isinstance(audience, dict):
        audience = {}
    fields = _additional_properties(item)
    candidates = {
        "product_type": item.get("category") or item.get("productGroupID"),
        "colour": item.get("colour") or item.get("color"),
        "material": item.get("material"),
        "fit": item.get("fit"),
        "size_label": item.get("size"),
        "gender": item.get("gender") or audience.get("suggestedGender"),
        "sku": item.get("sku") or item.get("mpn"),
        "gtin": (
            item.get("gtin13") or item.get("gtin12")
            or item.get("gtin14") or item.get("gtin8") or item.get("gtin")
        ),
    }
    for key, value in candidates.items():
        parsed = _validated_gtin(value) if key == "gtin" else _text(value)
        if parsed:
            fields[key] = parsed
    return fields


def _meta_value(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if node and node.get("content"):
            value = _text(node.get("content"))
            if value:
                return value
    return None


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


def _itemprop(scope, name: str) -> str | None:
    if scope is None:
        return None
    node = scope.find(attrs={"itemprop": name})
    if node is None:
        return None
    for attribute in ("content", "src", "href"):
        if node.get(attribute):
            return _text(node.get(attribute))
    return _text(node.get_text(" ", strip=True))


def _extract_microdata_product(soup: BeautifulSoup, page_url: str) -> dict | None:
    scope = soup.find(
        attrs={
            "itemscope": True,
            "itemtype": lambda value: bool(
                value and "schema.org/product" in str(value).lower()
            ),
        }
    )
    if scope is None:
        return None

    offer_scope = scope.find(attrs={"itemprop": "offers"}) or scope
    seller_scope = offer_scope.find(attrs={"itemprop": "seller"})
    brand_scope = scope.find(attrs={"itemprop": "brand"})
    image_value = _itemprop(scope, "image")
    fashion = _fashion_fields({
        "category": _itemprop(scope, "category"),
        "color": _itemprop(scope, "color"),
        "material": _itemprop(scope, "material"),
        "fit": _itemprop(scope, "fit"),
        "size": _itemprop(scope, "size"),
        "gender": _itemprop(scope, "gender"),
        "sku": _itemprop(scope, "sku"),
        "gtin13": _itemprop(scope, "gtin13"),
        "gtin12": _itemprop(scope, "gtin12"),
        "gtin14": _itemprop(scope, "gtin14"),
        "gtin8": _itemprop(scope, "gtin8"),
    })
    offer = _offer_fields({
        "price": _itemprop(offer_scope, "price"),
        "priceCurrency": _itemprop(offer_scope, "priceCurrency"),
        "availability": _itemprop(offer_scope, "availability"),
        "priceValidUntil": _itemprop(offer_scope, "priceValidUntil"),
        "seller": _itemprop(seller_scope, "name") if seller_scope else None,
    })
    name = _itemprop(scope, "name") or (
        soup.title.get_text(" ", strip=True) if soup.title else "Untitled product"
    )
    brand = (
        _itemprop(brand_scope, "name") or _text(brand_scope.get_text(" ", strip=True))
        if brand_scope else _itemprop(scope, "brand")
    )
    description = _itemprop(scope, "description")
    return {
        "title": str(name)[:500],
        "description": str(description or "")[:4000],
        "brand": brand,
        "image_url": _first_image(image_value, page_url),
        "canonical_url": page_url,
        "offer_label": "Microdata product offer" if offer["price"] is not None else None,
        **fashion,
        **offer,
    }


def extract_product(html: str, page_url: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    candidates = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            candidates.extend(walk_jsonld(json.loads(script.string or script.get_text())))
        except (json.JSONDecodeError, TypeError):
            continue
    if not candidates:
        microdata_product = _extract_microdata_product(soup, page_url)
        if microdata_product is not None:
            return microdata_product
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
            "brand": _text(brand),
            **_fashion_fields(item),
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
    fashion = {
        "product_type": _meta_value(soup, "product:category", "og:category"),
        "colour": _meta_value(soup, "product:color", "product:colour"),
        "material": _meta_value(soup, "product:material"),
        "fit": _meta_value(soup, "product:fit"),
        "size_label": _meta_value(soup, "product:size"),
        "gender": _meta_value(soup, "product:gender"),
        "sku": _meta_value(soup, "product:retailer_item_id"),
        "gtin": _meta_value(soup, "product:gtin"),
    }
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
        **{key: value for key, value in fashion.items() if value},
    }
