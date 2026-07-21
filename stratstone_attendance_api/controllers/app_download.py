# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.http import request


class AppDownloadController(http.Controller):

    @http.route(['/download-app', '/app/download'], type='http', auth='public', website=True, sitemap=True)
    def download_app_page(self, **kwargs):
        ICP = request.env['ir.config_parameter'].sudo()
        playstore_url = ICP.get_param('stratstone_attendance_api.playstore_url', default='')
        appstore_url = ICP.get_param('stratstone_attendance_api.appstore_url', default='')

        values = {
            'playstore_url': playstore_url.strip() if playstore_url else '',
            'appstore_url': appstore_url.strip() if appstore_url else '',
        }
        return request.render('stratstone_attendance_api.download_app_page', values)
