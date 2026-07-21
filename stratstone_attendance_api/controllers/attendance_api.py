# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import datetime, timedelta

from odoo import http, fields, _
from odoo.http import request
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class AttendanceAPIController(http.Controller):
    """REST-style JSON API for employee attendance with GPS location tracking.

    All endpoints use Odoo session authentication (auth='user').
    The employee is auto-detected from the logged-in user's linked employee record.
    """

    # -------------------------------------------------------------------------
    # Login (no db name required from frontend)
    # -------------------------------------------------------------------------

    @http.route('/api/attendance/login', type='json', auth='none', methods=['POST'], csrf=False)
    def api_login(self, login=None, password=None):
        """Authenticate and create a session. Database is auto-detected.

        Request body (JSON-RPC params):
            login    (str): Username or email
            password (str): Password

        The database is resolved automatically from:
          1. The Odoo config (db_name / --database flag)
          2. The only available database (if there's exactly one)
        """
        if not login or not password:
            return {
                'status': 'error',
                'message': 'Both "login" and "password" are required.',
            }

        # --- Auto-detect database ---
        db = self._get_db()
        if not db:
            return {
                'status': 'error',
                'message': 'Could not determine the database. '
                           'Please contact your administrator.',
            }

        # --- Authenticate ---
        try:
            credential = {
                'type': 'password',
                'login': login,
                'password': password,
            }
            auth_info = request.session.authenticate(db, credential)
            uid = auth_info.get('uid') if isinstance(auth_info, dict) else auth_info
        except Exception as e:
            _logger.warning('Login failed for %s: %s', login, e)
            return {
                'status': 'error',
                'message': f'{e}',
            }

        if not uid:
            return {
                'status': 'error',
                'message': 'Invalid credentials.',
            }

        # --- Build response ---
        env = request.env
        user = env['res.users'].sudo().browse(uid)
        employee = user.employee_id

        result = {
            'status': 'success',
            'message': 'Logged in successfully.',
            'session_id': request.session.sid,
            'uid': uid,
            'user_name': user.name,
        }

        if employee:
            result.update({
                'employee_id': employee.id,
                'employee_name': employee.name,
                'attendance_state': employee.attendance_state,
            })
        else:
            result['warning'] = 'No employee record linked to this user.'

        return result

    @staticmethod
    def _get_db():
        """Auto-detect the database name.

        Priority:
          1. Odoo config db_name (set via -d flag or config file)
          2. Single available database on the server
        """
        from odoo.tools import config
        import odoo.service.db as db_service

        # 1. Config database
        db_name = config.get('db_name')
        if db_name:
            # db_name might be comma-separated if multiple are set;
            # take the first one
            return db_name.split(',')[0].strip()

        # 2. List available databases and use if exactly one
        try:
            dbs = db_service.list_dbs()
            if len(dbs) == 1:
                return dbs[0]
        except Exception:
            pass

        return None

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _format_employee_dt(dt, employee=None):
        """Format a naive UTC datetime object to ISO 8601 format localized to the employee's timezone."""
        if not dt:
            return None
        import pytz
        # Odoo datetimes are naive UTC in DB
        dt_utc = pytz.utc.localize(dt)
        emp = employee or request.env.user.employee_id
        if emp:
            tz_name = emp._get_tz() if hasattr(emp, '_get_tz') else (emp.tz or 'UTC')
        else:
            tz_name = 'UTC'
        try:
            tz = pytz.timezone(tz_name)
            dt_local = dt_utc.astimezone(tz)
        except Exception:
            dt_local = dt_utc
        return dt_local.strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def _get_employee():
        """Return the employee linked to the current user, or raise."""
        employee = request.env.user.employee_id
        if not employee:
            return None, {
                'status': 'error',
                'message': 'No employee record linked to the current user.',
            }
        return employee, None

    @staticmethod
    def _build_geo_info(latitude, longitude, mode='systray'):
        """Build the geo_information dict that Odoo's _attendance_action_change expects.

        Follows the same pattern as Odoo's native _get_geoip_response but with
        a try/except fallback for environments without GeoIP configured.
        """
        try:
            geo = {
                'city': request.geoip.city.name or 'Unknown',
                'country_name': request.geoip.country.name or request.geoip.continent.name or 'Unknown',
                'latitude': latitude or request.geoip.location.latitude or False,
                'longitude': longitude or request.geoip.location.longitude or False,
                'ip_address': request.geoip.ip,
                'browser': request.httprequest.user_agent.browser or 'api',
                'mode': mode,
            }
        except Exception:
            geo = {
                'city': 'Unknown',
                'country_name': 'Unknown',
                'latitude': latitude or False,
                'longitude': longitude or False,
                'ip_address': request.httprequest.remote_addr or '',
                'browser': 'api',
                'mode': mode,
            }
        return geo

    @staticmethod
    def _create_location_record(attendance, employee, location_type,
                                latitude, longitude, accuracy, address,
                                is_auto=False):
        """Create an attendance.location record."""
        return request.env['attendance.location'].sudo().create({
            'attendance_id': attendance.id,
            'employee_id': employee.id,
            'location_type': location_type,
            'latitude': latitude or 0.0,
            'longitude': longitude or 0.0,
            'accuracy': accuracy or 0.0,
            'address': address or '',
            'is_auto_checkout': is_auto,
        })

    # -------------------------------------------------------------------------
    # API Endpoints
    # -------------------------------------------------------------------------

    @http.route('/api/attendance/check-in', type='json', auth='user', methods=['POST'])
    def api_check_in(self, latitude=False, longitude=False, accuracy=False, address=''):
        """Check in the current user's employee with GPS location data.

        Request body (JSON-RPC params):
            latitude  (float): GPS latitude
            longitude (float): GPS longitude
            accuracy  (float): GPS accuracy in meters
            address   (str):   Optional human-readable address
        """
        employee, error = self._get_employee()
        if error:
            return error

        # Validate employee is not already checked in
        if employee.attendance_state == 'checked_in':
            return {
                'status': 'error',
                'message': 'Employee is already checked in.',
                'last_check_in': self._format_employee_dt(employee.last_check_in, employee),
            }

        # Build geo info for Odoo's native attendance fields (in_latitude, etc.)
        geo_info = self._build_geo_info(latitude, longitude, mode='systray')

        # Create attendance via Odoo's standard method
        attendance = employee.sudo()._attendance_action_change(geo_info)

        # Write the custom address field
        if address:
            attendance.sudo().write({'checkin_address': address})

        # Create detailed location record
        self._create_location_record(
            attendance, employee, 'check_in',
            latitude, longitude, accuracy, address,
        )

        return {
            'status': 'success',
            'message': 'Checked in successfully.',
            'attendance_id': attendance.id,
            'check_in': self._format_employee_dt(attendance.check_in, employee),
        }

    @http.route('/api/attendance/check-out', type='json', auth='user', methods=['POST'])
    def api_check_out(self, latitude=False, longitude=False, accuracy=False,
                      address='', locations=None):
        """Check out the current user's employee with GPS location data.

        Request body (JSON-RPC params):
            latitude   (float): GPS latitude at checkout
            longitude  (float): GPS longitude at checkout
            accuracy   (float): GPS accuracy in meters at checkout
            address    (str):   Optional human-readable address at checkout
            locations  (list):  Array of location breadcrumbs collected throughout the day.
                                Each item: {
                                    "latitude": float,
                                    "longitude": float,
                                    "accuracy": float (optional),
                                    "address": str (optional),
                                    "timestamp": str (ISO format, e.g. "2026-07-21T10:30:00")
                                }
        """
        employee, error = self._get_employee()
        if error:
            return error

        # Validate employee is currently checked in
        if employee.attendance_state != 'checked_in':
            return {
                'status': 'error',
                'message': 'Employee is not checked in. Cannot check out.',
            }

        # Build geo info for Odoo's native attendance fields (out_latitude, etc.)
        geo_info = self._build_geo_info(latitude, longitude, mode='systray')

        # Check out via Odoo's standard method
        attendance = employee.sudo()._attendance_action_change(geo_info)

        # Write the custom address field
        if address:
            attendance.sudo().write({'checkout_address': address})

        # Create checkout location record
        self._create_location_record(
            attendance, employee, 'check_out',
            latitude, longitude, accuracy, address,
        )

        # Store all tracking/breadcrumb locations collected throughout the day
        tracking_count = 0
        if locations and isinstance(locations, list):
            location_vals = []
            for loc in locations:
                if not isinstance(loc, dict):
                    continue
                timestamp = loc.get('timestamp')
                # Parse timestamp if provided as string
                ts_value = False
                if timestamp:
                    try:
                        ts_value = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S')
                    except (ValueError, TypeError):
                        try:
                            ts_value = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            ts_value = False

                location_vals.append({
                    'attendance_id': attendance.id,
                    'employee_id': employee.id,
                    'location_type': 'tracking',
                    'latitude': loc.get('latitude', 0.0),
                    'longitude': loc.get('longitude', 0.0),
                    'accuracy': loc.get('accuracy', 0.0),
                    'address': loc.get('address', ''),
                    'timestamp': ts_value or fields.Datetime.now(),
                    'is_auto_checkout': False,
                })

            if location_vals:
                request.env['attendance.location'].sudo().create(location_vals)
                tracking_count = len(location_vals)

        return {
            'status': 'success',
            'message': 'Checked out successfully.',
            'attendance_id': attendance.id,
            'check_in': self._format_employee_dt(attendance.check_in, employee),
            'check_out': self._format_employee_dt(attendance.check_out, employee),
            'worked_hours': float_round(attendance.worked_hours or 0.0, precision_digits=2),
            'tracking_locations_saved': tracking_count,
        }

    @http.route('/api/attendance/status', type='json', auth='user', methods=['POST'], readonly=True)
    def api_status(self):
        """Get the current attendance status for the logged-in user's employee.

        No parameters needed — employee is auto-detected.
        """
        employee, error = self._get_employee()
        if error:
            return error

        return {
            'status': 'success',
            'employee_name': employee.name,
            'attendance_state': employee.attendance_state,
            'hours_today': float_round(employee.hours_today, precision_digits=2),
            'last_check_in': self._format_employee_dt(employee.last_check_in, employee),
            'last_check_out': self._format_employee_dt(employee.last_check_out, employee),
        }

    @http.route('/api/attendance/history', type='json', auth='user', methods=['POST'], readonly=True)
    def api_history(self, date_from=None, date_to=None):
        """Get attendance history with location data for the logged-in user.

        Request body (JSON-RPC params):
            date_from (str): Start date in YYYY-MM-DD format (defaults to 30 days ago)
            date_to   (str): End date in YYYY-MM-DD format (defaults to today)
        """
        employee, error = self._get_employee()
        if error:
            return error

        # Parse date range
        try:
            if date_from:
                dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            else:
                dt_from = datetime.now() - timedelta(days=30)

            if date_to:
                dt_to = datetime.strptime(date_to, '%Y-%m-%d').replace(
                    hour=23, minute=59, second=59
                )
            else:
                dt_to = datetime.now().replace(hour=23, minute=59, second=59)
        except ValueError:
            return {
                'status': 'error',
                'message': 'Invalid date format. Use YYYY-MM-DD.',
            }

        # Fetch attendances
        attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', dt_from),
            ('check_in', '<=', dt_to),
        ], order='check_in desc')

        records = []
        for att in attendances:
            # Get location data for this attendance
            checkin_loc = att.location_ids.filtered(
                lambda l: l.location_type == 'check_in'
            )
            checkout_loc = att.location_ids.filtered(
                lambda l: l.location_type == 'check_out'
            )

            record = {
                'attendance_id': att.id,
                'check_in': self._format_employee_dt(att.check_in, employee),
                'check_out': self._format_employee_dt(att.check_out, employee),
                'worked_hours': float_round(att.worked_hours or 0.0, precision_digits=2),
                'checkin_location': {
                    'latitude': checkin_loc[0].latitude if checkin_loc else None,
                    'longitude': checkin_loc[0].longitude if checkin_loc else None,
                    'accuracy': checkin_loc[0].accuracy if checkin_loc else None,
                    'address': checkin_loc[0].address if checkin_loc else None,
                } if checkin_loc else None,
                'checkout_location': {
                    'latitude': checkout_loc[0].latitude if checkout_loc else None,
                    'longitude': checkout_loc[0].longitude if checkout_loc else None,
                    'accuracy': checkout_loc[0].accuracy if checkout_loc else None,
                    'address': checkout_loc[0].address if checkout_loc else None,
                    'is_auto_checkout': checkout_loc[0].is_auto_checkout if checkout_loc else False,
                } if checkout_loc else None,
                'tracking_locations': [
                    {
                        'latitude': loc.latitude,
                        'longitude': loc.longitude,
                        'accuracy': loc.accuracy,
                        'address': loc.address,
                        'timestamp': self._format_employee_dt(loc.timestamp, employee),
                    } for loc in att.location_ids.filtered(lambda l: l.location_type == 'tracking').sorted(key=lambda l: l.timestamp or l.create_date)
                ]
            }
            records.append(record)

        return {
            'status': 'success',
            'count': len(records),
            'records': records,
        }
