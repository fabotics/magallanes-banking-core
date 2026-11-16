"""The wording of the insurance contract, in Spanish.

Same pages and same clauses, in the same order, as `contract_en.py`.
`{premium}`, `{card}` and `{limit}` are filled in for each customer.
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
        "Cotización N°",
        "Límite por evento",
    ],  # fmt: skip
    "term": "Mensual, con renovación automática. Comienza el día de la firma.",
    "any_card": "tarjeta del asegurado",
    "products": {},
    "cover": {
        "CARD_FRAUD": [
            "Robo de efectivo después de un giro: se repone el dinero que le roben al "
            "asegurado, con violencia o intimidación, dentro de las dos horas siguientes a un "
            "giro en cajero automático hecho con la tarjeta.",
            "Dinero de emergencia: si la tarjeta queda bloqueada por robo, hurto o extravío, "
            "se paga al asegurado una suma para gastos urgentes mientras llega la tarjeta de "
            "reemplazo, hasta el 20% del límite por evento.",
            "Reposición de documentos y llaves: se reembolsa el costo de reponer la cédula de "
            "identidad, la licencia de conducir, el pasaporte y las llaves robados o "
            "extraviados junto con la tarjeta.",
            "Asistencia: orientación telefónica las 24 horas para bloquear documentos, hacer "
            "la denuncia y presentar el reclamo ante el banco.",
            "Límite: hasta {limit} por evento, con un máximo de dos eventos por año de vigencia.",
            "Lo que esta póliza no reemplaza: anular o devolver las operaciones que el "
            "asegurado no autorizó es una obligación que la ley pone a cargo del emisor de la "
            "tarjeta, sin costo. Esta póliza no cubre ese riesgo y no se necesita para ejercer "
            "ese derecho.",
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
            "Las operaciones no autorizadas hechas con la tarjeta, que la ley pone a cargo del "
            "emisor.",
            "Robo de efectivo sin violencia ni intimidación, o después de las dos horas "
            "siguientes al giro.",
            "Hechos que no se denuncien a la policía dentro de las 48 horas siguientes.",
            "Hechos causados con dolo o culpa grave del asegurado.",
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
