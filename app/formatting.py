"""How amounts and dates are written for the customer, in messages, emails and pages."""

from datetime import date

MONTHS = {
    "es": (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ),
    "en": (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ),
}  # fmt: skip


def money(amount: float, currency: str, language: str = "es") -> str:
    """Write an amount: `$2.990` the Chilean way, `CLP 2,990` for an English reader."""
    whole = currency == "CLP"
    if whole and language == "es":
        return "$" + f"{round(float(amount)):,}".replace(",", ".")
    return f"{currency} {round(float(amount)):,}" if whole else f"{currency} {float(amount):,.2f}"


def long_date(day: date, language: str = "es") -> str:
    """Write a date in words: `16 de noviembre de 2026`, or `16 November 2026`."""
    month = MONTHS[language][day.month - 1]
    return (
        f"{day.day} {month} {day.year}"
        if language == "en"
        else f"{day.day} de {month} de {day.year}"
    )


def document(document_type: str, number: str) -> str:
    """Write a document number the way it is printed: `31.415.926-8` for a Chilean RUT."""
    if document_type != "RUT":
        return number
    body, check_digit = number[:-1], number[-1]
    return f"{int(body):,}".replace(",", ".") + f"-{check_digit}"


def card_label(card: dict, language: str = "es") -> str:
    """Describe a card without its number: `tarjeta Visa de crédito terminada en 4821`."""
    brand = card["brand"].capitalize()
    if language == "en":
        return f"{brand} {card['type']} card ending in {card['last4']}"
    kind = "crédito" if card["type"] == "credit" else "débito"
    return f"tarjeta {brand} de {kind} terminada en {card['last4']}"
