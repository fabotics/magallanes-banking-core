"""Seed customers with their accounts and cards.

Everyone here is invented. Chilean document numbers use the 30 to 35 million
range, which has not been issued to anyone, and carry a valid check digit.
Document numbers are stored without dots or hyphens.
"""

from seed.helpers import curp_check_digit, rut, seed_id

CURRENCY_BY_COUNTRY = {"CL": "CLP", "PE": "PEN", "CO": "COP", "MX": "MXN"}

SOFIA_CURP = "ROGS900514MDFBRF0"

# key, document type, document number, first name, last name, birth date,
# country, language, segment, vulnerable
PEOPLE = [
    ("marta", "RUT", rut(31415926), "Marta", "Rojas Fuentes", "1986-03-14",
     "CL", "es", "preferred", False),
    ("pedro", "RUT", rut(32718281), "Pedro Pablo", "Soto Aravena", "1979-11-02",
     "CL", "es", "preferred", False),
    ("carolina", "RUT", rut(33161803), "Carolina", "Vega Morales", "1991-07-23",
     "CL", "es", "mass", False),
    ("jorge", "RUT", rut(30577215), "Jorge", "Navarro Pizarro", "1948-05-09",
     "CL", "es", "mass", True),
    ("lucia", "RUT", rut(34141421), "Lucia", "Campos Tapia", "1995-01-30",
     "CL", "es", "mass", False),
    ("rosa", "DNI", "90000017", "Rosa", "Quispe Huaman", "1983-09-12",
     "PE", "es", "mass", False),
    ("diego", "DNI", "90000025", "Diego", "Flores Salazar", "1990-04-05",
     "PE", "es", "premium", False),
    ("camila", "CC", "1999000123", "Camila", "Restrepo Gil", "1988-12-19",
     "CO", "en", "preferred", False),
    ("andres", "CC", "1999000456", "Andres", "Mejia Ospina", "1975-06-27",
     "CO", "es", "mass", False),
    ("sofia", "CURP", SOFIA_CURP + curp_check_digit(SOFIA_CURP), "Sofia", "Robles Garcia",
     "1990-05-14", "MX", "es", "preferred", False),
]  # fmt: skip

# customer key, account type, available balance
ACCOUNTS = [
    ("marta", "checking", 1284500), ("marta", "savings", 3150000),
    ("pedro", "checking", 742300), ("carolina", "sight", 96400),
    ("jorge", "sight", 412000), ("lucia", "sight", 58200),
    ("rosa", "savings", 3120.50), ("diego", "checking", 18940.00),
    ("camila", "checking", 4875000), ("andres", "savings", 1260000),
    ("sofia", "checking", 23480.75),
]  # fmt: skip

# customer key, last four digits, brand, type, status, daily limit
CARDS = [
    ("marta", "4821", "visa", "credit", "active", 1500000),
    ("pedro", "7730", "mastercard", "credit", "active", 1200000),
    ("carolina", "1164", "visa", "credit", "active", 600000),
    ("jorge", "9052", "visa", "debit", "active", 300000),
    ("lucia", "3378", "mastercard", "debit", "blocked_temporary", 300000),
    ("rosa", "6410", "visa", "debit", "active", 2000),
    ("diego", "2295", "mastercard", "credit", "active", 12000),
    ("camila", "8807", "visa", "credit", "active", 6000000),
    ("andres", "5143", "mastercard", "debit", "active", 2500000),
    ("sofia", "7026", "visa", "credit", "active", 40000),
]  # fmt: skip


def country_of(key: str) -> str:
    """Return the country code of the seed customer with this key."""
    return next(person[6] for person in PEOPLE if person[0] == key)


def build_customers(demo_email: str = "") -> list[dict]:
    """Build the customer rows. The golden-path customer gets `demo_email` when given."""
    rows = []
    for key, doc_type, doc_number, first, last, birth, country, language, segment, weak in PEOPLE:
        email = f"{key}.{last.split()[0].lower()}@example.com"
        if key == "marta" and demo_email:
            email = demo_email
        rows.append({
            "id": seed_id(f"customer/{key}"), "document_type": doc_type,
            "document_number": doc_number, "first_name": first, "last_name": last,
            "birth_date": birth, "email": email, "phone": None, "telegram_chat_id": None,
            "country": country, "preferred_language": language, "segment": segment,
            "is_vulnerable": weak,
        })  # fmt: skip
    return rows


def build_accounts(now_iso: str) -> list[dict]:
    """Build the account rows, in each customer's local currency."""
    return [
        {"id": seed_id(f"account/{key}/{kind}"), "customer_id": seed_id(f"customer/{key}"),
         "type": kind, "currency": CURRENCY_BY_COUNTRY[country_of(key)],
         "available_balance": balance, "updated_at": now_iso}
        for key, kind, balance in ACCOUNTS
    ]  # fmt: skip


def build_cards(blocked_at_iso: str) -> list[dict]:
    """Build the card rows. A card seeded as blocked gets a block time and reason."""
    rows = []
    for key, last4, brand, kind, status, limit in CARDS:
        blocked = status != "active"
        rows.append({
            "id": seed_id(f"card/{key}"), "customer_id": seed_id(f"customer/{key}"),
            "last4": last4, "brand": brand, "type": kind, "status": status,
            "daily_limit": limit, "blocked_at": blocked_at_iso if blocked else None,
            "block_reason": "customer_request" if blocked else None,
        })  # fmt: skip
    return rows
