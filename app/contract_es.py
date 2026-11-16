"""The wording of the insurance contract, in Spanish.

Same pages and same clauses, in the same order, as `contract_en.py`.
`{premium}` and `{card}` are filled in for each customer.
"""

TEXT = {
    "titles": {
        "particulars": "Propuesta de seguro",
        "particulars_line": "Condiciones particulares.",
        "cover": "Coberturas",
        "cover_intro": "La compañía aseguradora cubre al asegurado, durante la vigencia de la "
        "póliza, en los términos siguientes.",
        "exclusions": "Exclusiones",
        "exclusions_intro": "Esta póliza no cubre:",
        "general": "Condiciones generales",
    },
    "labels": [
        "Propuesta N°",
        "Fecha de emisión",
        "Compañía aseguradora",
        "Contratante e intermediario",
        "Asegurado",
        "Documento",
        "Producto",
        "Prima mensual",
        "Medio de pago",
        "Vigencia",
    ],  # fmt: skip
    "term": "Mensual, con renovación automática. Comienza el día de la firma.",
    "any_card": "tarjeta del asegurado",
    "products": {},
    "cover": {
        "CARD_FRAUD": [
            "Cargos no autorizados: se reembolsan los cargos hechos con la tarjeta sin el "
            "consentimiento del asegurado, por robo, hurto, extravío, clonación o uso "
            "fraudulento de sus datos, en comercios presenciales o electrónicos.",
            "Reposición de la tarjeta: se cubre el costo de emitir y despachar la tarjeta de "
            "reemplazo.",
            "Límite: hasta $3.000.000 por evento, con un máximo de dos eventos por año de "
            "vigencia.",
            "Aviso: el asegurado debe avisar al banco dentro de los 30 días siguientes a la "
            "fecha del cargo que desconoce.",
        ],
        "UNEMPLOYMENT": [
            "Cesantía involuntaria: se paga el pago mínimo de la tarjeta por hasta seis meses "
            "mientras el asegurado esté sin empleo.",
            "Carencia: la cobertura comienza 60 días después de la firma.",
        ],
        "PURCHASE": [
            "Robo o daño accidental de las compras hechas con la tarjeta, durante 90 días "
            "desde la fecha de compra.",
            "Límite: hasta el valor de compra del bien, con un máximo de $1.000.000 por año.",
        ],
    },
    "exclusions": {
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
    },
    "general_exclusion": "Hechos ocurridos fuera de la vigencia de la póliza.",
    "general": [
        (
            "Prima y forma de pago",
            "La prima de {premium} se carga cada mes a la {card}. El "
            "primer cargo se hace en la fecha de la firma.",
        ),
        (
            "Derecho de retracto",
            "El asegurado puede dejar sin efecto este contrato dentro de "
            "los 10 días siguientes a la firma, sin expresar causa. La prima pagada se devuelve "
            "completa.",
        ),
        (
            "Término anticipado",
            "El asegurado puede dar de baja el seguro en cualquier momento, "
            "sin costo, desde la app o por teléfono. El cobro termina desde el período mensual "
            "siguiente.",
        ),
        (
            "Denuncia de siniestros",
            "Los siniestros se denuncian por los canales de atención "
            "del banco. La compañía aseguradora responde dentro de 10 días hábiles desde que "
            "recibe los antecedentes.",
        ),
        (
            "Datos personales",
            "Los datos del asegurado se usan solo para administrar esta "
            "póliza y no se entregan a terceros con otro fin.",
        ),
        (
            "Firma electrónica",
            "El asegurado declara que leyó este documento y que su firma "
            "electrónica en la app del banco tiene el mismo valor que su firma manuscrita.",
        ),
    ],  # fmt: skip
}
