import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class NinetyNineAcresRawLog(models.Model):
    """Stores every raw JSON payload received from the 99acres webhook.

    Once the request-body schema is finalised, a scheduled action or
    manual button can parse these records and create CRM leads.
    """

    _name = 'ninetynine.acres.raw.log'
    _description = '99acres Raw Payload Log'
    _order = 'received_at desc'
    _rec_name = 'display_name'

    # --- Payload data ---
    raw_json = fields.Text(
        string='Raw JSON',
        required=True,
        readonly=True,
        help='The complete, unmodified JSON body received from 99acres.',
    )

    # --- Request metadata ---
    http_method = fields.Char(
        string='HTTP Method',
        readonly=True,
    )
    source_ip = fields.Char(
        string='Source IP',
        readonly=True,
    )
    content_type = fields.Char(
        string='Content-Type',
        readonly=True,
    )
    user_agent = fields.Char(
        string='User-Agent',
        readonly=True,
    )
    request_url = fields.Char(
        string='Request URL',
        readonly=True,
    )

    # --- Timestamps ---
    received_at = fields.Datetime(
        string='Received At',
        default=fields.Datetime.now,
        readonly=True,
        index=True,
    )

    # --- Processing state ---
    state = fields.Selection(
        selection=[
            ('new', 'New'),
            ('processed', 'Processed'),
            ('error', 'Error'),
        ],
        string='Status',
        default='new',
        readonly=True,
        index=True,
    )
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
    )
    lead_id = fields.Many2one(
        'crm.lead',
        string='Created Lead',
        readonly=True,
        ondelete='set null',
    )

    # --- Display name ---
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('received_at', 'source_ip')
    def _compute_display_name(self):
        for rec in self:
            ts = rec.received_at or 'No date'
            rec.display_name = f"99acres – {ts} – {rec.source_ip or 'unknown'}"

    # --- Helpers ---
    def get_parsed_json(self):
        """Return the raw_json field parsed as a Python dict/list."""
        self.ensure_one()
        try:
            return json.loads(self.raw_json)
        except (json.JSONDecodeError, TypeError):
            return {}
