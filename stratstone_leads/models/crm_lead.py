from odoo import api, fields, models, _
import requests
from datetime import datetime, timedelta, timezone, time, date
from odoo.exceptions import UserError
import json
import logging
import pytz

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    # -------------------------
    # Meta Lead Ads Fields
    # -------------------------
    meta_lead_id = fields.Char(
        string="Meta Lead ID", index=True, readonly=True, copy=False,
    )
    meta_form_id = fields.Char(
        string="Meta Form ID", index=True, readonly=True, copy=False,
    )
    meta_ad_id = fields.Char(
        string="Meta Ad ID", index=True, readonly=True, copy=False,
    )
    meta_ad_name = fields.Char(
        string="Meta Ad Name", readonly=True, copy=False,
    )
    meta_adset_id = fields.Char(
        string="Meta Ad Set ID", readonly=True, copy=False,
    )
    meta_adset_name = fields.Char(
        string="Meta Ad Set Name", readonly=True, copy=False,
    )
    meta_campaign_id = fields.Char(
        string="Meta Campaign ID", index=True, readonly=True, copy=False,
    )
    meta_campaign_name = fields.Char(
        string="Meta Campaign Name", readonly=True, copy=False,
    )
    meta_created_time = fields.Datetime(
        string="Meta Created Time", readonly=True, copy=False,
    )
    meta_raw_payload = fields.Text(
        string="Meta Raw Payload", readonly=True, copy=False,
    )

    # Custom Property Fields
    bhk = fields.Char(string="BHK")
    possession = fields.Char(string="Possession")
    location = fields.Char(string="Location")

    _sql_constraints = [
        ('uniq_meta_lead_id', 'unique(meta_lead_id)',
         'Meta lead already exists in CRM.'),
    ]

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    @api.model
    def _meta_leadads_get_config(self):
        """Read Meta Lead Ads configuration from ir.config_parameter."""
        def _param_to_str(v):
            if v is None or v is False:
                return ''
            if isinstance(v, bool):
                return ''
            return str(v).strip()

        params = self.env['ir.config_parameter'].sudo()
        page_id = _param_to_str(
            params.get_param('stratstone_leads.meta_leadads_page_id'))
        access_token = _param_to_str(
            params.get_param('stratstone_leads.meta_leadads_access_token'))
        form_ids_raw = _param_to_str(
            params.get_param('stratstone_leads.meta_leadads_form_ids'))

        form_ids = [x.strip() for x in form_ids_raw.split(',')
                    if x.strip()] if form_ids_raw else []
        return page_id, access_token, form_ids

    # ------------------------------------------------------------------
    # Graph API helpers
    # ------------------------------------------------------------------
    @api.model
    def _meta_graph_get(self, path, access_token, params=None, timeout=30):
        """GET https://graph.facebook.com/v24.0/{path}"""
        if not access_token:
            raise UserError(_("Meta access token is not configured."))
        url = f"https://graph.facebook.com/v24.0/{path.lstrip('/')}"
        q = dict(params or {})
        q['access_token'] = access_token
        try:
            resp = requests.get(url, params=q, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise UserError(_("Meta Graph API error: %s") % str(e))

        if isinstance(data, dict) and data.get('error'):
            raise UserError(
                _("Meta Graph API error: %s") % data['error'])
        return data

    @api.model
    def _meta_graph_paged(self, path, access_token, params=None,
                          timeout=30, max_pages=200):
        """
        Iterate Graph API 'data' items across cursor pagination.
        Uses 'paging.cursors.after' (keeps requests within the same endpoint).
        """
        after = None
        pages = 0
        while pages < max_pages:
            q = dict(params or {})
            if after:
                q['after'] = after
            payload = self._meta_graph_get(
                path, access_token, params=q, timeout=timeout)
            for item in (payload.get('data') or []):
                yield item
            paging = (payload or {}).get('paging') or {}
            cursors = (paging or {}).get('cursors') or {}
            after = cursors.get('after')
            pages += 1
            if not after:
                break

    @api.model
    def _meta_get_page_access_token(self, page_id, user_or_page_token):
        """
        If the configured token is a user token, fetch the page token via:
        GET /{page_id}?fields=access_token&access_token={user_token}
        """
        if not page_id or not user_or_page_token:
            return user_or_page_token
        try:
            data = self._meta_graph_get(
                f"{page_id}",
                user_or_page_token,
                params={"fields": "access_token"},
            )
            page_token = (data or {}).get("access_token")
            return page_token or user_or_page_token
        except Exception:
            return user_or_page_token

    # ------------------------------------------------------------------
    # Form listing (manual helper)
    # ------------------------------------------------------------------
    @api.model
    def meta_leadads_list_forms(self):
        """Fetch ALL forms for configured page_id."""
        page_id, access_token, _form_ids = self._meta_leadads_get_config()
        if not page_id:
            raise UserError(_("Meta Page ID is not configured."))
        page_token = self._meta_get_page_access_token(page_id, access_token)
        forms = list(self._meta_graph_paged(
            f"{page_id}/leadgen_forms",
            page_token,
            params={
                "fields": "id,name,status,locale,created_time",
                "limit": 100,
            },
            max_pages=50,
        ))
        return forms

    # ------------------------------------------------------------------
    # Data parsing helpers
    # ------------------------------------------------------------------
    @api.model
    def _meta_parse_created_time(self, created_time_str):
        if not created_time_str:
            return False
        try:
            dt = datetime.strptime(created_time_str, '%Y-%m-%dT%H:%M:%S%z')
            dt_utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt_utc
        except Exception:
            return False

    @api.model
    def _meta_field_data_to_dict(self, field_data):
        """Convert Graph lead field_data [{name, values:[...]}] -> {name: first_value}"""
        res = {}
        for item in field_data or []:
            name = (item or {}).get('name')
            values = (item or {}).get('values') or []
            if not name:
                continue
            res[name] = values[0] if values else False
        return res

    @api.model
    def _meta_build_description(self, lead_json, fields_map):
        """Build a human-readable description from the Meta lead payload."""
        lines = [
            "Source: Meta Lead Ads",
            f"Meta Lead ID: {lead_json.get('id')}",
            f"Meta Form ID: {lead_json.get('form_id')}",
            f"Meta Campaign: {lead_json.get('campaign_name') or lead_json.get('campaign_id') or 'N/A'}",
            f"Meta Ad Set: {lead_json.get('adset_name') or lead_json.get('adset_id') or 'N/A'}",
            f"Meta Ad: {lead_json.get('ad_name') or lead_json.get('ad_id') or 'N/A'}",
            f"Created: {lead_json.get('created_time')}",
            "",
            "Field Data:",
        ]
        for k, v in sorted(fields_map.items(), key=lambda x: x[0]):
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)

    @api.model
    def _meta_get_or_create_utm_source(self, name):
        """Find or create a utm.source record by name."""
        name = (name or '').strip()
        if not name:
            return False
        src = self.env['utm.source'].sudo().search(
            [('name', '=', name)], limit=1)
        if not src:
            src = self.env['utm.source'].sudo().create({'name': name})
        return src.id

    @api.model
    def _meta_get_or_create_utm_campaign(self, name):
        """Find or create a utm.campaign record by name."""
        name = (name or '').strip()
        if not name:
            return False
        camp = self.env['utm.campaign'].sudo().search(
            [('name', '=', name)], limit=1)
        if not camp:
            camp = self.env['utm.campaign'].sudo().create({'name': name})
        return camp.id

    @api.model
    def _meta_get_or_create_utm_medium(self, name='Paid Social'):
        """Find or create a utm.medium record by name."""
        name = (name or '').strip()
        if not name:
            return False
        med = self.env['utm.medium'].sudo().search(
            [('name', '=', name)], limit=1)
        if not med:
            med = self.env['utm.medium'].sudo().create({'name': name})
        return med.id

    @api.model
    def _get_next_round_robin_salesperson(self):
        """
        Get the next salesperson and sales team for round-robin lead assignment.
        Target Sales Team: sales_team.team_sales_department (or crm.team search fallback)
        Returns: (user_id or False, team_id or False)
        """
        team = self.env.ref('sales_team.team_sales_department', raise_if_not_found=False)
        if not team:
            team = self.env['crm.team'].sudo().search([
                ('name', 'ilike', 'Sales Department')
            ], limit=1)
        if not team:
            team = self.env['crm.team'].sudo().search([], limit=1)

        if not team:
            return False, False

        members = self.env['res.users']
        if hasattr(team, 'member_ids') and team.member_ids:
            members = team.member_ids.filtered(lambda u: u.active)
        if not members and hasattr(team, 'crm_team_member_ids') and team.crm_team_member_ids:
            members = team.crm_team_member_ids.mapped('user_id').filtered(lambda u: u.active)

        if not members:
            return False, team.id

        member_ids = sorted(members.ids)

        params = self.env['ir.config_parameter'].sudo()
        param_key = 'stratstone_leads.last_assigned_user_id'
        last_assigned_id_raw = params.get_param(param_key, default=False)

        last_assigned_id = int(last_assigned_id_raw) if last_assigned_id_raw and str(last_assigned_id_raw).isdigit() else 0

        if last_assigned_id in member_ids:
            last_index = member_ids.index(last_assigned_id)
            next_index = (last_index + 1) % len(member_ids)
        else:
            next_index = 0

        next_user_id = member_ids[next_index]
        params.set_param(param_key, str(next_user_id))

        return next_user_id, team.id

    # ------------------------------------------------------------------
    # Main sync logic
    # ------------------------------------------------------------------
    @api.model
    def meta_leadads_sync_leads(self, limit=25, max_pages=50):
        """
        Sync leads for configured form ids:
        GET /{form_id}/leads?fields=created_time,id,ad_id,form_id,field_data
        """
        page_id, access_token, form_ids = self._meta_leadads_get_config()
        if not access_token:
            raise UserError(
                _("Meta access token is not configured in Settings."))

        # Prefer using a Page token for leadgen endpoints.
        page_token = self._meta_get_page_access_token(page_id, access_token)

        if not form_ids:
            if not page_id:
                raise UserError(
                    _("Meta Page ID is not configured in Settings."))
            forms = self.meta_leadads_list_forms()
            form_ids = [f.get('id') for f in forms if f.get('id')]
            if not form_ids:
                raise UserError(
                    _("No leadgen forms found for this Meta Page ID."))

        # Optional date range filtering (inclusive)
        date_from = self.env.context.get('meta_date_from')
        date_to = self.env.context.get('meta_date_to')
        start_dt_utc = end_dt_utc = False

        def _to_date(v):
            if not v:
                return False
            if isinstance(v, date):
                return v
            if isinstance(v, str):
                return fields.Date.from_string(v)
            return v

        date_from = _to_date(date_from)
        date_to = _to_date(date_to)
        if date_from and not date_to:
            date_to = date_from
        if date_to and not date_from:
            date_from = date_to

        if date_from and date_to:
            if date_from > date_to:
                raise UserError(_("Start date cannot be after end date."))
            tzname = self.env.user.tz or 'UTC'
            tz = pytz.timezone(tzname)
            local_start = tz.localize(datetime.combine(date_from, time.min))
            local_end = tz.localize(datetime.combine(date_to, time.max))
            start_dt_utc = local_start.astimezone(pytz.UTC).replace(
                tzinfo=None)
            end_dt_utc = local_end.astimezone(pytz.UTC).replace(tzinfo=None)

        params_store = self.env['ir.config_parameter'].sudo()
        last_sync_dt = False
        if not (start_dt_utc and end_dt_utc):
            last_sync_raw = params_store.get_param(
                'stratstone_leads.meta_leadads_last_sync') or ''
            if isinstance(last_sync_raw, bool):
                last_sync_raw = ''
            last_sync_raw = str(last_sync_raw).strip()
            if last_sync_raw:
                try:
                    last_sync_dt = fields.Datetime.from_string(last_sync_raw)
                except Exception:
                    last_sync_dt = False

        created = 0
        updated = 0
        skipped = 0

        # Always attribute Meta imports to Facebook UTM source
        fb_source = self.env.ref(
            'utm.utm_source_facebook', raise_if_not_found=False)

        for form_id in form_ids:
            after = None
            pages = 0
            stop_for_form = False
            while not stop_for_form and pages < max_pages:
                q = {
                    "fields": "created_time,id,ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,form_id,form_name,field_data",
                    "limit": int(limit),
                }
                if after:
                    q["after"] = after
                data = self._meta_graph_get(
                    f"{form_id}/leads", page_token, params=q)
                leads = data.get('data') or []

                for lead_json in leads:
                    meta_lead_id = lead_json.get('id')
                    if not meta_lead_id:
                        continue

                    created_time = self._meta_parse_created_time(
                        lead_json.get('created_time'))
                    if created_time:
                        if start_dt_utc and end_dt_utc:
                            if created_time < start_dt_utc:
                                stop_for_form = True
                                break
                            if created_time > end_dt_utc:
                                skipped += 1
                                continue
                        elif last_sync_dt and created_time <= last_sync_dt:
                            stop_for_form = True
                            break

                    fields_map = self._meta_field_data_to_dict(
                        lead_json.get('field_data'))

                    # Generic field extraction
                    full_name = (fields_map.get('full_name')
                                 or fields_map.get('name'))
                    email = fields_map.get('email')
                    phone = (fields_map.get('phone_number')
                             or fields_map.get('phone'))
                    city = fields_map.get('city')
                    zip_code = (fields_map.get('zip_code')
                                or fields_map.get('zip'))
                    bhk_val = (fields_map.get('bhk')
                               or fields_map.get('configuration'))
                    possession_val = (fields_map.get('possession')
                                      or fields_map.get('posation'))

                    lead_name = full_name or f"Meta Lead {meta_lead_id}"

                    existing = self.search(
                        [('meta_lead_id', '=', meta_lead_id)], limit=1)

                    if existing:
                        user_id = existing.user_id.id if existing.user_id else False
                        team_id = existing.team_id.id if existing.team_id else False
                        if not user_id:
                            user_id, team_id = self._get_next_round_robin_salesperson()
                    else:
                        user_id, team_id = self._get_next_round_robin_salesperson()

                    campaign_name = lead_json.get('campaign_name')
                    campaign_id = self._meta_get_or_create_utm_campaign(campaign_name) if campaign_name else False
                    medium_id = self._meta_get_or_create_utm_medium('Paid Social')

                    vals = {
                        "type": "opportunity",
                        "name": lead_name,
                        "contact_name": full_name,
                        "email_from": email,
                        "phone": phone,
                        "city": city,
                        "zip": zip_code,
                        "bhk": bhk_val or False,
                        "possession": possession_val or False,
                        "user_id": user_id,
                        "team_id": team_id,
                        "campaign_id": campaign_id,
                        "medium_id": medium_id,
                        "source_id": (
                            fb_source.id if fb_source
                            else self._meta_get_or_create_utm_source(
                                'Facebook')),
                        "meta_lead_id": meta_lead_id,
                        "meta_form_id": (lead_json.get('form_id')
                                         or form_id),
                        "meta_ad_id": lead_json.get('ad_id'),
                        "meta_ad_name": lead_json.get('ad_name'),
                        "meta_adset_id": lead_json.get('adset_id'),
                        "meta_adset_name": lead_json.get('adset_name'),
                        "meta_campaign_id": lead_json.get('campaign_id'),
                        "meta_campaign_name": campaign_name,
                        "meta_created_time": created_time,
                        "meta_raw_payload": json.dumps(
                            lead_json, ensure_ascii=False),
                        "description": self._meta_build_description(
                            lead_json, fields_map),
                    }

                    if existing:
                        existing.write(vals)
                        updated += 1
                    else:
                        try:
                            self.create(vals)
                            created += 1
                        except Exception as e:
                            _logger.warning(
                                "Meta lead create failed for %s: %s",
                                meta_lead_id, e)
                            skipped += 1

                paging = (data or {}).get('paging') or {}
                cursors = paging.get('cursors') or {}
                after = cursors.get('after')
                pages += 1
                if not after:
                    break

        # Update last_sync timestamp for incremental mode.
        params_store.set_param(
            'stratstone_leads.meta_leadads_last_sync',
            fields.Datetime.to_string(fields.Datetime.now()))
        return {"created": created, "updated": updated, "skipped": skipped}

    @api.model
    def _cron_meta_leadads_sync_leads(self):
        """Cron entrypoint — syncs today's leads."""
        today = fields.Date.context_today(self)
        self.with_context(
            meta_date_from=today, meta_date_to=today
        ).meta_leadads_sync_leads()
