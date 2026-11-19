# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import re
import logging

_logger = logging.getLogger(__name__)

try:
    from num2words import num2words
except ImportError:
    num2words = None


class AccountMove(models.Model):
    _inherit = 'account.move'

    amount_total_words = fields.Char(
        string='Total in Words',
        compute='_compute_amount_total_words',
        help='Invoice total amount expressed in words for official/legal compliance.',
    )

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_total_words(self):
        """Compute amount in words using num2words or currency_id.amount_to_text fallback."""
        for move in self:
            if not move.currency_id or not move.amount_total:
                move.amount_total_words = False
                continue

            try:
                # If currency is INR and num2words is available, use Indian numbering system
                if move.currency_id.name == 'INR' and num2words:
                    integer_part = int(move.amount_total)
                    decimal_part = int(round((move.amount_total - integer_part) * 100))
                    words = num2words(integer_part, lang='en_IN').title() + ' Rupees'
                    if decimal_part > 0:
                        words += ' and ' + num2words(decimal_part, lang='en_IN').title() + ' Paise'
                    words += ' Only'
                    move.amount_total_words = words
                else:
                    move.amount_total_words = move.currency_id.amount_to_text(move.amount_total)
            except Exception as e:
                _logger.warning("Could not convert amount to words: %s", e)
                move.amount_total_words = move.currency_id.amount_to_text(move.amount_total)

    @api.depends('date', 'journal_id', 'move_type', 'name', 'posted_before', 'sequence_number', 'sequence_prefix', 'state')
    def _compute_name_placeholder(self):
        """Override to correctly compute name placeholder with fiscal year reset.

        When a new fiscal year starts (new prefix), the sequence resets to 1
        instead of continuing from the previous year's last number.
        """
        for move in self:
            if (not move.name or move.name == '/') and move.date and not move._get_last_sequence():
                sequence_format_string, sequence_format_values = move._get_next_sequence_format()
                if move.move_type in ('out_invoice', 'out_refund', 'in_refund', 'in_invoice'):
                    base_prefix = (
                        str(sequence_format_values.get('prefix1') or '') +
                        str(sequence_format_values.get('year') or '') +
                        str(sequence_format_values.get('prefix2') or '') +
                        str(sequence_format_values.get('year_end') or '')
                    )
                    last_moves = self.env['account.move'].search([
                        ('move_type', '=', move.move_type),
                        ('name', 'ilike', base_prefix + '%')
                    ])
                    max_seq = 0
                    for lm in last_moves:
                        if lm.name:
                            match = re.search(r'(\d+)$', lm.name)
                            if match:
                                seq = int(match.group(1))
                                if seq > max_seq:
                                    max_seq = seq
                    if sequence_format_values.get('seq', 0) != (max_seq + 1):
                        sequence_format_values['seq'] = max_seq
                sequence_format_values['seq'] = sequence_format_values['seq'] + 1
                move.name_placeholder = sequence_format_string.format(**sequence_format_values)
            else:
                move.name_placeholder = False

    def _get_next_sequence_format(self):
        """Extend to fix the sequence number for fiscal year reset."""
        format_string, format_values = super()._get_next_sequence_format()

        if self.move_type in ('out_invoice', 'out_refund', 'in_refund', 'in_invoice'):
            base_prefix = (
                str(format_values.get('prefix1') or '') +
                str(format_values.get('year') or '') +
                str(format_values.get('prefix2') or '') +
                str(format_values.get('year_end') or '')
            )

            last_moves = self.env['account.move'].search([
                ('move_type', '=', self.move_type),
                ('name', 'ilike', base_prefix + '%')
            ])

            max_seq = 0
            for lm in last_moves:
                if lm.name:
                    match = re.search(r'(\d+)$', lm.name)
                    if match:
                        seq = int(match.group(1))
                        if seq > max_seq:
                            max_seq = seq

            if format_values.get('seq', 0) != (max_seq + 1):
                format_values['seq'] = max_seq

        return format_string, format_values
