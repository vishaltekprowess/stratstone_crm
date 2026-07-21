/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

function downloadMobileAppItem(env) {
    const url = "/download-app";
    return {
        type: "item",
        id: "download_mobile_app",
        description: _t("Download App"),
        href: url,
        callback: () => {
            browser.open(url, "_blank");
        },
        sequence: 25,
    };
}

registry.category("user_menuitems").add("download_mobile_app", downloadMobileAppItem);
