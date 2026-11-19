# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    description = fields.Html(
        string='Invoice Bank Details',
        help='Formatted bank and payment instructions to display on invoices (A/C No, IFSC, Branch, UPI, etc.)',
    )


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def get_split_gst_taxes(self):
        """
        Compute CGST, SGST, and IGST rates and amounts for Indian GST compliance.
        Uses tax_ids.compute_all() for precision.
        """
        self.ensure_one()
        results = {
            'cgst_rate': 0.0,
            'cgst_amount': 0.0,
            'sgst_rate': 0.0,
            'sgst_amount': 0.0,
            'igst_rate': 0.0,
            'igst_amount': 0.0,
            'has_gst': False,
        }

        if not self.tax_ids:
            return results

        tax_data = self.tax_ids.compute_all(
            self.price_unit * (1 - (self.discount or 0.0) / 100.0),
            currency=self.currency_id,
            quantity=self.quantity,
            product=self.product_id,
            partner=self.partner_id,
        )

        for tax in tax_data.get('taxes', []):
            name = (tax.get('name') or '').upper()
            amount = tax.get('amount', 0.0)
            base = tax.get('base', 0.0)
            rate = round((amount / base * 100.0), 2) if base else 0.0

            if 'CGST' in name:
                results['cgst_rate'] = rate
                results['cgst_amount'] = amount
                results['has_gst'] = True
            elif 'SGST' in name:
                results['sgst_rate'] = rate
                results['sgst_amount'] = amount
                results['has_gst'] = True
            elif 'IGST' in name:
                results['igst_rate'] = rate
                results['igst_amount'] = amount
                results['has_gst'] = True

        return results
