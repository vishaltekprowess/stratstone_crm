from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MetaLeadadsFetchWizard(models.TransientModel):
    _name = 'meta.leadads.fetch.wizard'
    _description = 'Fetch Meta Lead Ads (Date Range)'

    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    date_to = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wiz in self:
            if (wiz.date_from and wiz.date_to
                    and wiz.date_from > wiz.date_to):
                raise UserError(
                    _("Start date cannot be after end date."))

    def action_fetch(self):
        """Trigger a Meta Lead Ads sync for the selected date range."""
        self.ensure_one()
        res = self.env['crm.lead'].sudo().with_context(
            meta_date_from=self.date_from,
            meta_date_to=self.date_to,
        ).meta_leadads_sync_leads()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Meta Lead Ads Fetch'),
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
