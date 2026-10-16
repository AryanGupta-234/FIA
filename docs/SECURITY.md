# Security and research policy

- Research-only: FIA has no store login, cart, checkout, payment or purchase actions.
- The API binds to localhost by default. CORS is restricted to the local Vite origin unless explicitly changed.
- Keep provider credentials in .env or a secret manager. Never commit .env.
- Only HTTP(S) product-page URLs are accepted. The fetcher checks DNS results for public addresses, checks robots.txt, refuses redirects and limits time and response bytes.
- If robots.txt cannot be retrieved or returns an access-denied/error status, page fetching fails closed. A published 404/410 robots policy is treated as no published rule.
- FIA does not bypass CAPTCHAs, authentication, paywalls, rate limits, anti-bot controls or technical restrictions. Use provider APIs and permitted retailer data sources.
- DNS validation in application code is best-effort SSRF mitigation, not a hardened public egress gateway. Public multi-user deployment needs network-level egress filtering and redirect revalidation.
- Product text, images, reviews and metadata are untrusted. Treat them as data, never as executable instructions.
- Trust labels describe visible domain-level evidence only. They do not verify third-party marketplace seller identity or counterfeit status.
- Offer data is time-sensitive. Confirm price, seller, stock, size, delivery, returns and coupon terms on the retailer's live page before buying.
- FIA stores research history and preferences locally in its configured database. Secure the Windows account and local database directory accordingly.
