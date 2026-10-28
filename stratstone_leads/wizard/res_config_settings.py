from odoo import models, fields, _
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'



    def action_meta_leadads_sync_now(self):
        """Manually trigger a sync for today's Meta leads."""
        self.ensure_one()
        try:
            today = fields.Date.context_today(self)
            res = self.env['crm.lead'].sudo().with_context(
                meta_date_from=today, meta_date_to=today,
                meta_manual_sync=True,
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
