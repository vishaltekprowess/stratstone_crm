# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    playstore_url = fields.Char(
        string="Play Store URL",
        config_parameter="stratstone_attendance_api.playstore_url",
        help="Google Play Store URL for Stratstone Attendance Mobile App",
    )
    appstore_url = fields.Char(
        string="Apple Store URL",
        config_parameter="stratstone_attendance_api.appstore_url",
        help="Apple App Store URL for Stratstone Attendance Mobile App",
    )
