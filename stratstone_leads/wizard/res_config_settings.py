from odoo import models, fields, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Meta Lead Ads (Facebook Leadgen)
    meta_leadads_page_id = fields.Char(
        string="Meta Page ID",
        config_parameter="stratstone_leads.meta_leadads_page_id",
        help="Facebook Page ID that owns the Leadgen Forms "
             "(used for /{page_id}/leadgen_forms).",
    )
    meta_leadads_access_token = fields.Char(
        string="Meta Access Token",
        config_parameter="stratstone_leads.meta_leadads_access_token",
        help="User/Page access token. The sync will automatically fetch the "
             "Page access token using the configured Page ID when needed.",
    )
    meta_leadads_form_ids = fields.Char(
        string="Meta Lead Form IDs",
        config_parameter="stratstone_leads.meta_leadads_form_ids",
        help="Optional. Comma-separated Leadgen Form IDs to sync. "
             "Leave empty to auto-fetch all forms from the configured Page ID.",
    )

    def action_meta_leadads_sync_now(self):
        """Manually trigger a sync for today's Meta leads."""
        self.ensure_one()
        try:
            today = fields.Date.context_today(self)
            res = self.env['crm.lead'].sudo().with_context(
                meta_date_from=today, meta_date_to=today,
            ).meta_leadads_sync_leads()
        except Exception as e:
            raise UserError(str(e))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Meta Lead Ads Sync'),
                'message': _(
                    'Created: %(c)s, Updated: %(u)s, Skipped: %(s)s'
                ) % {
                    'c': res.get('created', 0),
                    'u': res.get('updated', 0),
                    's': res.get('skipped', 0),
                },
                'sticky': False,
                'type': 'success',
            }
        }
