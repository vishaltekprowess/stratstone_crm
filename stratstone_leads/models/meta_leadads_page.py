# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class MetaLeadadsPage(models.Model):
    _name = 'meta.leadads.page'
    _description = 'Meta Facebook Page'
    _order = 'name, id desc'

    name = fields.Char(
        string="Page Name / Label",
        required=True,
        help="Display name or label for this Facebook Page (e.g. Stratstone Prime, Stratstone Luxury).",
    )
    page_id = fields.Char(
        string="Meta Page ID",
        required=True,
        index=True,
        help="Facebook Page ID that owns the Leadgen Forms (e.g. 102938475612345).",
    )
    access_token = fields.Char(
        string="Access Token",
        required=True,
        help="Page Access Token (or User Access Token with leadgen permissions for this page).",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        help="Enable or disable automated lead retrieval for this page.",
    )

    sync_all_forms = fields.Boolean(
        string="Sync All Forms",
        default=True,
        help="If checked, automatically discovers and syncs all leadgen forms belonging to this page. "
             "If unchecked, syncs only the specific Form IDs entered below.",
    )
    form_ids = fields.Char(
        string="Specific Form IDs",
        help="Comma-separated Form IDs (e.g. 103976261614743, 705986448913842). "
             "Only used when 'Sync All Forms' is unchecked.",
    )

    # Lead routing defaults (optional per page)
    assignment_type = fields.Selection([
        ('round_robin', 'Round Robin'),
        ('specific_user', 'Specific Salesperson'),
        ('no_assignment', 'Do Not Assign (Leave Unassigned)'),
    ], string="Salesperson Assignment", default='round_robin', required=True,
       help="Choose how salespeople are assigned for leads from this page:\n"
            "- Round Robin: Automatically rotate assignment among salespeople.\n"
            "- Specific Salesperson: Assign all leads to the selected salesperson.\n"
            "- Do Not Assign: Create leads without assigning any salesperson.")
    team_id = fields.Many2one(
        'crm.team',
        string="Sales Team",
        help="Default Sales Team for leads from this page. Leave empty if no team should be assigned.",
    )
    user_id = fields.Many2one(
        'res.users',
        string="Salesperson",
        help="Default Salesperson for leads from this page (when 'Specific Salesperson' is selected).",
    )
    campaign_id = fields.Many2one(
        'utm.campaign',
        string="Default Campaign",
        help="Default Campaign for leads from this page if not specified in the Meta lead payload.",
    )
    source_id = fields.Many2one(
        'utm.source',
        string="Default Source",
        help="Default UTM Source (defaults to Facebook if left empty).",
    )

    # Sync status
    last_sync_date = fields.Datetime(
        string="Last Sync Date",
        readonly=True,
    )
    last_sync_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], string="Last Sync Status", readonly=True)
    last_sync_message = fields.Text(
        string="Last Sync Message",
        readonly=True,
    )

    lead_count = fields.Integer(
        string="Leads Count",
        compute='_compute_lead_count',
    )

    _sql_constraints = [
        ('uniq_page_id', 'unique(page_id)',
         'A record with this Meta Page ID already exists!'),
    ]

    def _compute_lead_count(self):
        for rec in self:
            rec.lead_count = self.env['crm.lead'].search_count(
                [('meta_page_id', '=', rec.id)]
            )

    def action_view_leads(self):
        self.ensure_one()
        return {
            'name': _('Leads: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'view_mode': 'list,form',
            'domain': [('meta_page_id', '=', self.id)],
            'context': {'default_meta_page_id': self.id},
        }

    def get_lead_salesperson_and_team(self, existing_lead=None):
        """
        Determine (user_id, team_id) for a lead originating from this page.
        Returns: (user_id or False, team_id or False)
        """
        self.ensure_one()
        # If an existing lead already has a salesperson assigned, preserve it
        if existing_lead and existing_lead.user_id:
            existing_team_id = existing_lead.team_id.id if existing_lead.team_id else (self.team_id.id or False)
            return existing_lead.user_id.id, existing_team_id

        existing_team_id = existing_lead.team_id.id if (existing_lead and existing_lead.team_id) else False

        if self.assignment_type == 'no_assignment':
            return False, (self.team_id.id or existing_team_id)

        if self.assignment_type == 'specific_user':
            return (self.user_id.id if self.user_id else False), (self.team_id.id or existing_team_id)

        # Fallback / Round-Robin:
        if self.user_id:
            return self.user_id.id, (self.team_id.id or existing_team_id)

        user_id, team_id = self.env['crm.lead']._get_next_round_robin_salesperson(team=self.team_id)
        return user_id, (team_id or existing_team_id)

    def _get_page_access_token(self):
        """Exchange user token for page token if needed, or return access token."""
        self.ensure_one()
        if not self.access_token or not self.page_id:
            return self.access_token or ''
        cleaned_token = self.access_token.strip()
        cleaned_page_id = self.page_id.strip()
        try:
            url = f"https://graph.facebook.com/v24.0/{cleaned_page_id}"
            resp = requests.get(
                url,
                params={"fields": "access_token", "access_token": cleaned_token},
                timeout=15,
            )
            data = resp.json()
            token = data.get("access_token")
            return token or cleaned_token
        except Exception:
            return cleaned_token

    def action_test_connection(self):
        """Test the Graph API connection and permissions for this page."""
        self.ensure_one()
        token = self._get_page_access_token()
        cleaned_page_id = self.page_id.strip()
        url = f"https://graph.facebook.com/v24.0/{cleaned_page_id}"
        try:
            resp = requests.get(
                url,
                params={"fields": "id,name", "access_token": token},
                timeout=20,
            )
            data = resp.json()
            if 'error' in data:
                err_msg = data['error'].get('message', str(data['error']))
                raise UserError(_("Meta API Error: %s") % err_msg)

            page_name = data.get('name', self.name)

            # Check forms
            forms_resp = requests.get(
                f"https://graph.facebook.com/v24.0/{cleaned_page_id}/leadgen_forms",
                params={"access_token": token, "limit": 100},
                timeout=20,
            )
            forms_data = forms_resp.json()
            forms_count = len(forms_data.get('data', [])) if 'data' in forms_data else 0

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Connected to "%(name)s" (Page ID: %(id)s). Found %(count)s form(s).') % {
                        'name': page_name,
                        'id': self.page_id,
                        'count': forms_count,
                    },
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(_("Connection failed: %s") % str(e))

    def action_sync_now(self):
        """Trigger sync for today's leads for this specific page."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        res = self.env['crm.lead'].sudo().with_context(
            meta_date_from=today,
            meta_date_to=today,
            meta_manual_sync=True,
        ).meta_leadads_sync_leads(page_ids=[self.id])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Meta Lead Ads Sync - %s') % self.name,
                'message': _('Created: %(c)s, Updated: %(u)s, Skipped: %(s)s') % {
                    'c': res.get('created', 0),
                    'u': res.get('updated', 0),
                    's': res.get('skipped', 0),
                },
                'sticky': False,
                'type': 'success',
            }
        }
