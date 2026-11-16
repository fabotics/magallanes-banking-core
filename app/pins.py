"""The PIN of the bank's app: stored as a slow salted hash, never as digits.

A four digit PIN has only 10,000 values, so the hash alone does not protect
it. The lock after three wrong attempts does. The hash still keeps PINs out
of database dumps, logs and backups.
"""

import hashlib
import secrets

ITERATIONS = 100_000


def hash_pin(pin: str, salt: str) -> str:
    """Return the PBKDF2 hash of a PIN. The salt is the customer's id."""
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), ITERATIONS)
    return digest.hex()


def pin_matches(pin: str, salt: str, stored_hash: str | None) -> bool:
    """Compare a typed PIN with the stored hash, in constant time."""
    if not stored_hash:
        return False
    return secrets.compare_digest(hash_pin(pin, salt), stored_hash)
