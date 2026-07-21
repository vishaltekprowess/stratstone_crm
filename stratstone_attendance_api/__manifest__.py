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
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
