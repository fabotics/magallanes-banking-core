"""The seed data tells the stories the API is built around, on any day of the week."""

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from seed.data import TABLES, build_seed
from seed.helpers import curp_check_digit, rut_check_digit, seed_id
from seed.movements import RESTAURANT_TAX_ID

WEDNESDAY = date(2026, 11, 11)
ONE_WEEK = [WEDNESDAY + timedelta(days=offset) for offset in range(7)]
SCHEMA = (Path(__file__).parent.parent / "db" / "schema.sql").read_text()


def card_transactions(seed: dict, key: str) -> list[dict]:
    return [row for row in seed["transactions"] if row["card_id"] == seed_id(f"card/{key}")]


def test_rut_check_digit_matches_known_values() -> None:
    assert rut_check_digit(12345678) == "5"
    assert rut_check_digit(11111111) == "1"
    assert rut_check_digit(6) == "K"


def test_curp_check_digit_matches_a_known_value() -> None:
    assert curp_check_digit("HEGG560427MVZRRL0") == "4"


def test_ten_fictional_customers_across_four_countries() -> None:
    customers = build_seed(WEDNESDAY)["customers"]
    assert len(customers) == 10
    assert {row["country"] for row in customers} == {"CL", "PE", "CO", "MX"}
    assert all(row["email"].endswith("@example.com") for row in customers)
    assert len({row["document_number"] for row in customers}) == 10


def test_demo_email_goes_to_the_golden_path_customer_only() -> None:
    customers = build_seed(WEDNESDAY, demo_email="demo@example.org")["customers"]
    assert [row["first_name"] for row in customers if row["email"] == "demo@example.org"] == [
        "Marta"
    ]


@pytest.mark.parametrize("today", ONE_WEEK)
def test_restaurant_charge_is_last_sunday_at_lunch_posted_on_monday(today: date) -> None:
    seed = build_seed(today)
    charge = next(row for row in seed["transactions"] if row["merchant_tax_id"])
    made = datetime.fromisoformat(charge["transaction_at"])
    posted = datetime.fromisoformat(charge["posted_at"])
    assert charge["card_id"] == seed_id("card/marta")
    assert charge["merchant_tax_id"] == RESTAURANT_TAX_ID
    assert made.weekday() == 6 and made.hour == 13
    assert 1 <= (today - made.date()).days <= 7
    assert posted.weekday() == 0 and charge["status"] == "posted"


def test_golden_path_customer_has_one_pending_charge_and_no_policy() -> None:
    seed = build_seed(WEDNESDAY)
    pending = [row for row in card_transactions(seed, "marta") if row["status"] == "pending"]
    assert len(pending) == 1 and pending[0]["posted_at"] is None
    assert seed_id("customer/marta") not in {row["customer_id"] for row in seed["policies"]}


def test_fraud_customer_has_two_night_charges_from_abroad_in_dollars() -> None:
    seed = build_seed(WEDNESDAY)
    foreign = [row for row in card_transactions(seed, "pedro") if row["country"] != "CL"]
    assert len(foreign) == 2
    for row in foreign:
        assert row["original_currency"] == "USD" and row["channel"] == "ecommerce"
        assert datetime.fromisoformat(row["transaction_at"]).hour == 3


def test_supporting_personas() -> None:
    seed = build_seed(WEDNESDAY)
    by_name = {row["first_name"]: row for row in seed["customers"]}
    cards = {row["customer_id"]: row for row in seed["cards"]}
    assert seed["policies"][0]["customer_id"] == by_name["Carolina"]["id"]
    assert by_name["Jorge"]["is_vulnerable"] is True
    assert cards[by_name["Lucia"]["id"]]["status"] == "blocked_temporary"
    assert cards[by_name["Lucia"]["id"]]["blocked_at"] is not None


def test_every_seed_table_and_column_exists_in_the_schema() -> None:
    seed = build_seed(WEDNESDAY)
    assert list(seed) == TABLES
    for table, rows in seed.items():
        match = re.search(rf"create table if not exists {table} \((.*?)\n\);", SCHEMA, re.DOTALL)
        assert match, f"table {table} is missing from db/schema.sql"
        columns = {line.split()[0] for line in match.group(1).splitlines() if line.strip()}
        for row in rows:
            assert set(row) <= columns, f"{table}: {set(row) - columns} not in schema"
