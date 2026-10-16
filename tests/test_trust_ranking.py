from fia.services.ranking import rank_product
from fia.services.trust import assess_url, retailer_name


def test_known_domain_does_not_imply_seller_authenticity():
    result = assess_url("https://www.myntra.com/shoes")
    assert result["retailer_name"] == "Myntra"
    assert result["score"] < 1


def test_domain_matching_is_exact():
    assert retailer_name("myntra.com.attacker.example") is None


def test_budget_affects_rank():
    item = {
        "title": "White casual sneakers",
        "canonical_url": "https://myntra.com/shoe",
        "price": 2200,
    }
    under = rank_product(item, "white sneakers", 3000)
    over = rank_product(item, "white sneakers", 1000)
    assert under["relevance_score"] > over["relevance_score"]
