"""Seed rows for the merchant registry: the businesses behind merchant tax IDs.

A card statement shows a cryptic descriptor and sometimes a tax ID. This
registry is what turns that tax ID into a business a customer can recognize.
All businesses are invented.
"""

from seed.helpers import rut
from seed.movements import RESTAURANT_TAX_ID

# tax ID, legal name, trade name, activity, address, commune
MERCHANTS = [
    (RESTAURANT_TAX_ID, "Inversiones Gastronomicas Providencia SpA", "Restaurante El Mirador",
     "Restaurant", "Avenida Los Aromos 245", "Providencia"),
    (rut(66245810, hyphen=True), "Comercial Don Lucho Limitada", "Supermercado Don Lucho",
     "Supermarket", "Calle Las Acacias 1020", "Nunoa"),
    (rut(66530977, hyphen=True), "Farmacias Salud Total SA", "Farmacia Salud Total",
     "Pharmacy", "Avenida Los Aromos 310", "Providencia"),
    (rut(67102345, hyphen=True), "Combustibles Ruta Sur SpA", "Estacion de Servicio Ruta 5 Sur",
     "Fuel station", "Ruta 5 Sur kilometro 32", "San Bernardo"),
    (rut(67480122, hyphen=True), "Tiendas Alameda SA", "Tienda Alameda",
     "Department store", "Avenida Central 890", "Santiago"),
]  # fmt: skip


def build_registry() -> list[dict]:
    """Build the registry rows."""
    return [
        {"tax_id": tax_id, "legal_name": legal, "trade_name": trade, "activity": activity,
         "address": address, "commune": commune, "country": "CL"}
        for tax_id, legal, trade, activity, address, commune in MERCHANTS
    ]  # fmt: skip
