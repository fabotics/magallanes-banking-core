"""The wording of each insurance contract, and the checks on the customer's signature.

The catalog row carries the name, the premium and a one line summary. The
clauses a customer signs are longer, so they live here, one list per product.
A product without its own clauses falls back to the catalog summary.
"""

import unicodedata

from app.db import Row

INSURER = "Magallanes Seguros Generales S.A."
PAGES = 4

COVER = {
    "CARD_FRAUD": [
        "Cargos no autorizados: se reembolsan los cargos hechos con la tarjeta sin el "
        "consentimiento del asegurado, por robo, hurto, extravío, clonación o uso fraudulento "
        "de sus datos, en comercios presenciales o electrónicos.",
        "Reposición de la tarjeta: se cubre el costo de emitir y despachar la tarjeta de "
        "reemplazo.",
        "Límite: hasta $3.000.000 por evento, con un máximo de dos eventos por año de vigencia.",
        "Aviso: el asegurado debe avisar al banco dentro de los 30 días siguientes a la fecha "
        "del cargo que desconoce.",
    ],
    "UNEMPLOYMENT": [
        "Cesantía involuntaria: se paga el pago mínimo de la tarjeta por hasta seis meses "
        "mientras el asegurado esté sin empleo.",
        "Carencia: la cobertura comienza 60 días después de la firma.",
    ],
    "PURCHASE": [
        "Robo o daño accidental de las compras hechas con la tarjeta, durante 90 días desde "
        "la fecha de compra.",
        "Límite: hasta el valor de compra del bien, con un máximo de $1.000.000 por año.",
    ],
}

EXCLUSIONS = {
    "CARD_FRAUD": [
        "Cargos hechos por el asegurado, o por una persona a quien entregó voluntariamente "
        "su tarjeta o sus claves.",
        "Cargos anteriores a la fecha de inicio de la vigencia.",
        "Hechos causados con dolo o culpa grave del asegurado.",
        "Pérdidas indirectas, intereses y lucro cesante.",
    ],
    "UNEMPLOYMENT": [
        "Renuncia voluntaria y término de un contrato a plazo fijo en la fecha pactada.",
        "Trabajadores independientes y personas sin contrato de trabajo.",
        "Despidos notificados antes de la fecha de inicio de la vigencia.",
    ],
    "PURCHASE": [
        "Desgaste por uso normal y defectos de fabricación.",
        "Extravío del bien sin que exista robo.",
        "Vehículos motorizados, dinero, joyas y animales.",
    ],
}

GENERAL_EXCLUSION = "Hechos ocurridos fuera de la vigencia de la póliza."


def clauses(product: Row) -> tuple[list[str], list[str]]:
    """Return the cover clauses and the exclusions for a product."""
    cover = COVER.get(product["code"], [product["coverage_summary"]])
    exclusions = EXCLUSIONS.get(product["code"], [])
    return cover, [*exclusions, GENERAL_EXCLUSION]


def initials(customer: Row) -> str:
    """Return the first letter of the first name and of the first surname: `MR`."""
    return (customer["first_name"][:1] + customer["last_name"][:1]).upper()


def plain(text: str) -> str:
    """Lower case, no accents, single spaces: how two spellings of a name are compared."""
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(without_accents.lower().split())


def name_matches(typed: str, customer: Row) -> bool:
    """Accept the customer's full name as the signature, whatever the case or accents."""
    return plain(typed) == plain(f"{customer['first_name']} {customer['last_name']}")
