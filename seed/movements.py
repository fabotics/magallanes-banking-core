"""Seed card transactions, dated relative to the day the seed runs.

The story stays fresh on any day: the golden-path restaurant charge is always
"last Sunday at lunch time, posted on Monday". Descriptors are cryptic on
purpose, the way they look on a real statement.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from seed.helpers import rut, seed_id
from seed.people import CURRENCY_BY_COUNTRY, country_of

BANK_TIMEZONE = ZoneInfo("America/Santiago")
RESTAURANT_TAX_ID = rut(66871234, hyphen=True)

# Two ordinary purchases (supermarket, pharmacy) per currency, for the supporting customers.
ORDINARY_AMOUNTS = {
    "CLP": (28990, 7490),
    "PEN": (112.50, 38.90),
    "COP": (148000, 42500),
    "MXN": (890.00, 245.50),
}
SUPPORTING_CUSTOMERS = ["carolina", "jorge", "lucia", "rosa", "diego", "camila", "andres", "sofia"]


def last_sunday(today: date) -> date:
    """Return the most recent Sunday strictly before `today`."""
    days_back = (today.weekday() + 1) % 7 or 7
    return today - timedelta(days=days_back)


def at(day: date, hour: int, minute: int) -> str:
    """Return an ISO timestamp for that day and time in the bank's timezone."""
    return datetime.combine(day, time(hour, minute), tzinfo=BANK_TIMEZONE).isoformat()


def movement(
    card: str, name: str, day: date, hour: int, minute: int, amount: float, descriptor: str,
    mcc: str, channel: str = "pos", country: str = "", tax_id: str | None = None,
    pending: bool = False, usd: float | None = None,
) -> dict:  # fmt: skip
    """Build one transaction row.

    A charge that is not pending is posted at the start of the next day, so a
    posting time is never in the future. `usd` marks a foreign charge: the
    original amount in US dollars.
    """
    home_country = country_of(card)
    return {
        "id": seed_id(f"transaction/{card}/{name}"),
        "card_id": seed_id(f"card/{card}"),
        "amount": amount,
        "currency": CURRENCY_BY_COUNTRY[home_country],
        "original_amount": usd,
        "original_currency": "USD" if usd else None,
        "descriptor": descriptor,
        "merchant_tax_id": tax_id,
        "mcc": mcc,
        "channel": channel,
        "country": country or home_country,
        "transaction_at": at(day, hour, minute),
        "posted_at": None if pending else at(day + timedelta(days=1), 0, 0),
        "status": "pending" if pending else "posted",
        "is_disputed": False,
    }


def build_transactions(today: date) -> list[dict]:
    """Build every seed transaction relative to `today`."""

    def ago(days: int) -> date:
        return today - timedelta(days=days)

    rows = [
        # Marta, golden path: a restaurant she does not recognize by its descriptor.
        movement("marta", "restaurant", last_sunday(today), 13, 42, 48900,
                 "MERPAGO*INVGASTRO PROV", "5812", tax_id=RESTAURANT_TAX_ID),
        movement("marta", "ride", ago(1), 20, 15, 6400, "APP*VIAJES STGO", "4121",
                 channel="ecommerce", pending=True),
        movement("marta", "supermarket", ago(3), 19, 5, 37250, "SUPERMERC DON LUCHO 012", "5411"),
        movement("marta", "pharmacy", ago(5), 11, 30, 12990, "FARM SALUD TOTAL PROV", "5912"),
        movement("marta", "fuel", ago(8), 8, 12, 30000, "ESTAC SERV RUTA 5 SUR", "5541"),
        movement("marta", "streaming", ago(12), 6, 0, 9480, "STREAMFLIX.COM 866-000", "4899",
                 channel="ecommerce", country="US", usd=9.99),
        movement("marta", "store", ago(20), 17, 48, 54990, "TIENDA DEPTO ALAMEDA", "5311"),
        # Pedro Pablo, real fraud: two online charges at about 03:00 from abroad in dollars.
        movement("pedro", "fraud-1", ago(2), 3, 4, 181900, "GAMEVAULT*TOPUP 4029", "5816",
                 channel="ecommerce", country="LT", usd=189.99),
        movement("pedro", "fraud-2", ago(2), 3, 11, 239400, "GAMEVAULT*TOPUP 4029", "5816",
                 channel="ecommerce", country="LT", usd=249.99),
        movement("pedro", "lunch-1", ago(4), 13, 10, 8900, "CASINO EMPRESAS OF 21", "5812"),
        movement("pedro", "supermarket", ago(6), 19, 40, 45120, "SUPERMERC DON LUCHO 007", "5411"),
        movement("pedro", "lunch-2", ago(10), 13, 5, 9200, "CASINO EMPRESAS OF 21", "5812"),
        movement("pedro", "fuel", ago(15), 7, 55, 25000, "ESTAC SERV RUTA 5 SUR", "5541"),
    ]  # fmt: skip
    for key in SUPPORTING_CUSTOMERS:
        groceries, pharmacy = ORDINARY_AMOUNTS[CURRENCY_BY_COUNTRY[country_of(key)]]
        rows.append(movement(key, "supermarket", ago(4), 18, 20, groceries,
                             "SUPERMERCADO CENTRAL 03", "5411"))  # fmt: skip
        rows.append(movement(key, "pharmacy", ago(9), 10, 45, pharmacy,
                             "FARMACIA DEL BARRIO", "5912"))  # fmt: skip
    return rows
