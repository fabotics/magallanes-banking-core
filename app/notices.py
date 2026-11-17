"""What the bank writes to the customer: chat messages and emails, in Spanish or English.

The language is the one the call is held in. When the caller does not say,
it is the language the bank has on file for the customer. Links in a message
carry the same language, so the page opens in the language of the message.
"""

from app.contracts import product_wording
from app.db import Row
from app.formatting import money

DEFAULT = "es"

WORDS = {
    "es": {
        "confirm": "Alguien en una llamada con Banco Magallanes pide confirmar su identidad. "
        "Código {code}\n\nAbra la app para aprobar o rechazar: {link}\n"
        "Si usted no está en una llamada con el banco, rechace la solicitud.",
        "proposal": "Su propuesta de {name} está lista para firmar.\n"
        "Prima mensual: {premium}\n\nRevise y firme en la app: {link}\n"
        "Nada queda contratado hasta que usted firme.",
        "policy": "Su seguro {name} quedó contratado.\n\nPóliza: {number}\n"
        "Vigente desde: {start}\nPrima mensual: {premium}\n\n"
        "Puede darlo de baja en cualquier momento desde la app.",
        "summary": "Resumen de su conversación con Maggie, la asistente virtual:",
        "premium": "Prima mensual",
        "sign_link": "Revisar y firmar la propuesta",
        "unsigned": "Nada queda contratado hasta que usted firme.",
        "policy_subject": "Banco Magallanes: su póliza {number}",
        "policy_lead": "Su seguro <strong>{name}</strong> quedó contratado.",
        "policy_number": "Póliza",
        "policy_start": "Vigente desde",
        "cancel": "Puede darlo de baja en cualquier momento desde la app.",
    },
    "en": {
        "confirm": "Someone on a call with Banco Magallanes is asking to confirm your identity. "
        "Code {code}\n\nOpen the app to approve or reject: {link}\n"
        "If you are not on a call with the bank, reject the request.",
        "proposal": "Your {name} proposal is ready to sign.\n"
        "Monthly premium: {premium}\n\nReview and sign in the app: {link}\n"
        "Nothing is taken out until you sign.",
        "policy": "Your {name} insurance is now active.\n\nPolicy: {number}\n"
        "In force from: {start}\nMonthly premium: {premium}\n\n"
        "You can cancel it at any time from the app.",
        "summary": "Summary of your conversation with Maggie, the virtual assistant:",
        "premium": "Monthly premium",
        "sign_link": "Review and sign the proposal",
        "unsigned": "Nothing is taken out until you sign.",
        "policy_subject": "Banco Magallanes: your policy {number}",
        "policy_lead": "Your <strong>{name}</strong> insurance is now active.",
        "policy_number": "Policy",
        "policy_start": "In force from",
        "cancel": "You can cancel it at any time from the app.",
    },
}


def language_for(customer: Row, asked: str | None = None) -> str:
    """Return the language to write in: the one asked for, else the customer's, else Spanish."""
    for choice in (asked, customer.get("preferred_language")):
        if choice in WORDS:
            return choice
    return DEFAULT


def chat(language: str, key: str, **values: str) -> str:
    """Write one chat message under the bank's name."""
    return "Banco Magallanes\n" + WORDS[language][key].format(**values)


def priced(product: Row, language: str) -> tuple[str, str, str]:
    """Return the product's name, cover line and premium as this language writes them."""
    name, cover = product_wording(product, language)
    return name, cover, money(product["monthly_premium"], product["currency"], language)


def proposal_email(product: Row, signing_url: str | None, language: str = DEFAULT) -> str:
    """Write the email body: product details, plus the signing link when there is one."""
    words = WORDS[language]
    name, cover, premium = priced(product, language)
    html = f"<p><strong>{name}</strong></p><p>{cover}</p><p>{words['premium']}: {premium}.</p>"
    if signing_url:
        html += f'<p><a href="{signing_url}">{words["sign_link"]}</a></p><p>{words["unsigned"]}</p>'
    return html


def policy_email(product: Row, policy: Row, start: str, language: str = DEFAULT) -> str:
    """Write the confirmation the customer keeps once the proposal is signed."""
    words = WORDS[language]
    name, cover, premium = priced(product, language)
    return (
        f"<p>{words['policy_lead'].format(name=name)}</p>"
        f"<p>{words['policy_number']}: {policy['policy_number']}<br>"
        f"{words['policy_start']}: {start}<br>"
        f"{words['premium']}: {premium}</p>"
        f"<p>{cover}</p><p>{words['cancel']}</p>"
    )
