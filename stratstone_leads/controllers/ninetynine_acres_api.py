import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class NinetyNineAcresWebhookController(http.Controller):
    """Open HTTP endpoint that accepts any JSON from 99acres.

    The raw payload is stored as-is in ``ninetynine.acres.raw.log`` so it
    can be inspected and mapped to CRM lead fields later, once the
    request-body schema is confirmed.

    Endpoint
    --------
    POST /api/99acres/lead

    * ``type='http'``  – accepts a plain HTTP POST (not JSON-RPC)
    * ``auth='none'``  – no Odoo login / API key required
    * ``csrf=False``   – external callers won't send a CSRF token
    """

    @http.route(
        '/api/99acres/lead',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def receive_99acres_payload(self, **kw):
        """Accept any payload from 99acres — JSON or form-encoded — and
        store the raw data as JSON text."""
        try:
            req = request.httprequest
            content_type = (req.content_type or '').lower()

            # --- Determine payload source -------------------------------
            raw_body = None

            # 1) Try JSON first (explicit Content-Type or raw body parse)
            if 'application/json' in content_type:
                raw_body = req.get_data(as_text=True)
                if raw_body:
                    try:
                        json.loads(raw_body)  # validate
                    except json.JSONDecodeError:
                        _logger.warning(
                            "99acres webhook: Content-Type says JSON but "
                            "body is not valid JSON: %s", raw_body[:500],
                        )
                        raw_body = None  # fall through to form handling

            # 2) If not JSON or JSON parsing failed, try raw body anyway
            if raw_body is None:
                raw_text = req.get_data(as_text=True)
                if raw_text:
                    try:
                        json.loads(raw_text)
                        raw_body = raw_text
                    except json.JSONDecodeError:
                        pass  # not JSON — will use form params below

            # 3) Fall back to form / multipart params (includes **kw)
            if raw_body is None:
                form_data = {}
                # Merge Werkzeug form + query-string params
                for key, value in req.form.to_dict(flat=False).items():
                    form_data[key] = value if len(value) > 1 else value[0]
                for key, value in req.args.to_dict(flat=False).items():
                    form_data[key] = value if len(value) > 1 else value[0]
                # Also merge any kwargs Odoo already parsed
                form_data.update(kw)

                if form_data:
                    raw_body = json.dumps(form_data, ensure_ascii=False)
                else:
                    raw_body = '{}'

            # --- Gather request metadata --------------------------------
            vals = {
                'raw_json': raw_body,
                'http_method': req.method,
                'source_ip': req.remote_addr,
                'content_type': content_type,
                'user_agent': req.user_agent.string if req.user_agent else '',
                'request_url': req.url,
            }

            # --- Resolve database & persist -----------------------------
            db = self._get_db()
            if not db:
                _logger.error("99acres webhook: could not determine database.")
                return Response(
                    json.dumps({
                        'status': 'error',
                        'message': 'Could not determine the database.',
                    }),
                    status=500,
                    content_type='application/json',
                )

            registry = request.env.registry
            with registry.cursor() as cr:
                env = request.env(cr=cr, user=1)
                log_record = env['ninetynine.acres.raw.log'].create(vals)
                log_id = log_record.id

            _logger.info(
                "99acres webhook: stored raw payload  id=%s  ip=%s  type=%s",
                log_id,
                vals['source_ip'],
                content_type,
            )

            return Response(
                json.dumps({
                    'status': 'success',
                    'message': 'Payload received and stored.',
                    'log_id': log_id,
                }),
                status=200,
                content_type='application/json',
            )

        except Exception as e:
            _logger.exception("99acres webhook error: %s", e)
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': str(e),
                }),
                status=500,
                content_type='application/json',
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _get_db():
        """Auto-detect the database name (same logic used by lead_api)."""
        from odoo.tools import config

        db = config.get('db_name')
        if db:
            return db.split(',')[0].strip()

        if hasattr(request, 'db') and request.db:
            return request.db

        try:
            import odoo.service.db as db_service
            dbs = db_service.list_dbs()
            if len(dbs) == 1:
                return dbs[0]
        except Exception:
            pass

        return None
