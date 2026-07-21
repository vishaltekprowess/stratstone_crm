# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

import pytz
from datetime import datetime

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

DEFAULT_CHECKOUT_HOUR = 18  # 18:00 in employee's timezone
DEFAULT_CHECKOUT_MINUTE = 0


class HrAttendanceInherit(models.Model):
    _inherit = 'hr.attendance'

    location_ids = fields.One2many(
        'attendance.location',
        'attendance_id',
        string='Location Data',
    )
    checkin_address = fields.Char(
        string='Check-In Address',
        help='Address recorded at check-in from the mobile app',
    )
    checkout_address = fields.Char(
        string='Check-Out Address',
        help='Address recorded at check-out from the mobile app',
    )

    @api.model
    def _cron_auto_check_out_fixed(self):
        """Auto check-out employees who forgot to check out.

        Sets check_out to 18:00 in the employee's timezone on the same day
        as check_in. Only processes attendances where check_in is before
        today (i.e., the employee forgot to check out yesterday or earlier).
        """
        now_utc = fields.Datetime.now()

        # Find all open attendances (no check_out)
        open_attendances = self.search([
            ('check_out', '=', False),
        ])

        if not open_attendances:
            _logger.info('Auto check-out cron: no open attendances found.')
            return

        for attendance in open_attendances:
            employee = attendance.employee_id
            tz_name = employee._get_tz() if hasattr(employee, '_get_tz') else (employee.tz or 'UTC')
            employee_tz = pytz.timezone(tz_name)

            # Convert check_in to employee timezone
            check_in_utc = pytz.utc.localize(attendance.check_in)
            check_in_local = check_in_utc.astimezone(employee_tz)

            # Current time in employee timezone
            now_local = pytz.utc.localize(now_utc).astimezone(employee_tz)

            # Only auto-checkout if the check-in date is before today in employee's TZ
            if check_in_local.date() >= now_local.date():
                continue

            # Set check_out to 18:00 on the check-in day in employee's timezone
            checkout_local = check_in_local.replace(
                hour=DEFAULT_CHECKOUT_HOUR,
                minute=DEFAULT_CHECKOUT_MINUTE,
                second=0,
                microsecond=0,
            )

            # If check-in was after 18:00, set checkout to check_in + 1 second
            # to avoid check_out < check_in validation error
            if checkout_local <= check_in_local:
                checkout_local = check_in_local.replace(
                    hour=23, minute=59, second=59, microsecond=0,
                )

            # Convert back to UTC naive for Odoo
            checkout_utc = checkout_local.astimezone(pytz.utc).replace(tzinfo=None)

            try:
                attendance.sudo().write({
                    'check_out': checkout_utc,
                    'out_mode': 'auto_check_out',
                    'checkout_address': _('Auto check-out at %s:00') % DEFAULT_CHECKOUT_HOUR,
                })

                # Create a location record marking auto-checkout
                self.env['attendance.location'].sudo().create({
                    'attendance_id': attendance.id,
                    'employee_id': employee.id,
                    'location_type': 'check_out',
                    'latitude': 0.0,
                    'longitude': 0.0,
                    'accuracy': 0.0,
                    'address': _('Auto check-out (no GPS data)'),
                    'is_auto_checkout': True,
                })

                # Post chatter message
                attendance.sudo().message_post(
                    body=_(
                        'This attendance was automatically checked out at '
                        '%s:00 because the employee did not check out.',
                        DEFAULT_CHECKOUT_HOUR,
                    ),
                )

                _logger.info(
                    'Auto check-out: employee %s (ID %s), attendance %s -> checkout at %s',
                    employee.name, employee.id, attendance.id, checkout_utc,
                )

            except Exception as e:
                _logger.error(
                    'Auto check-out failed for attendance %s (employee %s): %s',
                    attendance.id, employee.name, str(e),
                )
                continue
