"""Seed card transactions, dated relative to the day the seed runs.

The story stays fresh on any day: each of the demo customers spent a Saturday
evening at the same restaurant and bar, where each round was paid on its own,
and the place presented the whole weekend to the bank on Monday. So each one
sees several charges dated Monday for things bought on Saturday night.
Descriptors are cryptic on purpose, the way they look on a real statement.
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


# The evening at the restaurant: hour, minute and amount of each round.
EVENING_ROUNDS = [(21, 52, 8400), (22, 37, 11200), (23, 14, 8400), (23, 58, 6900)]
EMMA_ROUNDS = [(20, 41, 9800), (21, 34, 7600), (22, 18, 12400), (23, 5, 7600), (23, 49, 5900)]
DANIEL_ROUNDS = [(20, 55, 6800), (21, 48, 9400), (22, 31, 7200), (23, 12, 9400), (23, 54, 5600)]
EVENINGS = (("daniel", DANIEL_ROUNDS), ("emma", EMMA_ROUNDS), ("marta", EVENING_ROUNDS))


def posting_monday(today: date) -> date:
    """Return the most recent Monday, today included: the day the evening was posted."""
    return today - timedelta(days=today.weekday())


def at(day: date, hour: int, minute: int) -> str:
    """Return an ISO timestamp for that day and time in the bank's timezone."""
    return datetime.combine(day, time(hour, minute), tzinfo=BANK_TIMEZONE).isoformat()


def movement(
    card: str, name: str, day: date, hour: int, minute: int, amount: float, descriptor: str,
    mcc: str, channel: str = "pos", country: str = "", tax_id: str | None = None,
    pending: bool = False, usd: float | None = None, posted: date | None = None,
) -> dict:  # fmt: skip
    """Build one transaction row.

    A charge that is not pending is posted at the start of the next day, so a
    posting time is never in the future. `posted` sets another posting day,
    for a merchant that presents its sales late. `usd` marks a foreign charge:
    the original amount in US dollars.
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
        "posted_at": None if pending else at(posted or day + timedelta(days=1), 0, 0),
        "status": "pending" if pending else "posted",
        "is_disputed": False,
    }


def build_transactions(today: date) -> list[dict]:
    """Build every seed transaction relative to `today`."""

    def ago(days: int) -> date:
        return today - timedelta(days=days)

    monday = posting_monday(today)
    saturday = monday - timedelta(days=2)
    # Daniel, Emma and Marta, golden path: rounds on Saturday night, all posted on Monday.
    rows = [
        movement(key, f"restaurant-{number}", saturday, hour, minute, amount,
                 "MERPAGO*INVGASTRO PROV", "5812", tax_id=RESTAURANT_TAX_ID, posted=monday)
        for key, rounds in EVENINGS
        for number, (hour, minute, amount) in enumerate(rounds, start=1)
    ]  # fmt: skip
    rows += [
        movement("daniel", "ride", ago(1), 18, 55, 5900, "APP*VIAJES STGO", "4121",
                 channel="ecommerce", pending=True),
        movement("daniel", "supermarket", ago(2), 19, 30, 41870, "SUPERMERC DON LUCHO 012", "5411"),
        movement("daniel", "gym", ago(7), 7, 15, 34900, "CLUB DEPORTIVO ORIENTE", "7997"),
        movement("daniel", "streaming", ago(12), 6, 0, 9480, "STREAMFLIX.COM 866-000", "4899",
                 channel="ecommerce", country="US", usd=9.99),
        movement("daniel", "airline", ago(21), 9, 5, 688400, "AEROSUR WEB SCL", "4511",
                 channel="ecommerce"),
        movement("emma", "ride", ago(1), 19, 40, 7200, "APP*VIAJES STGO", "4121",
                 channel="ecommerce", pending=True),
        movement("emma", "supermarket", ago(3), 18, 25, 52340, "SUPERMERC DON LUCHO 012", "5411"),
        movement("emma", "bookshop", ago(6), 13, 10, 18900, "LIBRERIA DEL PARQUE PROV", "5942"),
        movement("emma", "streaming", ago(12), 6, 0, 9480, "STREAMFLIX.COM 866-000", "4899",
                 channel="ecommerce", country="US", usd=9.99),
        movement("emma", "airline", ago(18), 10, 22, 412600, "AEROSUR WEB SCL", "4511",
                 channel="ecommerce"),
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
