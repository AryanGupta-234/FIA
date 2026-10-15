import pytest

from fia.services.normalize import canonicalize_url, extract_price


def test_canonicalize_removes_tracking_parameters():
    assert canonicalize_url("https://www.Example.com/item?utm_source=x&id=7#top") == "https://example.com/item?id=7"


def test_rejects_non_http_url():
    with pytest.raises(ValueError):
        canonicalize_url("javascript:alert(1)")


@pytest.mark.parametrize(("value", "expected"), [
    ("₹2,499", 2499), ("Rs. 999", 999), ("INR 1,299.50", 1299.5)
])
def test_extract_price(value, expected):
    assert extract_price(value) == expected
