# Magallanes banking core

A mock banking core API for Banco Magallanes, a fictional Latin American retail bank. It is built to be called by conversational agents as tools: verify a customer, read balances and card transactions, block a card, open a case, check insurance eligibility.

Status: work in progress. The full documentation arrives with the first release.

## Stack

Python 3.12, FastAPI, Postgres on Supabase, pytest, ruff.

## Run it locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # then set BANK_API_KEY
uvicorn app.main:app --reload
```

The health check is at `http://localhost:8000/health` and the interactive docs at `http://localhost:8000/docs`.

## Tests

```bash
ruff check .
ruff format --check .
pytest -q
```

## License

MIT. See `LICENSE`.
