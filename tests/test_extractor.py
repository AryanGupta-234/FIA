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


def test_invalid_gtin_is_not_used_as_cross_retailer_identity():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Uncoded item","gtin13":"not-a-valid-barcode"}
    </script>
    </head><body></body></html>
    """
    result = extract_product(html, "https://shop.example/uncoded")
    assert result is not None
    assert "gtin" not in result


def test_extract_schema_org_microdata_when_jsonld_is_absent():
    html = """
    <html><head><title>Item page</title></head><body>
      <div itemscope itemtype="https://schema.org/Product">
        <span itemprop="name">Cotton poplin shirt</span>
        <span itemprop="brand" itemscope itemtype="https://schema.org/Brand">
          <span itemprop="name">Example Label</span>
        </span>
        <span itemprop="color">Navy</span>
        <span itemprop="material">Cotton</span>
        <span itemprop="size">L</span>
        <span itemprop="sku">POP-NV-L</span>
        <img itemprop="image" src="/images/poplin.jpg">
        <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
          <meta itemprop="price" content="1799">
          <meta itemprop="priceCurrency" content="INR">
          <link itemprop="availability" href="https://schema.org/InStock">
        </div>
      </div>
    </body></html>
    """
    result = extract_product(html, "https://shop.example/poplin")
    assert result is not None
    assert result["title"] == "Cotton poplin shirt"
    assert result["brand"] == "Example Label"
    assert result["colour"] == "Navy"
    assert result["material"] == "Cotton"
    assert result["size_label"] == "L"
    assert result["sku"] == "POP-NV-L"
    assert result["image_url"] == "https://shop.example/images/poplin.jpg"
    assert result["price"] == 1799
    assert result["currency"] == "INR"
