# Security

This is a demonstration project. The bank, the customers and every number in it are invented, and no real money or personal data is behind the API. Reports are still welcome.

## Reporting a problem

Use GitHub's private reporting: the **Security** tab of this repository, then **Report a vulnerability**. Please do not open a public issue for something that exposes a key or lets a caller skip a check. You can expect an answer within a week.

If you find a key or a token anywhere in this repository or its history, report it the same way. It will be revoked first and removed second.

## How the API protects itself

| Layer | What it does |
| --- | --- |
| Callers | Every `/v1` and `/mcp` route needs the API key, compared in constant time. With no key configured, everything is refused |
| Customers | Customer data needs a session token from identity verification. Tokens are random (`secrets.token_urlsafe`), last 15 minutes and belong to one customer |
| Lockout | Three failed verifications within 15 minutes lock a document. Three wrong PINs lock the app for one minute |
| PINs | Stored only as a salted PBKDF2-HMAC-SHA256 hash. Never logged, never returned |
| Database | Row level security on every table with no policies. Only the server-side key reads or writes, and it never reaches a browser |
| Audit | One row per call. Tokens, PINs and full document numbers are never written to it |
| Errors | One JSON shape. No stack traces and no internal detail leave the server |
| Dependencies | Pinned versions, checked on every pull request for known vulnerabilities, updated weekly |

## Known limits of the demo

These are accepted for a mock and would be closed before real use:

- One shared API key for all callers, with no rate limiting in the API itself.
- A four digit PIN. The lock slows guessing down but a real app would add device binding.
- The `conversation-ended` notice is authenticated by the API key only. It carries no signature of its sender and no replay protection.
- The session token is also accepted as a query parameter, for callers that cannot set headers. The header is preferred because addresses can end up in access logs.
- Seed customers have fixed, predictable ids, so that a reseed keeps every link working.
