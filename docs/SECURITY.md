# Security and research safety

- Research-only: the code has no account login, cart, checkout, payment or order placement.
- The API binds to localhost by default. Restrict CORS before exposing it.
- Never commit secrets. Put provider credentials in environment variables or a secret manager.
- Fetcher accepts HTTP(S) only, rejects private/loopback/link-local resolved addresses, does not auto-follow redirects, and bounds time and response size.
- Robots policy is consulted. If policy cannot be retrieved, fetching fails closed. Follow retailer terms, API policies and rate limits.
- Never bypass CAPTCHAs, authentication, paywalls, anti-bot controls or technical restrictions.
- The app's DNS check is best-effort SSRF protection, not a hardened public multi-tenant egress gateway. Public deployment needs network-level egress filtering and redirect revalidation.
- External descriptions, reviews and metadata are untrusted content, not instructions.
- Trust labels are evidence hints, not guarantees of authenticity or retailer certification. Marketplace seller-level verification needs source data that identifies the seller.
- Always verify price, stock, size, delivery and returns on the retailer's live site before purchasing.
