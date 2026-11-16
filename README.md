# Magallanes banking core

A mock banking core API for Banco Magallanes, a fictional Latin American retail bank. It is built to be called by conversational agents as tools: verify a customer, read balances and card transactions, block a card, open a case for a person, check insurance eligibility, record an offer and send a proposal to sign.

Everything in it is invented: the bank, the customers, the document numbers, the merchants.

## Why it looks the way it does

A language model follows a prompt most of the time. A bank needs rules that hold all of the time. So the rules that matter are enforced by the API, not left to the agent.

| Rule | How the API enforces it |
| --- | --- |
| Identity before data | Every customer endpoint needs a session token issued by identity verification. No token, HTTP 401 |
| Short sessions | A session lasts 15 minutes and belongs to one customer |
| Limited attempts | Three failed verifications for a document within 15 minutes lock it |
| Only reversible actions | The only state change on a card is a temporary block. No endpoint moves money |
| Eligibility is the bank's decision | The API computes which insurance products may be offered. An offer for anything else is refused |
| Consent is recorded | Every offer and the customer's answer is stored. A sale is signed by the customer on a page, not by voice |
| Never a dead end | A handoff case can be opened without a verified session, with no customer data attached |
| Everything is recorded | Every `/v1` call writes an audit row. Tokens and full document numbers are never logged |
| Only known callers | Every `/v1` call needs the `X-API-Key` header |

## Architecture

```
  Conversational agent
          |
          |  HTTPS, X-API-Key, X-Session-Token
          v
  +-----------------------------+        +--------------------+
  |  Banking core API (FastAPI) |        |  Customer browser  |
  |                             | <----- |  /sign/{token}     |
  |  security   API key, session|        +--------------------+
  |  audit      one row per call|
  |  routers    one per domain  |
  |  db         repository      |
  +-----------------------------+
          |
          v
  Postgres on Supabase (row level security on every table)
```

Stack: Python 3.12, FastAPI, Postgres on Supabase through the `supabase` client, Jinja2 for the signature page, pytest and ruff. Hosted as a single serverless function.

All database access goes through one small repository interface in `app/db.py`. The tests replace it with an in-memory version loaded with the same seed data, so they need no network.

```
app/
  main.py              app factory, routers, middleware
  config.py            settings from the environment
  security.py          API key check, session check
  audit.py             audit middleware
  db.py                repository: every database call
  errors.py            one error shape: {"error", "message"}
  email.py             optional proposal email
  schemas.py, schemas_insurance.py
  routers/             identity, customers, accounts, cards, cases, insurance, signing
  templates/sign.html  signature page
db/schema.sql          tables, checks, indexes, row level security
seed/                  fictional customers and transactions, dated relative to today
scripts/               seed.py, smoke_test.py
tests/                 one file per area, plus the in-memory repository
```

## Data model

| Table | Purpose |
| --- | --- |
| `customers` | Who the bank knows: document, name, segment, language, vulnerable flag |
| `accounts` | Balances per account |
| `cards` | Cards and their status: active, blocked_temporary, blocked |
| `transactions` | Card movements as on a statement: a cryptic descriptor, sometimes a merchant tax ID, never a merchant name |
| `insurance_products` | The catalog, with the segments each product is open to |
| `policies` | Who already holds which product |
| `insurance_offers` | Every offer made and the customer's answer. The consent record |
| `proposals` | Proposals sent, with their signing token and status |
| `cases` | Fraud cases, handoffs, complaints and callbacks, numbered `MG-<year>-<sequence>` |
| `verification_sessions` | Proof that identity was verified, with an expiry |
| `verification_attempts` | Used by the lockout rule |
| `audit_log` | One row per API call: endpoint, customer, conversation, outcome |

Row level security is enabled on every table with no policies, so only the server-side key can read or write.

## Endpoints

Interactive documentation is served at `/docs`.

| Method and path | Session | Purpose |
| --- | --- | --- |
| GET `/health` | no | Liveness and database status |
| POST `/v1/identity/verify` | no | Verify the customer and open a session |
| GET `/v1/customers/me` | yes | First name, segment, language, products held |
| GET `/v1/accounts/balance` | yes | Available balance per account |
| GET `/v1/cards/transactions` | yes | Recent card movements, newest first. `days` (default 30), `status` (all, pending, posted) |
| POST `/v1/cards/block` | yes | Temporary block. Returns a reference |
| POST `/v1/cases` | handoff: optional | Fraud case, handoff, complaint or callback. Returns a case number |
| GET `/v1/insurance/eligibility` | yes | Products the bank pre-approves, or the reason there are none |
| POST `/v1/insurance/offers` | yes | Record an offer and the answer: accepted, declined, info_requested |
| POST `/v1/insurance/proposals` | yes | Create the proposal for an offer. Accepted offers get a signing link |
| GET, POST `/sign/{token}` | no | Signature page. Signing creates the policy |

The session token goes in the `X-Session-Token` header (preferred). It is also accepted as a `session_token` query parameter on GET and as a `session_token` body field on POST.

Errors always have the same shape:

```json
{"error": "identity_not_verified", "message": "Verify the customer's identity before this request."}
```

Example:

```bash
curl -X POST http://localhost:8000/v1/identity/verify \
  -H "X-API-Key: $BANK_API_KEY" -H "Content-Type: application/json" \
  -d '{"document_number": "31.415.926-8", "card_last4": "4821", "birth_year": 1986}'
```

```json
{"verified": true, "locked": false, "session_token": "...", "first_name": "Marta"}
```

A wrong answer never says which field was wrong:

```json
{"verified": false, "locked": false, "attempts_remaining": 2}
```

## Run it locally

You need Python 3.12 and a Supabase project (the free tier is enough).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Fill `.env`: the Supabase project URL, its secret key (not the publishable one), the Postgres connection string, and a `BANK_API_KEY` of your own (`openssl rand -hex 32`).

Create the tables, load the seed data and start the API:

```bash
set -a; source .env; set +a
psql "$SUPABASE_DB_URL" -f db/schema.sql
python scripts/seed.py --reset
uvicorn app.main:app --reload
```

`python scripts/seed.py --reset` wipes every table and reloads the seed. Dates are relative to the day it runs, so the story is always recent. It also clears verification attempts, which unlocks a locked customer.

### Seed customers

| Customer | Document | Card | Birth year | Story |
| --- | --- | --- | --- | --- |
| Marta | 31.415.926-8 | 4821 | 1986 | Does not recognize a restaurant charge from last Sunday. Eligible for insurance |
| Pedro Pablo | 32.718.281-1 | 7730 | 1979 | Two online charges at night from abroad, in dollars |
| Carolina | 33.161.803-9 | 1164 | 1991 | Already holds the card fraud product |
| Jorge | 30.577.215-1 | 9052 | 1948 | Flagged as vulnerable: offers go to a human advisor |
| Lucia | 34.141.421-0 | 3378 | 1995 | Her card is already blocked |

Five more customers in Peru, Colombia and Mexico use other document types and currencies.

## Tests

```bash
ruff check .
ruff format --check .
pytest -q
```

The tests run on an in-memory repository and need no network or `.env`. The same checks run on every pull request.

To check a running instance end to end:

```bash
python scripts/smoke_test.py --base-url http://localhost:8000
```

## Deploy

The API runs on Vercel as one Python function with no extra configuration: `app/main.py` exports `app`, dependencies come from `requirements.txt`, and `.python-version` selects Python 3.12.

1. Import the repository as a new Vercel project. Production branch: `main`.
2. Set the environment variables: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `BANK_API_KEY`, and `PUBLIC_BASE_URL` (the production URL, used to build signing links). Optional: `TRANSACTIONS_DELAY_SECONDS`, `RESEND_API_KEY`, `EMAIL_FROM`.
3. Deploy, then run the smoke test against the production URL.

## Connecting an agent

Each endpoint maps to one webhook tool on any agent platform that can call HTTP APIs.

- Store `BANK_API_KEY` as a secret on the platform and send it in `X-API-Key` on every tool.
- After `verify identity`, keep `session_token` for the rest of the conversation and send it in `X-Session-Token`.
- Pass the platform's conversation ID as `conversation_id` when verifying. The API then ties every later call, case and offer to that conversation.
- Keep `offer_id` from `offers` to request the proposal, and read `case_number` and block `reference` back to the customer.
- `transactions` waits about one second before answering, like a legacy system would. Have the agent say something while it waits.
- When `eligibility` answers `eligible: false`, the agent makes no offer. When `verify` answers `locked: true`, the agent opens a handoff case.

## Roadmap

- Call summary sent to the customer's messaging channel after the conversation.
- Merchant registry: look up the business behind a tax ID, over REST and as an MCP tool.
- CRM sync for cases and opportunities.
- Operations dashboard on the audit, offers and cases tables.
- Proposal expiry.

## License

MIT. See `LICENSE`.
