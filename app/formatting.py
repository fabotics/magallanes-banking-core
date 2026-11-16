"""How amounts and dates are written for the customer, in messages, emails and pages."""

from datetime import date

MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def money(amount: float, currency: str) -> str:
    """Write an amount the local way: `$2.990` for Chilean pesos, `PEN 12.50` otherwise."""
    if currency == "CLP":
        return "$" + f"{round(float(amount)):,}".replace(",", ".")
    return f"{currency} {float(amount):,.2f}"


def long_date(day: date) -> str:
    """Write a date in words: `16 de noviembre de 2026`."""
    return f"{day.day} de {MONTHS[day.month - 1]} de {day.year}"


def document(document_type: str, number: str) -> str:
    """Write a document number the way it is printed: `31.415.926-8` for a Chilean RUT."""
    if document_type != "RUT":
        return number
    body, check_digit = number[:-1], number[-1]
    return f"{int(body):,}".replace(",", ".") + f"-{check_digit}"


def card_label(card: dict) -> str:
    """Describe a card without its number: `tarjeta Visa de crédito terminada en 4821`."""
    kind = "crédito" if card["type"] == "credit" else "débito"
    return f"tarjeta {card['brand'].capitalize()} de {kind} terminada en {card['last4']}"
