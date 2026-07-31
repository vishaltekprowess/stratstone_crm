import logging
import json

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class LeadAPIController(http.Controller):
    """Public POST API for creating CRM leads from external sources.

    Endpoint:
        POST /api/leads

    Content-Type: application/json

    Request body:
        {
            "name":    "John Doe",              (required)
            "phone":   "+919876543210",          (optional)
            "email":   "johndoe@example.com",    (optional)
            "config":  "2 BHK Signature Residence",  (optional)
            "comment": "Looking for ...",        (optional)
            "source":  "Popup Modal ..."         (optional)
        }

    Response (JSON):
        Success → {"status": "success", "lead_id": 42, "message": "Lead created successfully."}
        Error   → {"status": "error", "message": "..."}
    """

    @http.route(
        '/api/leads',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def create_lead(self, **kw):
        """Create a CRM lead from an external form submission."""
        try:
            # --- Extract fields from JSON-RPC params ---
            name = kw.get('name', '').strip() if kw.get('name') else ''
            phone = kw.get('phone', '').strip() if kw.get('phone') else ''
            email = kw.get('email', '').strip() if kw.get('email') else ''
            config = kw.get('config', '').strip() if kw.get('config') else ''
            comment = kw.get('comment', '').strip() if kw.get('comment') else ''
            source = kw.get('source', '').strip() if kw.get('source') else ''

            # --- Validate required fields ---
            if not name:
                return {
                    'status': 'error',
                    'message': '"name" is required.',
                }

            # --- Resolve database (same pattern as stratstone_attendance_api) ---
            db = self._get_db()
            if not db:
                return {
                    'status': 'error',
                    'message': 'Could not determine the database.',
                }

            # Use registry to get an env with SUPERUSER
            registry = request.env.registry
            with registry.cursor() as cr:
                env = request.env(cr=cr, user=1)

                # --- Build description from all submitted fields ---
                desc_lines = []
                if config:
                    desc_lines.append(f"Configuration: {config}")
                if comment:
                    desc_lines.append(f"Comment: {comment}")
                if source:
                    desc_lines.append(f"Source Form: {source}")
                description = "\n".join(desc_lines)

                # --- Resolve UTM source ---
                source_id = False
                if source:
                    utm_source = env['utm.source'].search(
                        [('name', '=', source)], limit=1)
                    if not utm_source:
                        utm_source = env['utm.source'].create(
                            {'name': source})
                    source_id = utm_source.id

                # --- Build lead name ---
                lead_name_parts = [name]
                if config:
                    lead_name_parts.append(config)
                lead_name = " - ".join(lead_name_parts)

                # --- Round-robin salesperson assignment ---
                user_id, team_id = env['crm.lead']._get_next_round_robin_salesperson()

                # --- Create the lead ---
                lead_vals = {
                    'type': 'opportunity',
                    'name': lead_name,
                    'contact_name': name,
                    'phone': phone or False,
                    'email_from': email or False,
                    'description': description or False,
                    'source_id': source_id,
                    'user_id': user_id,
                    'team_id': team_id,
                }
                lead = env['crm.lead'].create(lead_vals)

                _logger.info(
                    "API lead created: id=%s name=%s phone=%s email=%s",
                    lead.id, name, phone, email,
                )

                return {
                    'status': 'success',
                    'lead_id': lead.id,
                    'message': 'Lead created successfully.',
                }

        except Exception as e:
            _logger.exception("Error creating lead via API: %s", e)
            return {
                'status': 'error',
                'message': str(e),
            }

    def _get_db(self):
        """Auto-detect the database name."""
        # 1. From Odoo config
        from odoo.tools import config
        db = config.get('db_name')
        if db:
            return db.split(',')[0].strip()

        # 2. From HTTP database header / session
        if hasattr(request, 'db') and request.db:
            return request.db

        # 3. Only one database available
        try:
            import odoo.service.db as db_service
            dbs = db_service.list_dbs()
            if len(dbs) == 1:
                return dbs[0]
        except Exception:
            pass

        return None
