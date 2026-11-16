"""The wording of the insurance contract, in English.

Same pages and same clauses, in the same order, as `contract_es.py`.
`{premium}`, `{card}` and `{limit}` are filled in for each customer.
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
        "Quote No.",
        "Limit per event",
    ],  # fmt: skip
    "term": "Monthly, renewed automatically. It starts on the day of signature.",
    "any_card": "the insured's card",
    "products": {
        "CARD_FRAUD": (
            "Card protection and assistance",
            "Covers what the law does not put on the bank: cash stolen after a withdrawal, "
            "emergency money while the replacement card arrives, replacing stolen documents, "
            "and help with the paperwork.",
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
            "Cash stolen after a withdrawal: money taken from the insured by force or threat "
            "within two hours of a cash machine withdrawal made with the card is replaced.",
            "Emergency money: if the card is blocked after robbery, theft or loss, the insured "
            "is paid a sum for urgent expenses while the replacement card arrives, up to 20% "
            "of the limit per event.",
            "Documents and keys: the cost of replacing the identity card, the driving licence, "
            "the passport and the keys stolen or lost together with the card is refunded.",
            "Assistance: phone guidance, 24 hours a day, to block documents, report to the "
            "police and file the claim with the bank.",
            "Limit: up to {limit} per event, and at most two events per policy year.",
            "What this policy does not replace: cancelling or refunding operations the insured "
            "did not authorize is an obligation the law places on the card issuer, at no "
            "cost. This policy does not cover that risk and is not needed to use that right.",
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
            "Unauthorized operations made with the card, which the law places on the issuer.",
            "Cash stolen without force or threat, or more than two hours after the withdrawal.",
            "Events not reported to the police within 48 hours.",
            "Events caused by wilful misconduct or gross negligence of the insured.",
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
