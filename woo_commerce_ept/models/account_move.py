# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields
import requests
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger("Woo")

class AccountMove(models.Model):
    _inherit = "account.move"

    woo_instance_id = fields.Many2one("woo.instance.ept", "Woo Instances")
    is_refund_in_woo = fields.Boolean("Refund In Woo Commerce", default=False)

    def refund_in_woo(self):
        """
        This method is used for refund process. It'll call order refund api for that process
        Note: - It's only generate refund it'll not make any auto transaction according to woo payment method.
              - @param:api_refund: responsible for auto transaction as per woo payment method.
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 23-11-2019.
        Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 30 September 2020 .
        Task Id: 167148
        """
        for refund in self:
            woo_instance = refund.woo_instance_id or False
            if not woo_instance:
                continue
            wcapi = woo_instance.woo_connect()
            orders = refund.invoice_line_ids.sale_line_ids.order_id

            for order in orders:
                data = {"amount":str(refund.amount_total), 'reason':str(refund.name or ''),
                        'api_refund':False}

                response = wcapi.post('orders/%s/refunds' % order.woo_order_id, data)

                _logger.info("Refund created in Woocommerce store for woo order id: %s and refund amount is : %s"%(order.woo_order_id,str(refund.amount_total)))
                if not isinstance(response, requests.models.Response):
                    raise UserError("Refund \n Response is not in proper format :: %s" % response)

                if response.status_code in [200, 201]:
                    refund.write({'is_refund_in_woo':True})
                else:
                    raise UserError("Refund \n%s" % response.content)
        return True