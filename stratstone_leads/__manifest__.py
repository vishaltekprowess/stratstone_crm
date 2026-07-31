{
    'name': 'Stratstone Leads',
    'version': '18.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Meta Lead Ads sync and Lead creation API for Odoo CRM',
    'description': """
        Periodically fetches leads from Meta Lead Ads (Facebook / Instagram)
        via the Graph API and creates CRM opportunities in Odoo.

        Also provides a public POST API endpoint (/api/leads) for creating
        CRM leads from external sources (website forms, landing pages, etc.).

        Features:
        - Automated cron-based Meta Lead Ads sync every 10 minutes
        - Manual sync button in Settings
        - Date-range fetch wizard for historical imports
        - Deduplication via unique Meta Lead ID
        - All form field data captured in lead description
        - Public POST /api/leads endpoint for external lead capture
    """,
    'author': 'Stratstone',
    'depends': ['crm', 'utm'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'wizard/meta_leadads_fetch_wizard.xml',
        'wizard/res_config_settings.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
