# -*- coding: utf-8 -*-
{
    'name': "Tekprowess Dashboard",
    'summary': "Comprehensive Dashboards for Odoo apps",
    'description': """
        Tekprowess Dashboards Module
        ================================
        
        Standalone dashboard module that automatically detects installed apps
        and provides graphical dashboards for:
        * CRM (if crm is installed)
        * Manufacturing (if mrp is installed)
        * Sales (if sale is installed)
        * Purchase (if purchase is installed)
        * Accounting (if account is installed)
        * Inventory (if stock is installed)
    """,
    'author': "Tekprowess",
    'website': 'https://www.tekprowess.com',
    'category': 'Productivity',
    'version': '18.0.1.0.0',
    'depends': [
        'base',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'data/create_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'tekprowess_dashboard/static/src/js/manufacturing_dashboard.js',
            'tekprowess_dashboard/static/src/xml/manufacturing_dashboard.xml',
            'tekprowess_dashboard/static/src/css/manufacturing_dashboard.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
