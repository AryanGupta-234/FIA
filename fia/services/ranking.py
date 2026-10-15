from fia.services.trust import assess_url


def rank_product(product: dict, query: str, budget_max: float | None = None) -> dict:
    title = (product.get("title") or "").lower()
    description = (product.get("description") or "").lower()
    terms = {term for term in query.lower().split() if len(term) > 2}
    haystack = f" {title} {description} "
    overlap = sum(1 for term in terms if term in haystack)
    relevance = overlap / max(len(terms), 1)
    reasons = [f"Matches {overlap} of {len(terms)} query terms"]
    price = product.get("price")
    if budget_max is not None:
        if price is not None and price <= budget_max:
            relevance += 0.15
            reasons.append("Within stated budget")
        elif price is not None:
            relevance -= 0.20
            reasons.append("Above stated budget")
        else:
            reasons.append("Price unavailable; budget fit cannot be assessed")
    evidence = assess_url(product.get("canonical_url") or product.get("url") or "")
    reasons.extend(evidence["reasons"])
    return {**product, "relevance_score": round(max(0, min(1, relevance)), 3),
            "trust_score": evidence["score"], "trust_label": evidence["label"],
            "retailer_name": product.get("retailer_name") or evidence["retailer_name"],
            "reasons": reasons}
