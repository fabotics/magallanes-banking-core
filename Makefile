# Common tasks. Run `make help` to list them. Needs Python 3.12.

.PHONY: help install run test lint format seed smoke audit

help:  ## List the tasks
	@grep -E '^[a-z]+:.*##' Makefile | sed 's/:.*## /\t/'

install:  ## Create .venv and install the dependencies
	python3.12 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

run:  ## Start the API on http://localhost:8000
	.venv/bin/uvicorn app.main:app --reload

test:  ## Run the tests with coverage
	.venv/bin/pytest -q --cov --cov-report=term-missing:skip-covered

lint:  ## Check style and formatting
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:  ## Fix formatting and import order
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

seed:  ## Wipe the database in .env and reload the fictional data
	.venv/bin/python scripts/seed.py --reset

smoke:  ## Walk the main path against a running local instance
	.venv/bin/python scripts/smoke_test.py --base-url http://localhost:8000

audit:  ## Check the dependencies for known vulnerabilities
	.venv/bin/pip-audit -r requirements.txt
