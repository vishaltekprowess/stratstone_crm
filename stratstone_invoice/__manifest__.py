# -*- coding: utf-8 -*-
{
    'name': "Stratstone Invoice",

    'summary': "Executive Custom Invoice Format for Stratstone",

    'description': """
        Professional and modern invoice format for Stratstone.
        Features:
        - Sleek executive aesthetic with Deep Midnight Navy (#0f172a) and Warm Gold (#c59b27) accents.
        - High-clarity typography with clean metadata tiles (Invoice Date, Due Date, Reference, Place of Supply).
        - Distinctive Billed To and Shipped To / Dispatch cards.
        - Structured line items table with Serial No, Description, HSN/SAC, Quantity & UoM, Unit Price, and Subtotal.
        - Amount in Words with Indian Rupee formatting support.
        - Financial summary card with dynamic tax breakdown (CGST, SGST, IGST), rounding, and Grand Total.
        - Payment reconciliation history and highlighted Amount Due.
        - Configurable Bank & Remittance instructions card.
        - Clean signature and corporate acknowledgement block.
        - Custom A4 paperformat optimized for both digital and print output.
    """,

    'author': "Tekprowess",
    'website': 'https://www.tekprowess.com',

    'category': 'Accounting/Invoicing',
    'version': '18.0.1.0.0',

    'depends': ['base', 'web', 'account', 'l10n_in'],

    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_bank_views.xml',
        'report/paperformat_a4.xml',
        'report/custom_layout.xml',
        'report/report_invoice.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'stratstone_invoice/static/src/scss/invoice_style.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
