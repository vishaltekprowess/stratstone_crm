# -*- coding: utf-8 -*-

from odoo import models, api, fields
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import json


import logging

_logger = logging.getLogger(__name__)


class TekprowessManufacturingDashboard(models.TransientModel):
    _name = 'tekprowess.dashboard'
    _description = 'Tekprowess Dashboard'

    # -------------------------------------------------------------------------
    # Dynamic Menu Creation (called from data XML on every install/upgrade)
    # -------------------------------------------------------------------------

    @api.model
    def _create_menus(self):
        """Dynamically create dashboard menu items based on installed modules."""
        IrModule = self.env['ir.module.module']
        IrModelData = self.env['ir.model.data']

        def _is_installed(module_name):
            return bool(IrModule.search([
                ('name', '=', module_name), ('state', '=', 'installed')
            ], limit=1))

        def _get_xmlid(xmlid_str):
            try:
                return self.env.ref(xmlid_str).id
            except Exception:
                return False

        # (parent_menu_xmlid, action_xmlid, menu_name, sequence, data_name, override_xmlid, group_xmlids)
        menu_defs = []
        if _is_installed('crm'):
            menu_defs.append(('crm.crm_menu_root', 'tekprowess_dashboard.action_tekprowess_crm_dashboard', 'Dashboard', 0, 'menu_tekprowess_crm_dashboard', None, 'sales_team.group_sale_salesman'))
        if _is_installed('mrp'):
            menu_defs.append(('mrp.menu_mrp_root', 'tekprowess_dashboard.action_tekprowess_mfg_dashboard', 'Dashboard', 0, 'menu_tekprowess_mfg_dashboard', None, 'mrp.group_mrp_user'))
        if _is_installed('sale'):
            menu_defs.append(('sale.sale_menu_root', 'tekprowess_dashboard.action_tekprowess_sale_dashboard', 'Dashboard', 0, 'menu_tekprowess_sale_dashboard', None, 'sales_team.group_sale_salesman'))
        if _is_installed('purchase'):
            menu_defs.append(('purchase.menu_purchase_root', 'tekprowess_dashboard.action_tekprowess_purchase_dashboard', 'Dashboard', 0, 'menu_tekprowess_purchase_dashboard', None, 'purchase.group_purchase_user'))
        if _is_installed('account'):
            # allow read-only and invoice users
            menu_defs.append(('account.menu_finance', 'tekprowess_dashboard.action_tekprowess_accounting_dashboard', 'Dashboard', 0, 'menu_tekprowess_accounting_dashboard', None, 'account.group_account_readonly,account.group_account_invoice'))
        if _is_installed('stock'):
            menu_defs.append(('stock.menu_stock_root', 'tekprowess_dashboard.action_tekprowess_inventory_dashboard', 'Overview', 0, 'menu_tekprowess_inventory_dashboard', 'stock.stock_picking_type_menu', 'stock.group_stock_user'))

        for parent_xmlid, action_xmlid, name, sequence, data_name, override_xmlid, group_xmlids in menu_defs:
            parent_id = _get_xmlid(parent_xmlid)
            action_id = _get_xmlid(action_xmlid)
            if not parent_id or not action_id:
                continue

            # Resolve external IDs for groups
            group_ids = []
            if group_xmlids:
                for g_xmlid in group_xmlids.split(','):
                    g_id = _get_xmlid(g_xmlid.strip())
                    if g_id:
                        group_ids.append(g_id)

            if override_xmlid:
                existing_id = _get_xmlid(override_xmlid)
                if existing_id:
                    vals = {'action': 'ir.actions.client,%d' % action_id}
                    if group_ids:
                        vals['groups_id'] = [(6, 0, group_ids)]
                    self.env['ir.ui.menu'].browse(existing_id).write(vals)
                    _logger.info("Dashboard: overrode menu %s", override_xmlid)
                    continue

            existing = IrModelData.search([
                ('module', '=', 'tekprowess_dashboard'),
                ('name', '=', data_name),
            ], limit=1)
            
            if existing:
                # Upgrade path: ensure groups are set even on previously created menus
                if group_ids:
                    menu = self.env['ir.ui.menu'].browse(existing.res_id)
                    if menu.exists():
                        menu.write({'groups_id': [(6, 0, group_ids)]})
                continue

            menu_vals = {
                'name': name,
                'parent_id': parent_id,
                'action': 'ir.actions.client,%d' % action_id,
                'sequence': sequence,
            }
            if group_ids:
                menu_vals['groups_id'] = [(6, 0, group_ids)]

            menu = self.env['ir.ui.menu'].create(menu_vals)
            IrModelData.create({
                'module': 'tekprowess_dashboard',
                'name': data_name,
                'model': 'ir.ui.menu',
                'res_id': menu.id,
                'noupdate': True,
            })
            _logger.info("Dashboard: created menu '%s' under %s", name, parent_xmlid)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_month_labels(self, n=6):
        today = date.today()
        months = []
        for i in range(n - 1, -1, -1):
            d = today - relativedelta(months=i)
            start = d.replace(day=1)
            end = (start + relativedelta(months=1)) - timedelta(days=1)
            months.append({
                'label': start.strftime('%b'),
                'start': fields.Datetime.to_datetime(str(start) + ' 00:00:00'),
                'end': fields.Datetime.to_datetime(str(end) + ' 23:59:59'),
            })
        return months

    # -------------------------------------------------------------------------
    # CRM KPIs
    # -------------------------------------------------------------------------

    @api.model
    def get_crm_data(self):
        if 'crm.lead' not in self.env:
            return {}
        Lead = self.env['crm.lead']
        today = date.today()
        currency_symbol = self.env.company.currency_id.symbol or '$'

        # Domain for active opportunities
        base_domain = [('type', '=', 'opportunity')] if 'type' in Lead._fields else []

        active_opps = Lead.search(base_domain)
        total_opps_count = len(active_opps)
        total_expected_revenue = sum(active_opps.mapped('expected_revenue'))
        total_prorated_revenue = sum(active_opps.mapped('prorated_revenue')) if 'prorated_revenue' in Lead._fields else 0.0

        # Won opportunities
        won_domain = base_domain + ['|', ('probability', '=', 100), ('stage_id.is_won', '=', True)]
        won_opps = Lead.search(won_domain)
        won_count = len(won_opps)
        won_revenue = sum(won_opps.mapped('expected_revenue'))

        # Lost opportunities (active=False)
        lost_domain = [('active', '=', False)]
        if 'type' in Lead._fields:
            lost_domain.append(('type', '=', 'opportunity'))
        lost_opps = Lead.with_context(active_test=False).search(lost_domain + [('probability', '=', 0)])
        lost_count = len(lost_opps)

        # In Pipeline
        pipeline_count = total_opps_count - won_count

        # Win Rate
        closed_total = won_count + lost_count
        win_rate = round((won_count / closed_total * 100), 1) if closed_total > 0 else 0.0

        # Average Deal Size
        avg_deal_size = round(total_expected_revenue / total_opps_count, 2) if total_opps_count > 0 else 0.0

        # Overdue / Scheduled today
        overdue_count = Lead.search_count(base_domain + [
            ('date_deadline', '<', today),
            ('date_deadline', '!=', False),
            ('probability', '<', 100),
        ])
        today_start = fields.Datetime.to_datetime(str(today) + ' 00:00:00')
        today_end = fields.Datetime.to_datetime(str(today) + ' 23:59:59')
        today_count = Lead.search_count(base_domain + [
            ('create_date', '>=', today_start),
            ('create_date', '<=', today_end),
        ])

        # Monthly chart data (last 6 months)
        months = self._get_month_labels(6)
        chart_labels = [m['label'] for m in months]
        chart_opps_count = []
        chart_revenue = []
        chart_won_count = []

        for m in months:
            m_opps = Lead.search(base_domain + [
                ('create_date', '>=', m['start']),
                ('create_date', '<=', m['end']),
            ])
            m_won = Lead.search(won_domain + [
                ('create_date', '>=', m['start']),
                ('create_date', '<=', m['end']),
            ])

            chart_opps_count.append(len(m_opps))
            chart_revenue.append(round(sum(m_opps.mapped('expected_revenue')), 2))
            chart_won_count.append(len(m_won))

        # Pipeline by Stage
        stages_data = []
        if 'crm.stage' in self.env:
            stages = self.env['crm.stage'].search([], order='sequence, id')
            for st in stages:
                st_opps = Lead.search(base_domain + [('stage_id', '=', st.id)])
                st_count = len(st_opps)
                st_rev = sum(st_opps.mapped('expected_revenue'))
                pct = round((st_rev / total_expected_revenue * 100), 1) if total_expected_revenue > 0 else 0.0
                stages_data.append({
                    'id': st.id,
                    'name': st.name,
                    'count': st_count,
                    'revenue': round(st_rev, 2),
                    'pct': pct,
                    'is_won': st.is_won,
                })

        # Top Salespersons
        salesperson_rev = defaultdict(float)
        salesperson_cnt = defaultdict(int)
        for opp in active_opps:
            uname = opp.user_id.name if opp.user_id else 'Unassigned'
            salesperson_rev[uname] += opp.expected_revenue
            salesperson_cnt[uname] += 1

        top_salespersons = sorted(salesperson_rev.items(), key=lambda x: -x[1])[:5]
        top_sp_data = [{
            'name': k,
            'revenue': round(v, 2),
            'count': salesperson_cnt[k]
        } for k, v in top_salespersons]

        # Recent opportunities (last 10)
        recent_opps = Lead.search(base_domain, order='id desc', limit=10)
        recent = []
        for o in recent_opps:
            recent.append({
                'id': o.id,
                'name': o.name,
                'partner': o.partner_id.name or 'N/A',
                'revenue': round(o.expected_revenue, 2),
                'stage': o.stage_id.name or 'N/A',
                'probability': round(o.probability, 1),
                'user': o.user_id.name or 'Unassigned',
                'deadline': o.date_deadline.strftime('%d %b %Y') if o.date_deadline else '',
            })

        return {
            'total_opps': total_opps_count,
            'total_expected_revenue': round(total_expected_revenue, 2),
            'total_prorated_revenue': round(total_prorated_revenue, 2),
            'won_count': won_count,
            'won_revenue': round(won_revenue, 2),
            'lost_count': lost_count,
            'pipeline_count': pipeline_count,
            'win_rate': win_rate,
            'avg_deal_size': avg_deal_size,
            'overdue_count': overdue_count,
            'today_count': today_count,
            'currency_symbol': currency_symbol,
            'chart_labels': chart_labels,
            'chart_opps_count': chart_opps_count,
            'chart_revenue': chart_revenue,
            'chart_won_count': chart_won_count,
            'stages': stages_data,
            'top_salespersons': top_sp_data,
            'recent_opps': recent,
        }

    # -------------------------------------------------------------------------
    # Manufacturing KPIs
    # -------------------------------------------------------------------------

    @api.model
    def get_manufacturing_data(self):
        if 'mrp.production' not in self.env:
            return {}
        MO = self.env['mrp.production']

        draft_count     = MO.search_count([('state', '=', 'draft')])
        confirmed_count = MO.search_count([('state', '=', 'confirmed')])
        progress_count  = MO.search_count([('state', 'in', ['progress', 'to_close'])])
        done_count      = MO.search_count([('state', '=', 'done')])
        cancel_count    = MO.search_count([('state', '=', 'cancel')])
        total_count     = draft_count + confirmed_count + progress_count + done_count + cancel_count

        today = date.today()
        overdue_count = MO.search_count([
            ('state', 'not in', ['done', 'cancel']),
            ('date_finished', '<', fields.Datetime.now()),
            ('date_finished', '!=', False),
        ])
        today_count = MO.search_count([
            ('date_start', '>=', fields.Datetime.to_datetime(str(today) + ' 00:00:00')),
            ('date_start', '<=', fields.Datetime.to_datetime(str(today) + ' 23:59:59')),
        ])

        # This month done
        month_start = today.replace(day=1)
        month_done = MO.search_count([
            ('state', '=', 'done'),
            ('date_finished', '>=', fields.Datetime.to_datetime(str(month_start) + ' 00:00:00')),
        ])

        # Monthly chart data
        months = self._get_month_labels(6)
        chart_labels    = [m['label'] for m in months]
        chart_confirmed = []
        chart_done_list = []
        for m in months:
            chart_confirmed.append(MO.search_count([
                ('state', 'in', ['confirmed', 'progress', 'to_close']),
                ('date_start', '>=', m['start']),
                ('date_start', '<=', m['end']),
            ]))
            chart_done_list.append(MO.search_count([
                ('state', '=', 'done'),
                ('date_finished', '>=', m['start']),
                ('date_finished', '<=', m['end']),
            ]))

        # Recent manufacturing orders (last 10)
        recent_orders = MO.search([], order='id desc', limit=10)
        recent = []
        for o in recent_orders:
            recent.append({
                'id': o.id,
                'name': o.name,
                'product': o.product_id.display_name or '',
                'qty': o.product_qty,
                'uom': o.product_uom_id.name or '',
                'state': o.state,
                'state_label': dict(o._fields['state'].selection).get(o.state, o.state),
                'date': o.date_start.strftime('%d %b %Y') if o.date_start else '',
                'workcenter': o.workorder_ids[0].workcenter_id.name if o.workorder_ids else '',
            })

        # Workcenter utilization (top 5 by workorder count)
        WorkOrder = self.env['mrp.workorder']
        workcenters_data = []
        for wc in self.env['mrp.workcenter'].search([], limit=5):
            wc_count = WorkOrder.search_count([('workcenter_id', '=', wc.id)])
            wc_done  = WorkOrder.search_count([('workcenter_id', '=', wc.id), ('state', '=', 'done')])
            if wc_count:
                workcenters_data.append({
                    'name': wc.name,
                    'total': wc_count,
                    'done': wc_done,
                    'pct': round(wc_done / wc_count * 100) if wc_count else 0,
                })

        return {
            'draft': draft_count,
            'confirmed': confirmed_count,
            'progress': progress_count,
            'done': done_count,
            'cancel': cancel_count,
            'total': total_count,
            'overdue': overdue_count,
            'today': today_count,
            'month_done': month_done,
            'chart_labels': chart_labels,
            'chart_confirmed': chart_confirmed,
            'chart_done': chart_done_list,
            'recent_orders': recent,
            'workcenters': workcenters_data,
        }

    # -------------------------------------------------------------------------
    # Sales KPIs
    # -------------------------------------------------------------------------

    @api.model
    def get_sales_data(self):
        if 'sale.order' not in self.env:
            return {}
        SO = self.env['sale.order']

        quotation_count = SO.search_count([('state', '=', 'draft')])
        sent_count      = SO.search_count([('state', '=', 'sent')])
        sale_count      = SO.search_count([('state', '=', 'sale')])
        done_count      = SO.search_count([('state', '=', 'done')])
        cancel_count    = SO.search_count([('state', '=', 'cancel')])
        total_count     = quotation_count + sent_count + sale_count + done_count + cancel_count

        confirmed_orders = SO.search([('state', 'in', ['sale', 'done'])])
        confirmed_amount = sum(confirmed_orders.mapped('amount_total'))

        to_invoice_count = SO.search_count([
            ('state', 'in', ['sale', 'done']),
            ('invoice_status', '=', 'to invoice'),
        ])
        overdue_count = SO.search_count([
            ('state', 'in', ['draft', 'sent', 'sale']),
            ('commitment_date', '<', fields.Datetime.now()),
            ('commitment_date', '!=', False),
        ])

        today      = date.today()
        month_start = today.replace(day=1)
        month_orders = SO.search([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', fields.Datetime.to_datetime(str(month_start) + ' 00:00:00')),
        ])
        month_amount = sum(month_orders.mapped('amount_total'))
        month_count  = len(month_orders)

        # Average order value
        avg_order_val = round(confirmed_amount / len(confirmed_orders), 2) if confirmed_orders else 0.0

        # Top 5 customers by order total
        customer_totals = defaultdict(float)
        for o in confirmed_orders:
            customer_totals[o.partner_id.name or 'Unknown'] += o.amount_total
        top_customers = sorted(customer_totals.items(), key=lambda x: -x[1])[:5]

        # Monthly chart data
        months = self._get_month_labels(6)
        chart_labels = [m['label'] for m in months]
        chart_orders = []
        chart_amount = []
        for m in months:
            mo = SO.search([
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', m['start']),
                ('date_order', '<=', m['end']),
            ])
            chart_orders.append(len(mo))
            chart_amount.append(round(sum(mo.mapped('amount_total')), 2))

        # Recent orders (last 10)
        recent_so = SO.search([], order='id desc', limit=10)
        recent = []
        for o in recent_so:
            recent.append({
                'id': o.id,
                'name': o.name,
                'partner': o.partner_id.name or '',
                'amount': round(o.amount_total, 2),
                'state': o.state,
                'state_label': dict(o._fields['state'].selection).get(o.state, o.state),
                'date': o.date_order.strftime('%d %b %Y') if o.date_order else '',
                'invoice_status': o.invoice_status,
            })

        currency_symbol = self.env.company.currency_id.symbol or '$'

        return {
            'quotation': quotation_count,
            'sent': sent_count,
            'sale': sale_count,
            'done': done_count,
            'cancel': cancel_count,
            'total': total_count,
            'confirmed_amount': confirmed_amount,
            'to_invoice': to_invoice_count,
            'overdue': overdue_count,
            'month_amount': month_amount,
            'month_count': month_count,
            'avg_order_val': avg_order_val,
            'currency_symbol': currency_symbol,
            'chart_labels': chart_labels,
            'chart_orders': chart_orders,
            'chart_amount': chart_amount,
            'recent_orders': recent,
            'top_customers': [{'name': k, 'amount': v} for k, v in top_customers],
        }

    # -------------------------------------------------------------------------
    # Purchase KPIs
    # -------------------------------------------------------------------------

    @api.model
    def get_purchase_data(self):
        if 'purchase.order' not in self.env:
            return {}
        PO = self.env['purchase.order']

        draft_count    = PO.search_count([('state', '=', 'draft')])
        sent_count     = PO.search_count([('state', '=', 'sent')])
        purchase_count = PO.search_count([('state', '=', 'purchase')])
        done_count     = PO.search_count([('state', '=', 'done')])
        cancel_count   = PO.search_count([('state', '=', 'cancel')])
        total_count    = draft_count + sent_count + purchase_count + done_count + cancel_count

        confirmed_orders = PO.search([('state', 'in', ['purchase', 'done'])])
        confirmed_amount = sum(confirmed_orders.mapped('amount_total'))

        to_bill_count = PO.search_count([
            ('state', 'in', ['purchase', 'done']),
            ('invoice_status', '=', 'to invoice'),
        ])
        today       = date.today()
        month_start = today.replace(day=1)
        overdue_count = PO.search_count([
            ('state', 'in', ['draft', 'sent', 'purchase']),
            ('date_planned', '<', fields.Datetime.now()),
            ('date_planned', '!=', False),
        ])
        month_orders = PO.search([
            ('state', 'in', ['purchase', 'done']),
            ('date_order', '>=', fields.Datetime.to_datetime(str(month_start) + ' 00:00:00')),
        ])
        month_amount = sum(month_orders.mapped('amount_total'))
        month_count  = len(month_orders)

        # Average order value
        avg_order_val = round(confirmed_amount / len(confirmed_orders), 2) if confirmed_orders else 0.0

        # Top 5 vendors by purchase total
        vendor_totals = defaultdict(float)
        for o in confirmed_orders:
            vendor_totals[o.partner_id.name or 'Unknown'] += o.amount_total
        top_vendors = sorted(vendor_totals.items(), key=lambda x: -x[1])[:5]

        # Monthly chart data
        months = self._get_month_labels(6)
        chart_labels = [m['label'] for m in months]
        chart_orders = []
        chart_amount = []
        for m in months:
            po = PO.search([
                ('state', 'in', ['purchase', 'done']),
                ('date_order', '>=', m['start']),
                ('date_order', '<=', m['end']),
            ])
            chart_orders.append(len(po))
            chart_amount.append(round(sum(po.mapped('amount_total')), 2))

        # Recent orders (last 10)
        recent_po = PO.search([], order='id desc', limit=10)
        recent = []
        for o in recent_po:
            recent.append({
                'id': o.id,
                'name': o.name,
                'partner': o.partner_id.name or '',
                'amount': round(o.amount_total, 2),
                'state': o.state,
                'state_label': dict(o._fields['state'].selection).get(o.state, o.state),
                'date': o.date_order.strftime('%d %b %Y') if o.date_order else '',
                'invoice_status': o.invoice_status,
            })

        currency_symbol = self.env.company.currency_id.symbol or '$'

        return {
            'draft': draft_count,
            'sent': sent_count,
            'purchase': purchase_count,
            'done': done_count,
            'cancel': cancel_count,
            'total': total_count,
            'confirmed_amount': confirmed_amount,
            'to_bill': to_bill_count,
            'overdue': overdue_count,
            'month_amount': month_amount,
            'month_count': month_count,
            'avg_order_val': avg_order_val,
            'currency_symbol': currency_symbol,
            'chart_labels': chart_labels,
            'chart_orders': chart_orders,
            'chart_amount': chart_amount,
            'recent_orders': recent,
            'top_vendors': [{'name': k, 'amount': v} for k, v in top_vendors],
        }

    # -------------------------------------------------------------------------
    # Accounting / Invoice KPIs
    # -------------------------------------------------------------------------

    @api.model
    def get_accounting_data(self):
        if 'account.move' not in self.env:
            return {}
        Move = self.env['account.move']
        today = date.today()
        currency_symbol = self.env.company.currency_id.symbol or '$'

        # ── Customer Invoices ──────────────────────────────────────────────
        inv_domain = [('move_type', '=', 'out_invoice'), ('state', '!=', 'cancel')]
        inv_total      = Move.search_count(inv_domain)
        inv_draft      = Move.search_count(inv_domain + [('state', '=', 'draft')])
        inv_posted     = Move.search_count(inv_domain + [('state', '=', 'posted')])
        inv_paid       = Move.search_count(inv_domain + [('state', '=', 'posted'), ('payment_state', '=', 'paid')])
        inv_overdue    = Move.search_count(inv_domain + [
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment']),
            ('invoice_date_due', '<', today),
        ])
        inv_to_pay     = Move.search_count(inv_domain + [
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment']),
        ])

        # Total receivable (unpaid posted invoices)
        posted_inv = Move.search(inv_domain + [
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment']),
        ])
        total_receivable = sum(posted_inv.mapped('amount_residual'))

        # ── Vendor Bills ───────────────────────────────────────────────────
        bill_domain = [('move_type', '=', 'in_invoice'), ('state', '!=', 'cancel')]
        bill_total   = Move.search_count(bill_domain)
        bill_draft   = Move.search_count(bill_domain + [('state', '=', 'draft')])
        bill_posted  = Move.search_count(bill_domain + [('state', '=', 'posted')])
        bill_paid    = Move.search_count(bill_domain + [('state', '=', 'posted'), ('payment_state', '=', 'paid')])
        bill_overdue = Move.search_count(bill_domain + [
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment']),
            ('invoice_date_due', '<', today),
        ])

        posted_bills = Move.search(bill_domain + [
            ('state', '=', 'posted'),
            ('payment_state', 'not in', ['paid', 'in_payment']),
        ])
        total_payable = sum(posted_bills.mapped('amount_residual'))

        # ── This month invoiced ────────────────────────────────────────────
        month_start = today.replace(day=1)
        month_end   = (month_start + relativedelta(months=1)) - timedelta(days=1)
        month_inv   = Move.search(inv_domain + [
            ('state', '=', 'posted'),
            ('invoice_date', '>=', str(month_start)),
            ('invoice_date', '<=', str(month_end)),
        ])
        month_invoiced = sum(month_inv.mapped('amount_total'))
        month_inv_count = len(month_inv)

        # ── 6-month chart ──────────────────────────────────────────────────
        months = self._get_month_labels(6)
        chart_labels = [m['label'] for m in months]
        chart_inv_amount = []
        chart_bill_amount = []
        chart_inv_count = []

        for m in months:
            inv_m = Move.search(inv_domain + [
                ('state', '=', 'posted'),
                ('invoice_date', '>=', m['start'].date()),
                ('invoice_date', '<=', m['end'].date()),
            ])
            bill_m = Move.search(bill_domain + [
                ('state', '=', 'posted'),
                ('invoice_date', '>=', m['start'].date()),
                ('invoice_date', '<=', m['end'].date()),
            ])
            chart_inv_amount.append(round(sum(inv_m.mapped('amount_total')), 2))
            chart_bill_amount.append(round(sum(bill_m.mapped('amount_total')), 2))
            chart_inv_count.append(len(inv_m))

        # ── Recent customer invoices ───────────────────────────────────────
        recent_moves = Move.search(
            inv_domain + [('state', 'in', ['draft', 'posted'])],
            order='invoice_date desc, id desc', limit=10
        )
        recent = []
        state_labels = {'draft': 'Draft', 'posted': 'Posted', 'cancel': 'Cancelled'}
        pay_labels = {
            'not_paid': 'Not Paid', 'in_payment': 'In Payment',
            'paid': 'Paid', 'partial': 'Partial',
        }
        for m in recent_moves:
            recent.append({
                'id': m.id,
                'name': m.name or '/',
                'partner': m.partner_id.name or '',
                'amount': round(m.amount_total, 2),
                'date': str(m.invoice_date or ''),
                'due': str(m.invoice_date_due or ''),
                'state': m.state,
                'state_label': state_labels.get(m.state, m.state),
                'pay_state': m.payment_state,
                'pay_label': pay_labels.get(m.payment_state, m.payment_state),
                'overdue': bool(
                    m.state == 'posted'
                    and m.payment_state not in ('paid', 'in_payment')
                    and m.invoice_date_due
                    and m.invoice_date_due < today
                ),
            })

        # ── Top 5 customers by receivable ─────────────────────────────────
        customer_totals = defaultdict(float)
        for m in posted_inv:
            customer_totals[m.partner_id.name or 'Unknown'] += m.amount_residual
        top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:5]

        # ── Odoo Native Journal Graphs ────────────────────────────────────
        journals = self.env['account.journal'].search([('type', 'in', ('sale', 'purchase', 'bank', 'cash'))])
        journal_graphs = []
        for j in journals:
            if j.kanban_dashboard_graph:
                try:
                    graph_data = json.loads(j.kanban_dashboard_graph)
                    name = f"{j.name} ({j.company_id.name or 'Unknown'})" if len(self.env.companies) > 1 else j.name
                    journal_graphs.append({
                        'id': j.id,
                        'name': name,
                        'type': j.type,
                        'graph_data': graph_data
                    })
                except Exception:
                    pass

        return {
            # Invoice state counts
            'inv_total': inv_total,
            'inv_draft': inv_draft,
            'inv_posted': inv_posted,
            'inv_paid': inv_paid,
            'inv_overdue': inv_overdue,
            'inv_to_pay': inv_to_pay,
            # Bill state counts
            'bill_total': bill_total,
            'bill_draft': bill_draft,
            'bill_posted': bill_posted,
            'bill_paid': bill_paid,
            'bill_overdue': bill_overdue,
            # Summary amounts
            'total_receivable': round(total_receivable, 2),
            'total_payable': round(total_payable, 2),
            'net_balance': round(total_receivable - total_payable, 2),
            'month_invoiced': round(month_invoiced, 2),
            'month_inv_count': month_inv_count,
            # Chart
            'chart_labels': chart_labels,
            'chart_inv_amount': chart_inv_amount,
            'chart_bill_amount': chart_bill_amount,
            'chart_inv_count': chart_inv_count,
            # Lists
            'recent_invoices': recent,
            'top_customers': [{'name': k, 'amount': round(v, 2)} for k, v in top_customers],
            'journal_graphs': journal_graphs,
            'currency_symbol': currency_symbol,
        }

    @api.model
    def get_inventory_data(self):
        """ Fetch data for Inventory overview dashboard (Receipts, Deliveries, etc.) """
        if 'stock.picking.type' not in self.env:
            return {}
        picking_types = self.env['stock.picking.type'].search([])
        inventory_graphs = []
        
        # Calculate overall inventory valuation (if stock.valuation.layer exists, else 0)
        total_valuation = 0
        if 'stock.valuation.layer' in self.env:
            layers = self.env['stock.valuation.layer'].search([('company_id', 'in', self.env.companies.ids)])
            total_valuation = sum(layers.mapped('value'))
            
        # Overall transfer counters
        today = date.today()
        Move = self.env['stock.picking']
        domain = [('company_id', 'in', self.env.companies.ids), ('state', 'not in', ('cancel', 'done'))]
        
        total_transfers = Move.search_count(domain)
        late_transfers = Move.search_count(domain + [('scheduled_date', '<', today)])
        draft_transfers = Move.search_count([('company_id', 'in', self.env.companies.ids), ('state', '=', 'draft')])

        for pt in picking_types:
            graph_data = []
            if pt.kanban_dashboard_graph:
                try:
                    graph_data = json.loads(pt.kanban_dashboard_graph)
                except Exception:
                    pass
            
            name = f"{pt.name} ({pt.company_id.name or 'Unknown'})" if len(self.env.companies) > 1 else pt.name
            
            inventory_graphs.append({
                'id': pt.id,
                'name': name,
                'code': pt.code,
                'count_ready': pt.count_picking_ready,
                'count_waiting': pt.count_picking_waiting,
                'count_late': pt.count_picking_late,
                'count_backorders': pt.count_picking_backorders,
                'count_move_ready': pt.count_move_ready,
                'graph_data': graph_data
            })
            
        # Recent Transfers
        recent_pickings = Move.search(
            [('company_id', 'in', self.env.companies.ids)], 
            order='date desc', 
            limit=7
        )
        recent_pickings_data = []
        for p in recent_pickings:
            recent_pickings_data.append({
                'id': p.id,
                'name': p.name,
                'partner': p.partner_id.name or 'N/A',
                'scheduled_date': p.scheduled_date.strftime('%Y-%m-%d') if p.scheduled_date else '',
                'state': p.state,
                'type': p.picking_type_id.name
            })
            
        # Low Stock Alerts (Products with qty <= 0)
        low_stock_products = self.env['product.product'].search(
            [('is_storable', '=', True), ('qty_available', '<=', 0)], 
            limit=6
        )
        low_stock_data = []
        for product in low_stock_products:
            low_stock_data.append({
                'id': product.id,
                'name': product.display_name,
                'qty': product.qty_available,
                'uom': product.uom_id.name
            })
            
        currency = self.env.company.currency_id.symbol or '$'
        return {
            'inventory_graphs': inventory_graphs,
            'total_valuation': round(total_valuation, 2),
            'total_transfers': total_transfers,
            'late_transfers': late_transfers,
            'draft_transfers': draft_transfers,
            'currency_symbol': currency,
            'recent_transfers': recent_pickings_data,
            'low_stock': low_stock_data
        }
