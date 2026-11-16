"""The wording of the insurance contract, in English.

Same pages and same clauses, in the same order, as `contract_es.py`.
`{premium}` and `{card}` are filled in for each customer.
"""

TEXT = {
    "titles": {
        "particulars": "Insurance proposal",
        "particulars_line": "Schedule.",
        "cover": "Cover",
        "cover_intro": "The insurer covers the insured, while the policy is in force, on the "
        "following terms.",
        "exclusions": "Exclusions",
        "exclusions_intro": "This policy does not cover:",
        "general": "General conditions",
    },
    "labels": [
        "Proposal No.",
        "Date of issue",
        "Insurer",
        "Policyholder and intermediary",
        "Insured",
        "Document",
        "Product",
        "Monthly premium",
        "Payment method",
        "Term",
    ],  # fmt: skip
    "term": "Monthly, renewed automatically. It starts on the day of signature.",
    "any_card": "the insured's card",
    "products": {
        "CARD_FRAUD": (
            "Card fraud protection",
            "Refunds unauthorized charges made with the card and covers the replacement card.",
        ),
        "UNEMPLOYMENT": (
            "Unemployment protection",
            "Pays the card's minimum payment for up to six months if the insured loses their job.",
        ),
        "PURCHASE": (
            "Purchase protection",
            "Covers theft or accidental damage of purchases made with the card for 90 days.",
        ),
    },
    "cover": {
        "CARD_FRAUD": [
            "Unauthorized charges: charges made with the card without the insured's consent "
            "are refunded, whether through robbery, theft, loss, cloning or fraudulent use of "
            "its details, in shops or online.",
            "Card replacement: the cost of issuing and delivering the replacement card is covered.",
            "Limit: up to CLP 3,000,000 per event, and at most two events per policy year.",
            "Notice: the insured must notify the bank within 30 days of the date of the charge "
            "they do not recognize.",
        ],
        "UNEMPLOYMENT": [
            "Involuntary unemployment: the card's minimum payment is paid for up to six months "
            "while the insured is out of work.",
            "Waiting period: cover starts 60 days after signature.",
        ],
        "PURCHASE": [
            "Theft or accidental damage of purchases made with the card, for 90 days from the "
            "date of purchase.",
            "Limit: up to the purchase price of the item, and at most CLP 1,000,000 per year.",
        ],
    },
    "exclusions": {
        "CARD_FRAUD": [
            "Charges made by the insured, or by a person to whom they willingly gave their "
            "card or their codes.",
            "Charges made before the date the policy came into force.",
            "Events caused by wilful misconduct or gross negligence of the insured.",
            "Indirect losses, interest and loss of profit.",
        ],
        "UNEMPLOYMENT": [
            "Resignation, and the end of a fixed term contract on the agreed date.",
            "Self-employed workers and people without an employment contract.",
            "Dismissals notified before the date the policy came into force.",
        ],
        "PURCHASE": [
            "Normal wear and tear, and manufacturing defects.",
            "Loss of the item without theft.",
            "Motor vehicles, cash, jewellery and animals.",
        ],
    },
    "general_exclusion": "Events that happen while the policy is not in force.",
    "general": [
        (
            "Premium and payment",
            "The premium of {premium} is charged every month to the "
            "{card}. The first charge is made on the date of signature.",
        ),
        (
            "Right of withdrawal",
            "The insured may cancel this contract within 10 days of "
            "signature, without giving a reason. The premium paid is refunded in full.",
        ),
        (
            "Early termination",
            "The insured may cancel the insurance at any time, at no cost, "
            "in the app or by phone. Charges stop from the next monthly period.",
        ),
        (
            "Claims",
            "Claims are reported through the bank's service channels. The insurer "
            "answers within 10 business days of receiving the supporting information.",
        ),
        (
            "Personal data",
            "The insured's data is used only to administer this policy and is "
            "not given to third parties for any other purpose.",
        ),
        (
            "Electronic signature",
            "The insured declares that they have read this document and "
            "that their electronic signature in the bank's app has the same value as their "
            "handwritten signature.",
        ),
    ],  # fmt: skip
}
