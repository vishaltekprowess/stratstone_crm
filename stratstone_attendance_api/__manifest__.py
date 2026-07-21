# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Stratstone Attendance API',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'REST APIs for employee check-in/check-out with GPS location tracking',
    'description': """
        Provides JSON API endpoints for employee attendance management:
        - Check-in with GPS location
        - Check-out with GPS location
        - Attendance status query
        - Attendance history with location data
        - Auto check-out for missed checkouts (default 18:00)
    """,
    'author': 'Stratstone',
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'views/attendance_location_views.xml',
        'views/res_config_settings_views.xml',
        'views/download_app_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stratstone_attendance_api/static/src/user_menu/user_menu_items.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
