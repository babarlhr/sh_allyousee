# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import ast
import logging
import pytz
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import time

_logger = logging.getLogger("Woo")

class SaleOrder(models.Model):
    """
    Inherited for importing and creating sale orders from WooCommerce.
    @author: Maulik Barad on Date 23-Oct-2019.
    """
    _inherit = "sale.order"

    def _get_woo_order_status(self):
        """
        Compute updated_in_woo of order from the pickings.
        @author: Maulik Barad on Date 04-06-2020.
        """
        for order in self:
            if order.woo_instance_id:
                pickings = order.picking_ids.filtered(lambda x:x.state != "cancel")
                if pickings:
                    outgoing_picking = pickings.filtered(
                            lambda x:x.location_dest_id.usage == "customer")
                    if all(outgoing_picking.mapped("updated_in_woo")):
                        order.updated_in_woo = True
                        continue
                elif order.woo_status == "completed":
                    """When all products are service type and no pickings are there."""
                    order.updated_in_woo = True
                    continue
                order.updated_in_woo = False
                continue
            order.updated_in_woo = False

    def _search_woo_order_ids(self, operator, value):
        query = """
                    select so.id from stock_picking sp
                    inner join sale_order so on so.procurement_group_id=sp.group_id                   
                    inner join stock_location on stock_location.id=sp.location_dest_id and stock_location.usage='customer'
                    where sp.updated_in_woo = %s and sp.state != 'cancel' and
                    so.woo_instance_id notnull
                """ % (value)
        self._cr.execute(query)
        results = self._cr.fetchall()
        order_ids = []
        for result_tuple in results:
            order_ids.append(result_tuple[0])
        order_ids = list(set(order_ids))
        return [('id', 'in', order_ids)]

    woo_order_id = fields.Char("Woo Order Reference", help="WooCommerce Order Reference",
                               copy=False)
    woo_order_number = fields.Char("Order Number", help="WooCommerce Order Number", copy=False)
    woo_instance_id = fields.Many2one("woo.instance.ept", "Woo Instance", copy=False)
    payment_gateway_id = fields.Many2one("woo.payment.gateway", "Woo Payment Gateway", copy=False)
    woo_coupon_ids = fields.Many2many("woo.coupons.ept", string="Coupons", copy=False)
    woo_trans_id = fields.Char("Transaction ID", help="WooCommerce Order Transaction Id",
                               copy=False)
    woo_customer_ip = fields.Char("Customer IP", help="WooCommerce Customer IP Address", copy=False)
    updated_in_woo = fields.Boolean("Updated In woo", compute="_get_woo_order_status",
                                    search="_search_woo_order_ids", copy=False)
    canceled_in_woo = fields.Boolean("Canceled In WooCommerce", default=False, copy=False)
    woo_status = fields.Selection([("pending", "Pending"), ("processing", "Processing"),
                                   ("on-hold", "On hold"), ("completed", "Completed"),
                                   ("cancelled", "Cancelled"), ("refunded", "Refunded")],
                                  copy=False, tracking=7)
    is_service_woo_order = fields.Boolean(default=False,
                                          help="It uses to identify that sale order contains all products as service type.")

    _sql_constraints = [('_woo_sale_order_unique_constraint',
                         'unique(woo_order_id,woo_instance_id,woo_order_number)',
                         "Woocommerce order must be unique")]

    def create_woo_order_data_queue(self, woo_instance, orders_data, name="", created_by="import"):
        """
        Creates order data queues from the data got from API.
        @author: Maulik Barad on Date 04-Nov-2019.
        @param woo_instance: Instance of Woocommerce.
        @param orders_data: Imported JSON data of orders.
        """
        order_queues_list = order_data_queue_obj = self.env["woo.order.data.queue.ept"]
        bus_bus_obj = self.env['bus.bus']
        while orders_data:
            vals = {"name":name, "instance_id":woo_instance.id, "created_by":created_by}
            data = orders_data[:50]
            if data:
                order_data_queue = order_data_queue_obj.create(vals)
                order_queues_list += order_data_queue
                _logger.info("New order queue %s created." % (order_data_queue.name))
                order_data_queue.create_woo_data_queue_lines(data)
                _logger.info("Lines added in Order queue %s." % (order_data_queue.name))
                del orders_data[:50]
                message = "Order Queue created ", order_data_queue.mapped('name')
                bus_bus_obj.sendone((self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                                    {'type':'simple_notification',
                                     'title':'Woocomerce Connector', 'message':message,
                                     'sticky':False, 'warning':True})
                self._cr.commit()

        return order_queues_list

    def import_woo_orders(self, woo_instance, from_date="", to_date="", order_type=False):
        """
        Imports orders from woo commerce and creates order data queue.
        @author: Maulik Barad on Date 04-Nov-2019.
        @param woo_instance: Woo Instance to import orders from.
        @param from_date: Orders will be imported which are created after this date.
        @param to_date: Orders will be imported which are created before this date.
        Migration done by Haresh Mori @ Emipro on date 1 September 2020 .
        """
        woo_instance_obj = self.env["woo.instance.ept"]
        start = time.time()
        if isinstance(woo_instance, int):
            woo_instance = woo_instance_obj.browse(woo_instance)
        if not woo_instance.active:
            return False
        from_date = from_date if from_date else woo_instance.last_order_import_date - timedelta(
                days=1) if woo_instance.last_order_import_date else fields.Datetime.now() - timedelta(
                days=1)
        to_date = to_date if to_date else fields.Datetime.now()

        from_date = pytz.utc.localize(from_date).astimezone(
                pytz.timezone(woo_instance.store_timezone)) if from_date else False
        to_date = pytz.utc.localize(to_date).astimezone(pytz.timezone(woo_instance.store_timezone))

        params = {"after":str(from_date)[:19], "before":str(to_date)[:19],
                  "per_page":100, "page":1, "order":"asc"}
        _logger.info("Page 1")
        order_data_queue = self.get_order_data_wc_v3(params, woo_instance, order_type=order_type)

        if order_type == 'completed':
            woo_instance.last_completed_order_import_date = to_date.astimezone(
                    pytz.timezone("UTC")).replace(tzinfo=None)
        else:
            woo_instance.last_order_import_date = to_date.astimezone(pytz.timezone("UTC")).replace(
                    tzinfo=None)
        end = time.time()
        _logger.info("Order queues time -- %s -- seconds." % (str(end - start)))

        return order_data_queue

    @api.model
    def get_order_data_wc_v3(self, params, woo_instance, order_type):
        """ This method used to get order response from Woocommerce to Odoo.
            @param : self, params, woo_instance,order_type
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 3 September 2020 .
            Task_id: 165893
        """
        bus_bus_obj = self.env['bus.bus']
        common_log_book_obj = self.env['common.log.book.ept']
        log_line_obj = self.env["common.log.lines.ept"]
        order_queues = []
        orders_response = False
        status = ",".join(map(str, woo_instance.import_order_status_ids.mapped("status")))
        params["status"] = status
        wcapi = woo_instance.woo_connect()
        if order_type == 'completed':
            params["status"] = 'completed'
        try:
            response = wcapi.get("orders", params=params)
        except Exception as error:
            raise UserError(
                    "Something went wrong while importing orders.\n\nPlease Check your Connection and Instance Configuration.\n\n" + str(
                            error))

        if response.status_code != 200:
            common_log_book_id = common_log_book_obj.create({"woo_instance_id":woo_instance.id,
                                                             "type":"import",
                                                             "module":"woocommerce_ept",
                                                             "active":True,
                                                             })
            message = (str(response.status_code) + " || " + response.json().get("message",
                                                                                response.reason))
            self.create_woo_log_lines(message, common_log_book_id)
            return False
        if order_type != 'completed':
            orders_response = response.json()
        orders_data = response.json()
        if not orders_data:
            message = "==No orders Found between %s and %s for %s" % (
                params.get('after'), params.get('before'), woo_instance.name)
            bus_bus_obj.sendone((self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                                {'type':'simple_notification', 'title':'Woocomerce Connector',
                                 'message':message, 'sticky':False, 'warning':True})
            _logger.info(message)
        total_pages = response.headers.get("X-WP-TotalPages")
        if int(total_pages) > 1:
            if order_type == 'completed':
                order_queue_ids = self.create_woo_order_data_queue(woo_instance, orders_data)
                order_queues += order_queue_ids.ids
            for page in range(2, int(total_pages) + 1):
                params["page"] = page
                response = wcapi.get("orders", params=params)
                orders_data = response.json()
                _logger.info("Page")
                _logger.info(params["page"])
                if order_type == 'completed':
                    order_queue_ids = self.create_woo_order_data_queue(woo_instance, orders_data)
                    order_queues += order_queue_ids.ids
                else:
                    orders_response += orders_data
        elif order_type == 'completed' and orders_data:
            order_queue_ids = self.create_woo_order_data_queue(woo_instance, orders_data)
            order_queues += order_queue_ids.ids

        if orders_response and order_type != 'completed':
            common_log_book_id = common_log_book_obj.create({"type":"import",
                                                             "module":"woocommerce_ept",
                                                             "model_id":log_line_obj.get_model_id(
                                                                     self._name),
                                                             "woo_instance_id":woo_instance.id,
                                                             "active":True})
            self.create_woo_orders(orders_response, common_log_book_id)
            if not common_log_book_id.log_lines:
                common_log_book_id.unlink()

        return order_queues

    @api.model
    def create_or_update_payment_gateway(self, instance, order_response):
        """ This method used to create a payment gateway in odoo base on code.
            @param : self, instance, order
            @return: payment_gateway
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 3 September 2020 .
            Task_id: 165893
        """
        payment_gateway_obj = self.env["woo.payment.gateway"]
        code = order_response.get("payment_method", "")
        name = order_response.get("payment_method_title", "")
        if not code:
            return False
        payment_gateway = payment_gateway_obj.search(
                [("code", "=", code), ("woo_instance_id", "=", instance.id)], limit=1)
        if not payment_gateway:
            payment_gateway = payment_gateway_obj.create({"code":code,
                                                          "name":name,
                                                          "woo_instance_id":instance.id})
        return payment_gateway

    def create_woo_log_lines(self, message, common_log_book_id=False, queue_line=False):
        """
        Creates log line for the failed queue line.
        @author: Maulik Barad on Date 09-Nov-2019.
        @param queue_line: Failed queue line.
        @param message: Cause of failure.
        @return: Created log line.
        """
        log_line_obj = self.env["common.log.lines.ept"]
        log_line_vals = {"message":message,
                         "model_id":log_line_obj.get_model_id(self._name)}
        if queue_line:
            log_line_vals.update({"woo_order_data_queue_line_id":queue_line.id})
            queue_line.state = "failed"
        if common_log_book_id:
            log_line_vals.update({"log_book_id":common_log_book_id.id})
        return log_line_obj.create(log_line_vals)

    def prepare_woo_order_vals(self, order_data, woo_instance, partner, shipping_partner,
                               workflow_config):
        """ This method used to prepare a order vals.
            @param : self, order_data, woo_instance, partner, shipping_partner, workflow_config
            @return: woo_order_vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        order_date = order_data.get("date_created_gmt")
        price_list = self.find_woo_order_pricelist(order_data, woo_instance)

        ordervals = {
            "partner_id":partner.ids[0],
            "partner_shipping_id":shipping_partner.ids[0],
            "partner_invoice_id":partner.ids[0],
            "warehouse_id":woo_instance.woo_warehouse_id.id,
            "company_id":woo_instance.company_id.id,
            "pricelist_id":price_list.id,
            "payment_term_id":woo_instance.woo_payment_term_id.id,
            "date_order":order_date.replace("T", " "),
            "state":"draft",
        }
        woo_order_vals = self.create_sales_order_vals_ept(ordervals)

        woo_order_number = order_data.get("number")

        if not woo_instance.custom_order_prefix:
            if woo_instance.order_prefix:
                name = "%s%s" % (woo_instance.order_prefix, woo_order_number)
            else:
                name = woo_order_number
            woo_order_vals.update({"name":name})

        woo_order_vals.update({
            "note":order_data.get("customer_note"),
            "woo_order_id":order_data.get("id"),
            "woo_order_number":woo_order_number,
            "woo_instance_id":woo_instance.id,
            "team_id":woo_instance.sales_team_id.id if woo_instance.sales_team_id else False,
            "payment_gateway_id":workflow_config.woo_payment_gateway_id.id if workflow_config.woo_payment_gateway_id else False,
            "woo_trans_id":order_data.get("transaction_id", ""),
            "woo_customer_ip":order_data.get("customer_ip_address"),
            # "global_channel_id":woo_instance.global_channel_id.id if woo_instance.global_channel_id else False,
            "picking_policy":workflow_config.woo_auto_workflow_id.picking_policy,
            "auto_workflow_process_id":workflow_config.woo_auto_workflow_id.id,
            "partner_shipping_id":shipping_partner.ids[0],
            "woo_status":order_data.get("status"),
            "client_order_ref":woo_order_number
        })
        return woo_order_vals

    def find_woo_order_pricelist(self, result, woo_instance):
        """ This method use to check the order price list exists or not in odoo base on the order currency..
            @param : self, result, woo_instance
            @return: price_list
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        product_pricelist_obj = self.env['product.pricelist']
        currency_obj = self.env["res.currency"]
        order_currency = result.get("currency")

        currency_id = currency_obj.search([('name', '=', order_currency)], limit=1)
        if not currency_id:
            currency_id = currency_obj.search([('name', '=', order_currency),
                                               ('active', '=', False)], limit=1)
            currency_id.write({'active':True})
        if woo_instance.woo_pricelist_id.currency_id.id == currency_id.id:
            return woo_instance.woo_pricelist_id
        price_list = product_pricelist_obj.search([('currency_id', '=', currency_id.id)],
                                                          limit=1)
        if price_list:
            return price_list

        price_list = product_pricelist_obj.create({'name':currency_id.name,
                                                           'currency_id':currency_id.id,
                                                           'company_id':woo_instance.company_id.id,
                                                           })

        return price_list

    @api.model
    def create_woo_tax(self, tax, tax_included, woo_instance):
        """
        Creates tax in odoo as woo tax.
        @author: Maulik Barad on Date 20-Nov-2019.
        @param tax: Dictionary of woo tax.
        @param tax_included: If tax is included or not in price of product in woo.
        Migration done by Haresh Mori @ Emipro on date 5 September 2020 .
        """
        account_tax_obj = self.env["account.tax"]
        title = tax["name"]
        rate = tax["rate"]

        if tax_included:
            name = "%s (%s %% included)" % (title, rate)
        else:
            name = "%s (%s %% excluded)" % (title, rate)

        odoo_tax = account_tax_obj.create({"name":name, "amount":float(rate),
                                                   "type_tax_use":"sale",
                                                   "price_include":tax_included,
                                                   "company_id":woo_instance.company_id.id})

        odoo_tax.mapped("invoice_repartition_line_ids").write(
                {"account_id":woo_instance.invoice_tax_account_id.id})
        odoo_tax.mapped("refund_repartition_line_ids").write(
                {"account_id":woo_instance.credit_note_tax_account_id.id})

        return odoo_tax

    @api.model
    def apply_woo_taxes(self, taxes, tax_included, woo_instance):
        """
        Finds matching odoo taxes with woo taxes' rates.
        If no matching tax found in odoo, then creates a new one.
        @author: Maulik Barad on Date 20-Nov-2019.
        @param taxes: List of Dictionaries of woo taxes.
        @param tax_included: If tax is included or not in price of product in woo.
        @param woo_instance: Instance of Woo.
        @return: Taxes' ids in format to add in order line.
        Migration done by Haresh Mori @ Emipro on date 4 September 2020 .
        """
        tax_obj = self.env["account.tax"]
        tax_ids = []
        for tax in taxes:
            rate = float(tax.get("rate"))
            tax_id = tax_obj.search([("price_include", "=", tax_included),
                                     ("type_tax_use", "=", "sale"),
                                     ("amount", "=", rate),
                                     ("company_id", "=",
                                      woo_instance.company_id.id)],
                                    limit=1)
            if not tax_id:
                tax_id = self.sudo().create_woo_tax(tax, tax_included, woo_instance)
                _logger.info('==New tax: %s :created in Odoo.', tax_id.name)
            if tax_id:
                tax_ids.append(tax_id.id)

        return tax_ids

    @api.model
    def create_woo_order_line(self, line_id, product, quantity, order, price, taxes, tax_included,
                              woo_instance, is_shipping=False):
        """ This method used to create a sale order line.
            @param : self, line_id, product, quantity, order, price, taxes, tax_included,woo_instance,is_shipping=False
            @return: sale order line
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        sale_line_obj = self.env["sale.order.line"]
        line_vals = {
            "name":product.name,
            "product_id":product.id,
            "product_uom":product.uom_id.id if product.uom_id else False,
            "order_id":order.id,
            "order_qty":quantity,
            "price_unit":price,
            "is_delivery":is_shipping,
            "company_id":woo_instance.company_id.id
        }

        woo_so_line_vals = sale_line_obj.create_sale_order_line_ept(line_vals)

        if woo_instance.apply_tax == "create_woo_tax":
            tax_ids = self.apply_woo_taxes(taxes, tax_included, woo_instance)
            woo_so_line_vals.update({"tax_id":[(6, 0, tax_ids)]})

        woo_so_line_vals.update({"woo_line_id":line_id})
        return sale_line_obj.create(woo_so_line_vals)

    @api.model
    def create_woo_sale_order_lines(self, queue_line, order_data, sale_order, tax_included,
                                    common_log_book_id, woo_taxes, is_process_from_queue):
        """
        Checks for products and creates sale order lines.
        @author: Maulik Barad on Date 13-Nov-2019.
        @param queue_line: The queue line.
        @param sale_order: Created sale order.
        @param woo_taxes: Dictionary of woo taxes.
        @param tax_included: If tax is included or not in price of product.
        @return: Created sale order lines.
        Migration done by Haresh Mori @ Emipro on date 8 September 2020 .
        """
        order_lines_list = []
        order_line_data = order_data.get("line_items")
        order_number =  order_data.get('number')
        woo_instance = common_log_book_id.woo_instance_id
        round = bool(woo_instance.tax_rounding_method == 'round_per_line')
        for order_line in order_line_data:
            taxes = []
            woo_product = self.find_or_create_woo_product(queue_line, order_line,
                                                          common_log_book_id, is_process_from_queue)
            if not woo_product:
                message = "Product [%s][%s] not found for Order %s" % (order_line.get("sku"), order_line.get("name"), order_number)
                if is_process_from_queue:
                    self.create_woo_log_lines(message, common_log_book_id, queue_line)
                else:
                    self.create_woo_log_lines(message, common_log_book_id)
                return False
            product = woo_product.product_id
            actual_unit_price = 0.0
            if tax_included:
                actual_unit_price = (float(order_line.get("subtotal_tax")) + float(
                        order_line.get("subtotal"))) / float(order_line.get("quantity"))
            else:
                actual_unit_price = float(order_line.get("subtotal")) / float(
                        order_line.get("quantity"))
            if woo_instance.apply_tax == "create_woo_tax":
                for tax in order_line.get("taxes"):
                    taxes.append(woo_taxes.get(tax['id']))
            order_line_id = self.create_woo_order_line(order_line.get("id"), product,
                                                       order_line.get("quantity"), sale_order,
                                                       actual_unit_price, taxes, tax_included,
                                                       woo_instance)
            order_lines_list.append(order_line_id)
            # sale_order.with_context({'round':round}).write({'woo_instance_id' : woo_instance.id})
            # order_line_id.with_context(round=round)._compute_amount()
            line_discount = float(order_line.get('subtotal')) - float(order_line.get('total')) or 0
            if line_discount > 0:
                if tax_included:
                    tax_discount = float(order_line.get("subtotal_tax", 0.0)) - float(
                            order_line.get("total_tax", 0.0)) or 0
                    line_discount = tax_discount + line_discount

                discount_line = self.create_woo_order_line(False,
                                                           woo_instance.discount_product_id,
                                                           1, sale_order, line_discount * -1, taxes,
                                                           tax_included, woo_instance)
                discount_line.write({'name':'Discount for ' + order_line_id.name})
                # sale_order.with_context({'round':round}).write({'woo_instance_id' : woo_instance.id})
                if woo_instance.apply_tax == 'odoo_tax':
                    discount_line.tax_id = order_line_id.tax_id

            _logger.info("Sale order line is created for order %s.", sale_order.name)
        return order_lines_list

    @api.model
    def find_or_create_woo_product(self, queue_line, order_line, common_log_book_id,
                                   is_process_from_queue):
        """
        Searches for the product and return it.
        If it is not found and configuration is set to import product, it will collect data and
        create the product.
        @author: Maulik Barad on Date 12-Nov-2019.
        @param queue_line: Order data queue.
        @param order_line: Order line.
        @return: Woo product if found, otherwise blank object.
        """
        woo_product_template_obj = self.env["woo.product.template.ept"]
        woo_instance = common_log_book_id.woo_instance_id

        # Checks for the product. If found then returns it.
        woo_product_id = order_line.get("variation_id") if order_line.get(
                "variation_id") else order_line.get("product_id")
        woo_product = woo_product_template_obj.search_odoo_product_variant(woo_instance,
                                                                           order_line.get("sku"),
                                                                           woo_product_id)[0]
        # If product not found and configuration is set to import product, then creates it.
        if not woo_product and woo_instance.auto_import_product:
            if not order_line.get("product_id"):
                _logger.info('Product id not found in sale order line response')
                return woo_product
            product_data = woo_product_template_obj.get_products_from_woo_v1_v2_v3(woo_instance,
                                                                                   common_log_book_id,
                                                                                   order_line.get(
                                                                                           "product_id"))
            if is_process_from_queue:
                woo_product_template_obj.sync_products(product_data, woo_instance,
                                                       common_log_book_id,
                                                       order_queue_line=queue_line)
            else:
                woo_product_template_obj.sync_products(product_data, woo_instance,
                                                       common_log_book_id,
                                                       is_process_from_queue=False)
            woo_product = woo_product_template_obj.search_odoo_product_variant(woo_instance,
                                                                               order_line.get(
                                                                                       "sku"),
                                                                               woo_product_id)[0]
        return woo_product

    @api.model
    def get_tax_ids(self, woo_instance, tax_id, woo_taxes):
        """
        Fetches all taxes for the woo instance.
        @author: Maulik Barad on Date 20-Nov-2019.
        @param woo_instance: Woo Instance.
        @return: Tax data if no issue was there, otherwise the error message.
        Migration done by Haresh Mori @ Emipro on date 8 September 2020 .
        """
        wcapi = woo_instance.woo_connect()
        params = {"_fields":"id,name,rate"}
        try:
            response = wcapi.get("taxes/%s" % (tax_id), params=params)
            if response.status_code != 200:
                return response.json().get("message", response.reason)
            tax_data = response.json()
        except:
            return woo_taxes
        woo_taxes.update({tax_data["id"]:tax_data})
        return woo_taxes

    @api.model
    def verify_order_for_payment_method(self, order_data):
        """
        Check order for full discount, when there is no payment gateway found.
        @author: Maulik Barad on Date 21-May-2020.
        Migration done by Haresh Mori @ Emipro on date 4 September 2020 .
        """
        total_discount = 0

        total = order_data.get("total")
        if order_data.get("coupon_lines"):
            total_discount = order_data.get("discount_total")

        if float(total) == 0 and float(total_discount) > 0:
            return True
        return False

    @api.model
    def create_woo_orders(self, queue_lines, common_log_book_id):
        """ This method used to create a order in Odoo base on the response.
            @param : self, queue_lines, common_log_book_id
            @return: new_orders
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        stock_location_obj = self.env["stock.location"]
        new_orders = self
        woo_instance = False
        commit_count = 0
        woo_taxes = {}
        rate_percent = ""
        is_process_from_queue = True
        if isinstance(queue_lines, list):
            is_process_from_queue = False
        for queue_line in queue_lines:
            commit_count += 1
            if commit_count == 5:
                if is_process_from_queue:
                    queue_line.order_data_queue_id.is_process_queue = True
                self._cr.commit()
                commit_count = 0
            if is_process_from_queue:
                if woo_instance != queue_line.instance_id:
                    woo_instance = queue_line.instance_id
                if not queue_line.order_data:
                    queue_line.state = "failed"
                    continue

                order_data = ast.literal_eval(queue_line.order_data)
                queue_line.processed_at = fields.Datetime.now()
            else:
                order_data = queue_line
                woo_instance = common_log_book_id.woo_instance_id

            existing_order = self.search_existing_woo_order(woo_instance, order_data)
            if existing_order:
                if is_process_from_queue:
                    queue_line.state = "done"
                continue

            payment_gateway, workflow_config = self.create_update_payment_gateway_and_workflow(
                    order_data, woo_instance, common_log_book_id, queue_line, is_process_from_queue)
            if not workflow_config:
                continue

            partner, shipping_partner = self.woo_order_billing_shipping_partner(order_data,
                                                                                woo_instance,
                                                                                queue_line,
                                                                                common_log_book_id,
                                                                                is_process_from_queue)
            if not partner:
                continue

            order_vals = self.prepare_woo_order_vals(order_data, woo_instance, partner,
                                                     shipping_partner, workflow_config)

            sale_order = self.create(order_vals)

            tax_included = order_data.get("prices_include_tax")
            for order_tax in order_data.get('tax_lines'):
                if order_tax.get('rate_id') in woo_taxes.keys():
                    continue
                if not rate_percent:
                    if 'rate_percent' in order_tax.keys():
                        rate_percent = "available"
                    else:
                        rate_percent = "not available"

                if rate_percent == "available":
                    woo_taxes.update({order_tax.get('rate_id'):{"name":order_tax.get('label'),
                                                                "rate":order_tax.get(
                                                                        'rate_percent')}})
                elif rate_percent == "not available":
                    woo_taxes = self.get_tax_ids(sale_order.woo_instance_id,
                                                 order_tax.get('rate_id'), woo_taxes)
            order_lines = self.create_woo_sale_order_lines(queue_line, order_data, sale_order,
                                                           tax_included, common_log_book_id,
                                                           woo_taxes, is_process_from_queue)
            if not order_lines:
                sale_order.unlink()
                if is_process_from_queue:
                    queue_line.state = "failed"
                continue
            round = bool(woo_instance.tax_rounding_method == 'round_per_line')
            if order_data.get("shipping_lines"):
                self.create_woo_shipping_line(order_data, sale_order, tax_included, woo_taxes,
                                              round)

            if order_data.get("fee_lines"):
                self.create_woo_fee_line(order_data, tax_included, woo_taxes, sale_order, round)

            if order_data.get("coupon_lines"):
                self.set_coupon_in_sale_order(order_data, sale_order)
            if sale_order.woo_status == 'completed':
                sale_order.auto_workflow_process_id.shipped_order_workflow_ept(sale_order)
            else:
                sale_order.process_orders_and_invoices_ept()
            storable_product = [product for product in sale_order.order_line.mapped('product_id') if
                                product.type != 'service']
            if not storable_product:
                sale_order.is_service_woo_order = True
            new_orders += sale_order
            if is_process_from_queue:
                queue_line.write({"sale_order_id":sale_order.id, "state":"done"})
            message = "Sale order: %s and Woo order number: %s is created." % (
                sale_order.name, order_data.get('number'))
            _logger.info(message)
        if is_process_from_queue:
            queue_lines.order_data_queue_id.is_process_queue = False
        return new_orders

    def search_existing_woo_order(self, woo_instance, order_data):
        """ This method used to search existing Woo order in Odoo.
            @param : self,woo_instance,order_data
            @return: existing_order
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        existing_order = self.search([("woo_instance_id", "=", woo_instance.id),
                                      ("woo_order_id", "=", order_data.get("id")),
                                      ("woo_order_number", "=", order_data.get("number"))]).ids
        if not existing_order:
            existing_order = self.search([("woo_instance_id", '=', woo_instance.id),
                                          ("client_order_ref", "=", order_data.get("number"))]).ids
        return existing_order

    def create_update_payment_gateway_and_workflow(self, order_data, woo_instance,
                                                   common_log_book_id, queue_line,
                                                   is_process_from_queue):
        """ This method used to search or create payment gateway and workflow base on the order response.
            @param : self,order_data,woo_instance,common_log_book_id,queue_line
            @return: payment_gateway, workflow_config
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        sale_auto_workflow_obj = self.env["woo.sale.auto.workflow.configuration"]
        woo_payment_gateway_obj =self.env['woo.payment.gateway']
        workflow_config = False
        financial_status = "paid"
        if order_data.get("transaction_id"):
            financial_status = "paid"
        elif order_data.get("date_paid") and order_data.get(
                "payment_method") != "cod" and order_data.get("status") == "processing":
            financial_status = "paid"
        else:
            financial_status = "not_paid"
        payment_gateway = self.create_or_update_payment_gateway(woo_instance, order_data)
        no_payment_gateway = self.verify_order_for_payment_method(order_data)

        if payment_gateway:
            workflow_config = sale_auto_workflow_obj.search(
                    [("woo_instance_id", "=", woo_instance.id),
                     ("woo_financial_status", "=", financial_status),
                     ("woo_payment_gateway_id", "=", payment_gateway.id)], limit=1)
        elif no_payment_gateway:
            payment_gateway = woo_payment_gateway_obj.search([
                ("code", "=", "no_payment_method"), ("woo_instance_id", "=", woo_instance.id)])
            workflow_config = sale_auto_workflow_obj.search(
                    [("woo_instance_id", "=", woo_instance.id),
                     ("woo_financial_status", "=", financial_status),
                     ("woo_payment_gateway_id", "=", payment_gateway.id)], limit=1)
        else:
            message = """- System could not find the payment gateway response from WooCommerce store.\n- The response received from Woocommerce store was - Empty. Woo Order number: %s""", order_data.get(
                    "number")
            if is_process_from_queue:
                self.create_woo_log_lines(message, common_log_book_id, queue_line)
                queue_line.write({"state":"failed"})
            else:
                self.create_woo_log_lines(message, common_log_book_id)
            return False, False

        if not workflow_config:
            message = "- Automatic order process workflow configuration not found for this order " \
                      "%s. \n - System tries to find the workflow based on combination of Payment " \
                      "Gateway(such as Manual,Credit Card, Paypal etc.) and Financial Status(such as Paid,Pending,Authorised etc.)." \
                      "\n - In this order Payment Gateway is %s and Financial Status is %s." \
                      " \n - You can configure the Automatic order process workflow " \
                      "under the menu Woocommerce > Configuration > Financial Status." % (order_data.get("number"), order_data.get("payment_method_title", ""),financial_status)
            if is_process_from_queue:
                self.create_woo_log_lines(message, common_log_book_id, queue_line)
                queue_line.write({"state":"failed"})
            else:
                self.create_woo_log_lines(message, common_log_book_id)
            return False, False
        workflow = workflow_config.woo_auto_workflow_id

        if not workflow.picking_policy:
            message = "- Picking policy decides how the products will be delivered, " \
                      "'Deliver all at once' or 'Deliver each when available'.\n- System found %s Auto Workflow, but coudn't find configuration about picking policy under it." \
                      "\n- Please review the Auto workflow configuration here : " \
                      "WooCommerce -> Configuration -> Sales Auto Workflow "% workflow.name
            if is_process_from_queue:
                self.create_woo_log_lines(message, common_log_book_id, queue_line)
                queue_line.write({"state":"failed"})
            else:
                self.create_woo_log_lines(message, common_log_book_id)
            return False, False
        return payment_gateway, workflow_config

    def woo_order_billing_shipping_partner(self, order_data, woo_instance, queue_line,
                                           common_log_book_id, is_process_from_queue):
        """ This method used to call a child method of billing and shipping partner.
            @param : self, order_data, woo_instance, queue_line,common_log_book_id,is_process_from_queue
            @return: partner, shipping_partner
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        partner_obj = self.env['res.partner']
        if not order_data.get("billing"):
            message = "- System could not find the billing address in Woocmerce order : %s" % (
                order_data.get("id"))
            if is_process_from_queue:
                self.create_woo_log_lines(message, common_log_book_id, queue_line)
                queue_line.write({"state":"failed"})
            else:
                self.create_woo_log_lines(message, common_log_book_id)
            return False, False

        customer_vals = {'id':order_data.get('customer_id'),
                         'first_name':order_data.get("billing").get('first_name', ''),
                         'last_name':order_data.get("billing").get('last_name', ''),
                         'email':order_data.get("billing").get('email', ''),
                         }
        parent_partner = partner_obj.woo_create_contact_customer(customer_vals, woo_instance)
        partner = partner_obj.woo_create_or_update_customer(order_data.get("billing"), woo_instance,
                                                            parent_partner, 'invoice')
        shipping_partner = partner_obj.woo_create_or_update_customer(order_data.get("shipping"),
                                                                     woo_instance, parent_partner,
                                                                     'delivery')
        if not shipping_partner:
            shipping_partner = partner
        return partner, shipping_partner

    def create_woo_shipping_line(self, order_data, sale_order, tax_included, woo_taxes, round):
        """ This method used to create a shipping line base on the shipping response in the order.
            @param : self, order_data, sale_order, tax_included, woo_taxes
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        delivery_carrier_obj = self.env["delivery.carrier"]
        shipping_product_id = sale_order.woo_instance_id.shipping_product_id

        for shipping_line in order_data.get("shipping_lines"):
            delivery_method = shipping_line.get("method_title")
            if delivery_method:
                carrier = delivery_carrier_obj.search(
                        [("woo_code", "=", delivery_method)], limit=1)
                if not carrier:
                    carrier = delivery_carrier_obj.search(
                            [("name", "=", delivery_method)], limit=1)
                if not carrier:
                    carrier = delivery_carrier_obj.search(
                            ["|", ("name", "ilike", delivery_method),
                             ("woo_code", "ilike", delivery_method)], limit=1)
                if not carrier:
                    carrier = delivery_carrier_obj.create({"name":delivery_method,
                                                           "woo_code":delivery_method,
                                                           "fixed_price":shipping_line.get("total"),
                                                           "product_id":shipping_product_id.id})
                shipping_product = carrier.product_id
                sale_order.write({"carrier_id":carrier.id})

                taxes = []
                for tax in shipping_line.get("taxes"):
                    taxes.append(woo_taxes.get(tax['id']))

                if tax_included:
                    total_shipping = float(shipping_line.get("total", 0.0)) + float(
                            shipping_line.get("total_tax", 0.0))
                else:
                    total_shipping = float(shipping_line.get("total", 0.0))
                self.create_woo_order_line(shipping_line.get("id"), shipping_product, 1,
                                           sale_order, total_shipping, taxes,
                                           tax_included, sale_order.woo_instance_id, True)
                # sale_order.with_context({'round':round}).write({'woo_instance_id' : sale_order.woo_instance_id.id})
                _logger.info("Shipping line is created for the sale order: %s.", sale_order.name)

    def create_woo_fee_line(self, order_data, tax_included, woo_taxes, sale_order, round):
        """ This method used to create a fee line base on the fee response in the order.
            @param : self, order_data, tax_included, woo_taxes, sale_order
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        for fee_line in order_data.get("fee_lines"):
            if tax_included:
                total_fee = float(fee_line.get("total", 0.0)) + float(
                        fee_line.get("total_tax", 0.0))
            else:
                total_fee = float(fee_line.get("total", 0.0))
            if total_fee:
                taxes = []
                for tax in fee_line.get("taxes"):
                    taxes.append(woo_taxes.get([tax["id"]]))

                self.create_woo_order_line(fee_line.get("id"),
                                           sale_order.woo_instance_id.fee_product_id, 1,
                                           sale_order, total_fee, taxes, tax_included,
                                           sale_order.woo_instance_id)
                # sale_order.with_context({'round':round}).write({'woo_instance_id' : sale_order.woo_instance_id.id})
                _logger.info("Fee line is created for the sale order %s.", sale_order.name)

    def set_coupon_in_sale_order(self, order_data, sale_order):
        """ This method is used to set the coupon in the order, it will set coupon if the coupon is already synced in odoo.
            @param : self, order_data, sale_order
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 4 September 2020 .
            Task_id: 165893
        """
        woo_coupon_obj = self.env["woo.coupons.ept"]
        woo_coupons = []
        for coupon_line in order_data.get("coupon_lines"):
            coupon_code = coupon_line["code"]
            coupon = woo_coupon_obj.search([("code", "=", coupon_code),
                                            (
                                                "woo_instance_id", "=",
                                                sale_order.woo_instance_id.id)])
            if coupon:
                woo_coupons.append(coupon.id)
                _logger.info("Coupon {0} added.".format(coupon_code))
            else:
                message = "The coupon {0} could not be added as it is not imported in odoo.".format(
                        coupon_line["code"])
                sale_order.message_post(body=message)
                _logger.info("Coupon {0} not found.".format(coupon_line["code"]))
        sale_order.woo_coupon_ids = [(6, 0, woo_coupons)]

    @api.model
    def update_woo_order_status(self, woo_instance):
        """
        Updates order's status in WooCommerce.
        @author: Maulik Barad on Date 14-Nov-2019.
        @param woo_instance: Woo Instance.
        Migration done by Haresh Mori @ Emipro on date 9 September 2020 .
        """
        common_log_book_obj = self.env["common.log.book.ept"]
        log_lines = []
        if isinstance(woo_instance, int):
            woo_instance = self.env["woo.instance.ept"].browse(woo_instance)
        wcapi = woo_instance.woo_connect()
        sales_orders = self.search([("warehouse_id", "=", woo_instance.woo_warehouse_id.id),
                                    ("woo_order_id", "!=", False),
                                    ("woo_instance_id", "=", woo_instance.id),
                                    ("state", "=", "sale"),
                                    ("woo_status", "!=", 'completed')]).ids
        count = 0
        for sale_order in sales_orders:
            sale_order = self.browse(sale_order)
            if sale_order.updated_in_woo:
                continue

            count += 1
            if count > 50:
                self._cr.commit()
                count = 1

            data = {"status":"completed"}
            order_completed = False
            pickings = sale_order.picking_ids.filtered(lambda
                                                           picking_id:picking_id.location_dest_id.usage == "customer" and picking_id.state != "cancel" and picking_id.updated_in_woo == False)
            if all(state == 'done' for state in pickings.mapped("state")):
                _logger.info("Start Order update status for Order : %s" % sale_order.name)
                response = wcapi.put("orders/%s" % sale_order.woo_order_id, data)

                if response.status_code not in [200, 201]:
                    _logger.info("Could not update status of Order %s." % sale_order.woo_order_id)
                    message = "Error in updating status of order %s,  %s" % (
                        sale_order.name, response.content)
                    log_line = self.create_woo_log_lines(message)
                    log_line and log_lines.append(log_line.id)
                    continue
                pickings.write({"updated_in_woo":True})
                order_completed = True
                _logger.info("Done Order update status for Order : %s" % sale_order.name)

            """When all products are service type."""
            if not pickings and sale_order.state == "sale":
                _logger.info("Start Order update status for Order : %s" % sale_order.name)
                response = wcapi.put("orders/%s" % sale_order.woo_order_id, data)

                if response.status_code not in [200, 201]:
                    _logger.info("Could not update status of Order %s." % sale_order.woo_order_id)
                    message = "Error in updating status of order %s,  %s" % (
                        sale_order.name, response.content)
                    log_line = self.create_woo_log_lines(message)
                    log_line and log_lines.append(log_line.id)
                    continue
                order_completed = True
                _logger.info("Done Order update status for Order : %s" % sale_order.name)
            if order_completed:
                sale_order.woo_status = "completed"

        if log_lines:
            common_log_book_obj.create({"type":"export",
                                        "module":"woocommerce_ept",
                                        "woo_instance_id":woo_instance.id,
                                        "log_lines":[(6, 0, log_lines)],
                                        "active":True})
        return True

    def cancel_in_woo(self):
        """
        This method used to open a wizard to cancel order in WooCommerce.
        @return: action
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 23-11-2019.
        :Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 30 September 2020 .
        """
        view = self.env.ref('woo_commerce_ept.view_woo_cancel_order_wizard')
        context = dict(self._context)
        context.update({'active_model':'sale.order', 'active_id':self.id, 'active_ids':self.ids})
        return {
            'name':_('Cancel Order In WooCommerce'),
            'type':'ir.actions.act_window',
            'view_type':'form',
            'view_mode':'form',
            'res_model':'woo.cancel.order.wizard',
            'views':[(view.id, 'form')],
            'view_id':view.id,
            'target':'new',
            'context':context
        }

    @api.model
    def process_order_via_webhook(self, order_data, instance, update_order=False):
        """
        Creates order data queue and process it.
        This method is for order imported via create and update webhook.
        @author: Maulik Barad on Date 30-Dec-2019.
        @param order_data: Dictionary of order's data.
        @param instance: Instance of Woo.
        Migration done by Haresh Mori @ Emipro on date 23 September 2020 .
        """
        sale_order_obj = self.env["sale.order"]
        common_log_book_obj = self.env['common.log.book.ept']
        log_line_obj = self.env["common.log.lines.ept"]
        woo_order_data_queue_obj = self.env["woo.order.data.queue.ept"]
        if update_order:
            order_queue = woo_order_data_queue_obj.search(
                    [('instance_id', '=', instance.id), ('created_by', '=', 'webhook'),
                     ('state', '=', 'draft')], limit=1)
            order_queue and order_queue.create_woo_data_queue_lines([order_data])
            order_queue and _logger.info(
                "Added woo order number : %s in existing order queue webhook queue %s" % (
                order_data.get('number'), order_queue.display_name))
            if order_queue and len(order_queue.order_data_queue_line_ids) >= 50:
                order_queue.order_data_queue_line_ids.process_order_queue_line()
            elif not order_queue:
                order_data_queue = self.create_woo_order_data_queue(instance, [order_data], '',
                                                                    "webhook")
                _logger.info(
                    "Created order data queue : %s as receive response from update order webhook" % order_data_queue.display_name)
        else:
            log_book_id = common_log_book_obj.create({"type":"import",
                                                      "module":"woocommerce_ept",
                                                      "model_id":log_line_obj.get_model_id(
                                                              self._name),
                                                      "woo_instance_id":instance.id,
                                                      "active":True})
            _logger.info(
                "Creating order in odoo with woo order number: %s as receive response from webhook." % (
                    order_data.get('number')))

            sale_order_obj.create_woo_orders([order_data], log_book_id)

            _logger.info("Creating woo order %s process is finished from webhook." % (
                order_data.get('number')))

        return True

    @api.model
    def update_woo_order(self, queue_lines, log_book):
        """
        This method will update order as per its status got from WooCommerce.
        @author: Maulik Barad on Date 31-Dec-2019.
        @param queue_line: Order Data Queue Line.
        @param log_book: Common Log Book.
        @return: Updated Sale order.
        """
        orders = []
        sale_order_obj = self.env["sale.order"]
        for queue_line in queue_lines:
            message = ""
            woo_instance = queue_line.instance_id
            order_data = ast.literal_eval(queue_line.order_data)
            queue_line.processed_at = fields.Datetime.now()
            woo_status = order_data.get("status")
            partner_obj = self.env['res.partner']
            order = self.search([("woo_instance_id", "=", woo_instance.id),
                                 ("woo_order_id", "=", order_data.get("id"))])
            if not order:
                # Below uses for any order queue, not process due to concurrent issues while webhook process order queue.
                if woo_status in woo_instance.import_order_status_ids.mapped("status") + [
                    'completed']:
                    sale_order_obj.create_woo_orders(queue_line, log_book)
                else:
                    _logger.info(
                            "Woo Order %s is not created in Odoo because as received order status %s is not configured in import order status configuration" % (
                            order_data.get('number'), order_data.get('status')))
                queue_line.state = "done"
                return True
            picking = order and order.picking_ids.filtered(
                    lambda x:x.picking_type_code == 'outgoing' and x.state not in ['cancel',
                                                                                   'done'])
            if picking and woo_status != "cancelled":
                parent_partner = order.partner_invoice_id.parent_id or False
                shipping_partner = order.partner_shipping_id
                updated_shipping_partner = parent_partner and partner_obj.woo_create_or_update_customer(
                        order_data.get("shipping"), woo_instance, parent_partner,
                        'delivery') or False
                if updated_shipping_partner and updated_shipping_partner.id != shipping_partner.id:
                    order.write({'partner_shipping_id':updated_shipping_partner.id})
                    picking.write({'partner_id':updated_shipping_partner.id})

            if woo_status == "cancelled" and order.state != "cancel":
                cancelled = order.cancel_woo_order()
                if not cancelled:
                    message = "System can not cancel the order {0} as one of the picking is in the done state.".format(
                            order.name)
            elif woo_status == "refunded":
                refunded = order.create_woo_refund(order_data.get("refunds"), woo_instance)
                if refunded[0] == 4:
                    message = "- Refund can only be generated if it's related order " \
                              "invoice is found.\n- For order [%s], system could not find the " \
                              "related order invoice. " % (order_data.get('number'))
                elif refunded[0] == 3:
                    message = "- Refund can only be generated if it's related order " \
                              "invoice is in 'Post' status.\n- For order [%s], system found " \
                              "related invoice but it is not in 'Post' status." % (
                                  order_data.get('number'))
                elif refunded[0] == 2:
                    message = "- Partial refund is received from Woocommerce for order [%s].\n " \
                              "- System do not process partial refunds.\n" \
                              "- Either create partial refund manually in Odoo or do full " \
                              "refund in Woocommerce." % (order_data.get('number'))
            elif woo_status == "completed":
                completed = order.complete_woo_order()
                if isinstance(completed, bool) and not completed:
                    message = "There is not enough stock to complete Delivery for order [" \
                              "%s]" % order_data.get('number')
                elif not completed:
                    message = "There is not enough stock to complete Delivery for order [" \
                              "%s]" % order_data.get('number')

            if message:
                order.create_woo_log_lines(message, log_book, queue_line)
            else:
                queue_line.state = "done"
                order.woo_status = woo_status
            orders.append(order)

        return orders

    def cancel_woo_order(self):
        """
        Cancelled the sale order when it is cancelled in WooCommerce.
        @author: Maulik Barad on Date 31-Dec-2019.
        """
        if "done" in self.picking_ids.mapped("state"):
            return False
        self.action_cancel()
        return True

    def complete_woo_order(self):
        """
        If order is confirmed yet, confirms it first.
        Make the picking done, when order will be completed in WooCommerce.
        This method is used for Update order webhook.
        @author: Maulik Barad on Date 31-Dec-2019.
        Migration done by Haresh Mori @ Emipro on date 24 September 2020 .
        """
        if not self.state == "sale":
            self.action_confirm()
        return self.complete_picking_for_woo(
                self.picking_ids.filtered(lambda x:x.location_dest_id.usage == "customer"))

    def complete_picking_for_woo(self, pickings):
        """
        It will make the pickings done.
        This method is used for Update order webhook.
        @author: Maulik Barad on Date 01-Jan-2020.
        Migration done by Haresh Mori @ Emipro on date 24 September 2020 .
        """
        stock_imediate_trasfre_obj = self.env['stock.immediate.transfer']
        for picking in pickings.filtered(lambda x:x.state != "done"):
            if picking.state != "assigned":
                if picking.move_lines.move_orig_ids:
                    completed = self.complete_picking_for_woo(
                            picking.move_lines.move_orig_ids.picking_id)
                    if not completed:
                        return False
                picking.action_assign()
                if picking.state != "assigned":
                    return False
            result = picking.button_validate()

            if isinstance(result, dict):
                context = result.get("context")
                context.update({"skip_sms":True})
                res_model = result.get("res_model", "")
                # model can be stock.immediate.transfer or stock backorder.confirmation

                if res_model:
                    immediate_transfer_record = self.env[res_model].with_context(context).create({})
                    immediate_transfer_record.process()
                    if picking.state == 'done':
                        picking.write({"updated_in_woo":True})
                        picking.message_post(
                            body="Picking is done by Webhook as Order is fulfilled in Woocommerce.")
            else:
                return result
        return True

    def create_woo_refund(self, refunds_data, woo_instance):
        """
        Creates refund of Woo order, when order is refunded in WooCommerce.
        It will need invoice created and posted for creating credit note in Odoo, otherwise it will
        create log and generate activity as per configuration.
        @author: Maulik Barad on Date 02-Jan-2019.
        @param refunds_data: Data of refunds.
        @param woo_instance: Instance of Woo.
        @return:[0] : When no invoice is created.
                [1] : When invoice is not posted.
                [2] : When partial refund was made in Woo.
                [True]:When credit notes are created or partial refund is done.
        """
        account_move_obj = self.env['account.move']
        if not self.invoice_ids:
            return [4]
        total_refund = 0.0
        for refund in refunds_data:
            total_refund += float(refund.get("total", 0)) * -1
        invoices = self.invoice_ids.filtered(lambda x:x.move_type == "out_invoice")
        refunds = self.invoice_ids.filtered(lambda x:x.move_type == "out_refund")

        if refunds:
            return [True]

        for invoice in invoices:
            if not invoice.state == "posted":
                return [3]
        if self.amount_total == total_refund:
            move_reversal = self.env["account.move.reversal"].with_context(
                    {"active_model":"account.move",
                     "active_ids":invoices.ids}).create({"refund_method":"cancel",
                                                         "reason":"Refunded from Woo" if len(
                                                                 refunds_data) > 1 else
                                                         refunds_data[0].get(
                                                                 "reason")})
            move_reversal.reverse_moves()
            move_reversal.new_move_ids.message_post(
                    body="Credit note generated by Webhook as Order refunded in Woocommerce.")
            return [True]
        return [2]

    def _prepare_invoice(self):
        """
        This method is used to set instance id to invoice. for identified invoice.
        :return: invoice
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 23-11-2019.
        :Task id: 156886
        """
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.woo_instance_id:
            invoice_vals.update({'woo_instance_id':self.woo_instance_id.id})
        return invoice_vals

    def validate_and_paid_invoices_ept(self, work_flow_process_record):
        """
        This method will create invoices, validate it and paid it, according
        to the configuration in workflow sets in quotation.
        :param work_flow_process_record:
        :return: It will return boolean.
        Migration done by twinkalc August 2020
        This method used to create and register payment base on the Woo order status.
        """
        self.ensure_one()
        if self.woo_instance_id and self.woo_status == 'pending':
            return True
        if work_flow_process_record.create_invoice:
            invoices = self._create_invoices()
            self.validate_invoice_ept(invoices)
            if self.woo_instance_id and self.woo_status == 'on-hold':
                return True
            if work_flow_process_record.register_payment:
                self.paid_invoice_ept(invoices)
        return True

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    woo_line_id = fields.Char()
