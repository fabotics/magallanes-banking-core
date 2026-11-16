"""Small helpers for building seed rows: stable ids and national ID check digits."""

import uuid

CURP_ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"


def seed_id(name: str) -> str:
    """Return the same UUID for the same name every time.

    Stable ids mean a reseed keeps every row's id, and tests can look rows up by name.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"magallanes-seed/{name}"))


def rut_check_digit(number: int) -> str:
    """Compute the check digit of a Chilean RUT (modulo 11).

    Digits are multiplied right to left by 2, 3, 4, 5, 6, 7, then 2 again.
    """
    total = 0
    factor = 2
    for digit in reversed(str(number)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - total % 11
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def rut(number: int, hyphen: bool = False) -> str:
    """Return a RUT with its check digit: `31415926K`, or `31415926-K` with a hyphen."""
    separator = "-" if hyphen else ""
    return f"{number}{separator}{rut_check_digit(number)}"


def curp_check_digit(first_17: str) -> str:
    """Compute the 18th character of a Mexican CURP from its first 17."""
    total = 0
    for position, character in enumerate(first_17):
        total += CURP_ALPHABET.index(character) * (18 - position)
    return str((10 - total % 10) % 10)
