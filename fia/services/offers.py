def apply_price_evidence(product, item: dict) -> bool:
    """Replace prior offer evidence when a retailer page exposes a new current price."""
    price = item.get("price")
    if price is None:
        return False
    price = float(price)
    if price <= 0:
        return False

    original = item.get("original_price")
    original = float(original) if original is not None else None
    product.price = price
    product.currency = str(item.get("currency") or product.currency or "INR").upper()[:3]

    if original is not None and original > price:
        product.original_price = original
        # Derive the discount from source prices so old or inconsistent percentages cannot persist.
        product.discount_percent = round((1 - price / original) * 100, 1)
    else:
        product.original_price = None
        product.discount_percent = None

    # These fields describe the latest offer; absent values clear older, unsupported claims.
    product.offer_label = item.get("offer_label")
    product.offer_valid_until = item.get("offer_valid_until")
    product.availability = item.get("availability")
    return True


def should_emit_price_alert(
    drop_percent: float,
    threshold_percent: float,
    within_cooldown: bool,
) -> bool:
    """Apply the user's minimum-drop preference and avoid repeated alerts."""
    return drop_percent >= max(0.0, threshold_percent) and not within_cooldown
