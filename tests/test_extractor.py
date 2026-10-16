from fia.crawling.extractor import extract_product


def test_extract_structured_product_offer_and_image():
    html = """
    <html><head><title>Test shoe</title>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "Canvas low-top shoe",
      "brand": {"@type": "Brand", "name": "Example"},
      "image": ["/media/shoe.jpg"],
      "offers": {
        "@type": "Offer",
        "price": "1499",
        "priceCurrency": "INR",
        "availability": "https://schema.org/InStock",
        "priceValidUntil": "2026-12-31",
        "seller": {"@type": "Organization", "name": "Example Retail"}
      }
    }
    </script></head><body></body></html>
    """
    result = extract_product(html, "https://shop.example/products/shoe")
    assert result is not None
    assert result["title"] == "Canvas low-top shoe"
    assert result["brand"] == "Example"
    assert result["image_url"] == "https://shop.example/media/shoe.jpg"
    assert result["price"] == 1499
    assert result["currency"] == "INR"
    assert result["seller_name"] == "Example Retail"


def test_ignore_non_product_jsonld_and_handle_bad_json():
    html = """
    <html><head><title>Simple page</title>
    <script type="application/ld+json">{ broken }</script>
    <script type="application/ld+json">{"@type":"WebPage","name":"Not a product"}</script>
    <meta property="og:image" content="/shirt.png">
    </head><body><p>₹2,499</p></body></html>
    """
    result = extract_product(html, "https://shop.example/item")
    assert result is not None
    assert result["title"] == "Simple page"
    assert result["image_url"] == "https://shop.example/shirt.png"
    assert result["price"] == 2499
