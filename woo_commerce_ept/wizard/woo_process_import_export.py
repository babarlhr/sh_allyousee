# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import json
import base64
import logging
import csv
from datetime import datetime, timedelta
from io import StringIO, BytesIO

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.misc import split_every
import time
from odoo.tools.mimetypes import guess_mimetype

_logger = logging.getLogger("Woo")

class WooProcessImportExport(models.TransientModel):
    _name = 'woo.process.import.export'
    _description = "Woo Import/Export Process"

    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance",
                                      domain=[("state", "=", "confirmed")])
    woo_operation = fields.Selection([
        ('import_product', 'Import Products'),
        ('import_customer', 'Import Customers'),
        ('import_unshipped_orders', 'Import Unshipped Orders'),
        ('import_completed_orders', 'Import Completed Orders'),
        ('is_update_order_status', 'Update Order Shipping Status'),
        ('import_product_tags', 'Import Product Tags'),
        ('import_attribute', 'Import Attributes'),
        ('import_category', 'Import Categories'),
        ('import_coupon', 'Import Coupons'),
        ('import_stock', 'Import Stock'),
        ('export_stock', 'Export Stock'),
        ("update_tags", "Update Tags"),
        ("export_tags", "Export Tags"),
        ('update_category', 'Update Categories'),
        ('export_category', 'Export Categories'),
        ('update_coupon', 'Update Coupons'),
        ('export_coupon', 'Export Coupons'),
        ('import_product_from_csv', 'Import Product From CSV')
    ], string="Operation")
    woo_skip_existing_product = fields.Boolean(string="Do not update existing products",
                                               help="Check if you want to skip existing products in"
                                                    " odoo", default=False)
    orders_before_date = fields.Datetime("To")
    orders_after_date = fields.Datetime("From")
    woo_is_set_price = fields.Boolean(string="Woo Set Price ?")
    woo_is_set_stock = fields.Boolean(string="Woo Set Stock ?")
    woo_publish = fields.Selection([('publish', 'Publish'), ('unpublish', 'Unpublish')],
                                   string="Publish In Website ?",
                                   help="If select publish then Publish the product in website and"
                                        " If the select unpublish then Unpublish the product "
                                        "from website")
    woo_is_set_image = fields.Boolean(string="Woo Set Image ?", default=False)
    woo_basic_detail = fields.Boolean(string="Basic Detail", default=True)
    export_stock_from = fields.Datetime(help="It is used for exporting stock from Odoo to Woo.")
    import_products_method = fields.Selection([("import_all", "Import all"),
                                               ("new_and_updated", "New and Updated Only")],
                                              "Products to Import",
                                              default="new_and_updated")
    choose_file = fields.Binary(filters="*.csv", help="Select CSV file to upload.")
    file_name = fields.Char(string="File Name", help="Name of CSV file.")
    csv_data = fields.Binary('CSV File', readonly=True, attachment=False)

    @api.constrains('orders_after_date', 'orders_before_date')
    def _check_order_after_before_date(self):
        """
        Constraint for from and to date of import order process.
        @author: Maulik Barad on Date 08-Jan-2019.
        """
        if self.orders_before_date <= self.orders_after_date:
            raise ValidationError(
                    "From date should be less than To date.\nPlease enter proper date range for import order process.")

    @api.onchange('woo_operation')
    def _onchange_woo_operation(self):
        """ Onchange method of Instance as need to set the From date for import order process.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 3 September 2020 .
            Task_id: 165893
        """
        if self.woo_instance_id:
            if self.woo_instance_id.last_order_import_date and self.woo_operation == 'import_unshipped_orders':
                self.orders_after_date = self.woo_instance_id.last_order_import_date
            elif self.woo_instance_id.last_completed_order_import_date and self.woo_operation == 'import_completed_orders':
                self.orders_after_date = self.woo_instance_id.last_completed_order_import_date
            elif self.woo_operation not in ['import_unshipped_orders', 'import_completed_orders']:
                self.orders_after_date = fields.Datetime.now() - timedelta(days=1)
            if self.woo_instance_id.last_inventory_update_time:
                self.export_stock_from = self.woo_instance_id.last_inventory_update_time
            else:
                self.export_stock_from = fields.Datetime.now() - timedelta(days=30)
        else:
            self.orders_after_date = False
        self.orders_before_date = fields.Datetime.now()

    def execute(self):
        queues = False
        if self.woo_operation == "import_customer":
            queues = self.woo_import_customers()
            action = self.env.ref("woo_commerce_ept.woo_customer_data_queue_ept_action").sudo().read()[0]
            form_view = [(self.env.ref('woo_commerce_ept.woo_customer_data_data_queue_ept_form_view').id, 'form')]
        elif self.woo_operation == "import_product":
            queues = self.get_products_from_woo()
            action = self.env.ref("woo_commerce_ept.action_woo_product_data_queue_ept").sudo().read()[0]
            form_view = [(self.env.ref('woo_commerce_ept.woo_product_data_queue_form_view_ept').id, 'form')]
        elif self.woo_operation == "import_product_tags":
            self.sync_product_tags()
        elif self.woo_operation == "import_attribute":
            self.sync_woo_attributes()
        elif self.woo_operation == "import_category":
            self.sync_woo_product_category()
        elif self.woo_operation == "import_unshipped_orders":
            self.import_sale_orders()
        elif self.woo_operation == "import_completed_orders":
            queues = self.import_sale_orders(order_type='completed')
            action = self.env.ref("woo_commerce_ept.action_woo_order_data_queue_ept").sudo().read()[0]
            form_view = [(self.env.ref('woo_commerce_ept.view_woo_order_data_queue_ept_form').id, 'form')]
        elif self.woo_operation == "is_update_order_status":
            self.update_order_status()
        elif self.woo_operation == 'import_stock':
            self.import_stock()
        elif self.woo_operation == "export_stock":
            self.update_stock_in_woo()
        elif self.woo_operation == "update_tags":
            self.update_tags_in_woo()
        elif self.woo_operation == "export_tags":
            self.export_tags_in_woo()
        elif self.woo_operation == "update_category":
            self.update_product_categ()
        elif self.woo_operation == "export_category":
            self.export_product_categ()
        elif self.woo_operation == "import_coupon":
            queues = self.import_woo_coupon()
            action = self.env.ref("woo_commerce_ept.action_woo_coupon_data_queue_ept").sudo().read()[0]
            form_view = [(self.env.ref('woo_commerce_ept.view_woo_coupon_data_queue_ept_form').id, 'form')]
        elif self.woo_operation == "export_coupon":
            self.export_woo_coupons()
        elif self.woo_operation == "update_coupon":
            self.update_woo_coupons()
        elif self.woo_operation == "import_product_from_csv":
            self.import_products_from_csv()

        if queues:
            if len(queues) >1:
                action["domain"] = [("id", "in", queues)]
            else:
                action['views'] = form_view
                action['res_id'] = queues[0]
            return action

        return {
            'type':'ir.actions.client',
            'tag':'reload',
        }

    def sync_woo_product_category(self, woo_instance=False):
        """
        This method is used for create a woo product category based on category response
        :param woo_instance: It contain the browsable object of the current instance
        :return: It will return True if the process successfully completed
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        woo_category_obj = self.env['woo.product.categ.ept']
        woo_common_log_obj = self.env["common.log.book.ept"]
        if self:
            woo_instance = self.woo_instance_id
        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':woo_instance.id,
                    'active':True,
                })
        sync_product_image = woo_instance.sync_images_with_product
        woo_category_obj.sync_woo_product_category(woo_instance, woo_common_log_id,
                                                   woo_product_categ=False,
                                                   woo_product_categ_name=False,
                                                   sync_images_with_product=sync_product_image)
        if not woo_common_log_id.log_lines:
            woo_common_log_id.unlink()
        self._cr.commit()
        return True

    def sync_woo_attributes(self, woo_instance=False):
        """
        This method is used for create a product attribute with its values based in product attributes response
        :param woo_instance: It contain the browsable object of the current instance
        :return: It will return true if the process successful complete
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        woo_common_log_obj = self.env["common.log.book.ept"]
        if self:
            woo_instance = self.woo_instance_id
        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':woo_instance.id,
                    'active':True,
                })
        woo_template_obj = self.env['woo.product.template.ept']
        woo_template_obj.sync_woo_attribute(woo_instance, woo_common_log_id)

        if not woo_common_log_id.log_lines:
            woo_common_log_id.unlink()
        return True

    def sync_product_tags(self, woo_instance=False):
        """
        This method is used for create a product tags based on product tags response
        :param woo_instance: It contain the browsable object of the current instance
        :return: It will return True if the process successfully completed
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        woo_common_log_obj = self.env["common.log.book.ept"]
        if self:
            woo_instance = self.woo_instance_id
        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':woo_instance.id,
                    'active':True,
                })
        product_tags_obj = self.env['woo.tags.ept']
        product_tags_obj.woo_sync_product_tags(woo_instance, woo_common_log_id)
        if not woo_common_log_id.log_lines:
            woo_common_log_id.unlink()
        self._cr.commit()
        return True

    def woo_import_customers(self):
        """ This method used for get customers and generate queue for import process.
            @param : self
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 28 August 2020.
            Task_id: 165956
        """
        start = time.time()
        res_partner_obj = self.env['res.partner']
        common_log_obj = self.env["common.log.book.ept"]
        common_log_id = common_log_obj.create({
            'type':'import',
            'module':'woocommerce_ept',
            'woo_instance_id':self.woo_instance_id.id,
            'active':True,
        })
        customer_queues = res_partner_obj.with_context(import_export_record_id=self.id).woo_get_customers(
                common_log_id, self.woo_instance_id)
        if not common_log_id.log_lines:
            common_log_id.unlink()
        end = time.time()
        _logger.info("Created customer queues time -- %s -- seconds." % (str(end - start)))
        return customer_queues

    def prepare_data_for_import_stock(self):
        """
        This method is used for prepare data for import stock
        :return: List of dict
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd 16-Nov-2019
        :Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 22 September 2020 .
        """
        common_log_obj = self.env["common.log.book.ept"]
        woo_product = self.env['woo.product.product.ept']
        common_log_line_obj = self.env["common.log.lines.ept"]
        model = "woo.product.product.ept"
        model_id = common_log_line_obj.get_model_id(model)
        instance = self.woo_instance_id
        wcapi = instance.woo_connect()
        products_stock = []
        dublicate_woo_product = []
        log_line_id = []
        try:
            woo_products = woo_product.search(
                    [('exported_in_woo', '=', True), ('woo_instance_id', '=', instance.id)])
            sku = woo_products.mapped('default_code')
            product_fields = 'id,name,sku,manage_stock,stock_quantity'
            for sku_chunk in split_every(100, sku):
                str_sku = ",".join(sku_chunk)
                res = wcapi.get("products",
                                params={'sku':str_sku, '_fields':product_fields, 'per_page':100})
                if res.status_code not in [200, 201]:
                    log_id = common_log_line_obj.create({
                        'model_id':model_id,
                        'message':'Import Stock for products has not proper response.\n Response %s' % (
                            res.content)
                    })
                    log_line_id.append(log_id.id)

                res_products = res.json()
                for res_product in res_products:
                    stock_data = {}
                    product = woo_products.filtered(
                            lambda x:x.default_code == res_product.get('sku'))
                    if product:
                        if res_product.get('manage_stock') and res_product.get('stock_quantity'):
                            if product.product_id.type == 'product':
                                product_qty = res_product.get('stock_quantity')
                                stock_data.update({'product_qty':product_qty})
                                stock_data.update({'product_id':product.product_id})
                                if  product.product_id.id not in dublicate_woo_product:
                                    _logger.info("\n Adding dict in Woo product list for inventory adjustment: %s for Woo product variant ID: %s"%(stock_data,product.variant_id))
                                    products_stock.append(stock_data)
                                    dublicate_woo_product.append(product.product_id.id)
                                else:
                                    _logger.info("== Duplicate product available in Woocmmerce store with SKU: %s " % product.default_code)
                    else:
                        log_id = common_log_line_obj.create({
                            'model_id':model_id,
                            'message':'Import Stock for product %s does not exist in odoo' % (
                                res_product.get('sku')),
                        })
                        log_line_id.append(log_id.id)

        except Exception as e:
            log_id = common_log_line_obj.create({
                'model_id':model_id,
                'message':'Import Stock for products not perform.\n Error %s' % (e),
            })
            log_line_id.append(log_id.id)

        if log_line_id:
            common_log_obj.create({
                'type':'import',
                'module':'woocommerce_ept',
                'woo_instance_id':instance.id,
                'active':True,
                'log_lines': [(6, 0, log_line_id)]
            })

        return products_stock

    def import_stock(self):
        """
        This method is used for import stock. In which call methods for prepare stock data.
        :return: Boolean
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 08-11-2019.
        :Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 22 September 2020 .
        """
        instance = self.woo_instance_id

        products_stock = self.prepare_data_for_import_stock()

        if products_stock:
            _logger.info("== Going for the create inventory adjustment....")
            self.env['stock.inventory'].create_stock_inventory_ept(products_stock,
                                                                   instance.woo_warehouse_id.lot_stock_id,
                                                                   auto_validate=False)
            _logger.info("== Created inventory adjustment and inventory adjustment line.")
        return True

    def update_stock_in_woo(self):
        """
        This method is call update_stock() method which is responsible to update stock in WooCommerce.
        :return: Boolean
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 16-11-2019.
        :Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 11 September 2020 .
        """
        instance = self.woo_instance_id
        self.env['woo.product.template.ept'].update_stock(instance, self.export_stock_from)
        return True

    def get_products_from_woo(self):
        """
        This method used to get products with its variants from woo commerce
        @param : self: It contain browsable object of class woo_process_import_export
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        Migration done by Haresh Mori @ Emipro on date 13 August 2020.
        Task_Id: 165892
        """
        start = time.time()
        woo_products_template_obj = self.env['woo.product.template.ept']
        woo_common_log_obj = self.env["common.log.book.ept"]
        woo_instance_id = self.woo_instance_id
        import_all = True if self.import_products_method == "import_all" else False

        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':woo_instance_id.id,
                    'active':True,
                })
        self.sync_woo_product_category(woo_instance_id)
        self.sync_product_tags(woo_instance_id)
        self.sync_woo_attributes(woo_instance_id)
        product_queues = woo_products_template_obj.with_context(
                import_export_record=self.id).get_products_from_woo_v1_v2_v3(woo_instance_id,
                                                                             woo_common_log_id,
                                                                             import_all=import_all)
        if not woo_common_log_id.log_lines:
            woo_common_log_id.unlink()
        end = time.time()
        _logger.info("Created product queues time -- %s -- seconds." % (str(end - start)))

        return product_queues

    def create_customer_queue(self, customers, created_by="import"):
        """ This method used to create a customer queue base on the customer response.
            @param : self, customers
            @return: queue
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 28 August 2020 .
            Task_id: 165956
        """
        woo_sync_customer_obj = self.env['woo.customer.data.queue.ept']
        woo_sync_customer_data = self.env['woo.customer.data.queue.line.ept']

        for customer_queue in split_every(101, customers):
            queue = woo_sync_customer_obj.create({"woo_instance_id":self.woo_instance_id.id,'created_by':created_by})
            _logger.info("Created customer queue: %s" % queue.display_name)
            sync_vals = {
                'woo_instance_id':self.woo_instance_id.id,
                'queue_id':queue.id,
            }

            for customer in customer_queue:
                sync_vals.update({
                    'last_process_date':datetime.now(),
                    'woo_synced_data':json.dumps(customer),
                    'woo_synced_data_id':customer.get('id'),
                    'name':customer.get('billing').get('first_name') + customer.get('billing').get(
                            'last_name') if customer.get('billing') else ''
                })
                woo_sync_customer_data.create(sync_vals)
        return queue

    def woo_import_products(self, woo_products, created_by="import"):
        """ This method used to create a new product queue based on product response from woocommerce
            @param : self :- It contain the object of current class
            @param : woo_products - It contain the products of woo commerce and its type is list
            @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
            Migration done by Haresh Mori @ Emipro on date 13 August 2020.
            Task_Id: 165892
        """
        woo_product_synced_queue_line_obj = self.env['woo.product.data.queue.line.ept']
        queue_obj = self.create_product_queue(created_by)
        _logger.info(
                "Product Data Queue {0} created. Adding data in it.....".format(queue_obj.name))
        queue_obj_list = [queue_obj]
        sync_queue_vals_line = self.prepare_product_queue_line_vals(queue_obj)

        for woo_product in woo_products:
            sync_queue_vals_line.update(
                    {
                        'woo_synced_data':json.dumps(woo_product),
                        'woo_update_product_date':woo_product.get('date_modified'),
                        'woo_synced_data_id':woo_product.get('id'),
                        'name':woo_product.get('name')
                    })
            woo_product_synced_queue_line_obj.create(sync_queue_vals_line)
            if len(queue_obj.queue_line_ids) == 101:
                queue_obj = self.create_product_queue(created_by="import")
                _logger.info(
                        "Product Data Queue {0} created. Adding data in it.....".format(
                            queue_obj.name))
                queue_obj_list.append(queue_obj)
                sync_queue_vals_line = self.prepare_product_queue_line_vals(queue_obj)
                continue
        for queue_obj in queue_obj_list:
            if not queue_obj.queue_line_ids:
                queue_obj.unlink()
        return queue_obj

    def create_product_queue(self, created_by):
        """This method used to create a product data queue.
            @param : self,created_by
            @return: product_queue
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13 August 2020.
            Task_id:165892
        """
        woo_product_synced_queue_obj = self.env['woo.product.data.queue.ept']
        queue_vals = {
            'name':self.woo_operation,
            'woo_instance_id':self.woo_instance_id.id,
            'woo_skip_existing_products':self.woo_skip_existing_product,
            "created_by":created_by
        }
        product_queue = woo_product_synced_queue_obj.create(queue_vals)
        return product_queue

    def prepare_product_queue_line_vals(self, queue_obj):
        """This method used to prepare a vals for the product data queue line.
            @param : self,queue_obj
            @return: sync_queue_vals_line
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13 August 2020.
            Task_id:165892
        """
        sync_queue_vals_line = {
            'woo_instance_id':self.woo_instance_id.id,
            'synced_date':datetime.now(),
            'last_process_date':datetime.now(),
            'queue_id':queue_obj.id
        }
        return sync_queue_vals_line

    def woo_export_products(self):
        """ This method use to export selected product in the Woocommerce store.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 15 September 2020 .
            Task_id: 165897
        """
        woo_product_tmpl_obj = self.env['woo.product.template.ept']
        common_log_book_obj = self.env['common.log.book.ept']
        woo_instance_obj = self.env['woo.instance.ept']
        woo_product_categ_obj = self.env['woo.product.categ.ept']
        woo_template_ids = self._context.get('active_ids')
        common_log_line_obj = self.env['common.log.lines.ept']
        woo_tags_obj = self.env["woo.tags.ept"]
        woo_process_import_export_obj = self.env["woo.process.import.export"]
        model_id = common_log_line_obj.get_model_id('woo.product.categ.ept')
        if not woo_template_ids:
            raise UserError("Please select some products to Export to WooCommerce Store.")

        if woo_template_ids and len(woo_template_ids) > 80:
            raise UserError("Error:\n- System will not export more then 80 Products at a "
                            "time.\n- Please "
                            "select only 80 product for export.")

        instances = woo_instance_obj.search([('active', '=', True)])

        woo_product_templates = woo_product_tmpl_obj.search([('id', 'in', woo_template_ids),
                                                             ('exported_in_woo', '=', False)])

        for instance in instances:
            woo_templates = woo_product_templates.filtered(lambda x:x.woo_instance_id == instance)
            if not woo_templates:
                continue
            woo_templates = self.woo_filter_templates(woo_templates)

            common_log_id = common_log_book_obj.create(
                    {
                        'type':'export',
                        'module':'woocommerce_ept',
                        'woo_instance_id':instance.id,
                        'active':True,
                    })
            domain = [('exported_in_woo', '=', False), ('woo_instance_id', '=', instance.id)]
            not_exported_category = woo_product_categ_obj.search(domain)
            if not_exported_category:
                woo_process_import_export_obj.sync_woo_product_category(instance)
                not_exported_category = woo_product_categ_obj.search(domain)
                not_exported_category and woo_product_categ_obj.export_product_categs(instance,
                                                                                      not_exported_category,
                                                                                      common_log_id,
                                                                                      model_id)
            not_exported_tag = woo_tags_obj.search(domain)
            if not_exported_tag:
                woo_process_import_export_obj.sync_product_tags(instance)
                not_exported_tag = woo_tags_obj.search(domain)
                woo_tags_obj.woo_export_product_tags(instance, not_exported_tag, common_log_id)

            woo_product_tmpl_obj.export_products_in_woo(instance, woo_templates,
                                                        self.woo_is_set_price, self.woo_publish,
                                                        self.woo_is_set_image,
                                                        self.woo_basic_detail, common_log_id)
            if common_log_id and not common_log_id.log_lines:
                common_log_id.unlink()

    def woo_filter_templates(self, woo_templates):
        """
        This method is used for filter the woo product template based on default_code and woo template id
        :param woo_templates: It contain the woo product templates and Its type is Object
        :return: It will return the browsable object of the woo product template
        """
        filter_templates = []
        for woo_template in woo_templates:
            if not self.env['woo.product.product.ept'].search(
                    [('woo_template_id', '=', woo_template.id), ('default_code', '=', False)]):
                filter_templates.append(woo_template)
        return filter_templates

    def import_sale_orders(self, order_type=False):
        """
        Imports woo orders and makes queues for selected instance.
        @author: Maulik Barad on Date 14-Nov-2019.
        Migration done by Haresh Mori @ Emipro on date 1 September 2020 .
        """
        order_queues = self.env['sale.order'].import_woo_orders(self.woo_instance_id,
                                                 self.orders_after_date,
                                                 self.orders_before_date,
                                                 order_type=order_type)
        return order_queues

    def update_order_status(self):
        """ This method used to call child method of update order status.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 9 September 2020 .
            Task_id: 165894
        """
        self.env['sale.order'].update_woo_order_status(self.woo_instance_id)

    def update_products(self):
        """
        This method is used to update the existing products in woo commerce
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        Migration done by Haresh Mori @ Emipro on date 19 September 2020 .
        """
        start = time.time()
        woo_instance_obj = self.env['woo.instance.ept']
        common_log_book_obj = self.env['common.log.book.ept']
        woo_product_tmpl_obj = self.env['woo.product.template.ept']
        woo_product_categ_obj = self.env['woo.product.categ.ept']
        woo_tags_obj = self.env["woo.tags.ept"]
        woo_process_import_export_obj = self.env["woo.process.import.export"]
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')

        if not self.woo_basic_detail and not self.woo_is_set_price and not self.woo_is_set_image and not \
                self.woo_publish:
            raise UserError('Please Select any one Option for process Update Products')

        if self._context.get('process') == 'update_products':
            woo_tmpl_ids = self._context.get('active_ids')
            if woo_tmpl_ids and len(woo_tmpl_ids) > 80:
                raise UserError("Error\n- System will not update more then 80 Products at a "
                                "time.\n- Please "
                                "select only 80 product for update.")

        instances = woo_instance_obj.search([('active', '=', True)])
        woo_tmpl_ids = woo_product_tmpl_obj.browse(woo_tmpl_ids)
        for instance in instances:
            if woo_tmpl_ids:
                woo_templates = woo_tmpl_ids.filtered(lambda woo_template:woo_template.woo_instance_id.id == instance.id and woo_template.exported_in_woo == True)
            if not woo_templates:
                continue
            common_log_id = common_log_book_obj.create(
                    {
                        'type':'export',
                        'module':'woocommerce_ept',
                        'woo_instance_id':instance.id,
                        'active':True,
                    })
            if self.woo_basic_detail:
                domain = [('exported_in_woo', '=', False), ('woo_instance_id', '=', instance.id)]
                not_exported_category = woo_product_categ_obj.search(domain)
                not_exported_tag = woo_tags_obj.search(domain)

                if not_exported_category:
                    woo_process_import_export_obj.sync_woo_product_category(instance)
                    not_exported_category = woo_product_categ_obj.search(domain)
                    not_exported_category and woo_product_categ_obj.export_product_categs(instance,
                                                                                          not_exported_category,
                                                                                          common_log_id,
                                                                                          model_id)

                if not_exported_tag:
                    woo_process_import_export_obj.sync_product_tags(instance)
                    not_exported_tag = woo_tags_obj.search(domain)
                    woo_tags_obj.woo_export_product_tags(instance, not_exported_tag, common_log_id)

            woo_product_tmpl_obj.update_products_in_woo(instance, woo_templates,
                                                        self.woo_is_set_price,
                                                        self.woo_publish,
                                                        self.woo_is_set_image,
                                                        self.woo_basic_detail,
                                                        common_log_id)
            if not common_log_id.log_lines:
                common_log_id.unlink()
        end = time.time()
        _logger.info("Update products in Woocommerce Store in %s seconds." % (str(end - start)))
        return True

    def export_stock_in_woo(self):
        """ This method use to export stock for selected Woo template.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 15 September 2020 .
            Task_id: 166453
        """
        woo_instance_obj = self.env['woo.instance.ept']
        woo_product_tmpl_obj = self.env['woo.product.template.ept']
        woo_tmpl_ids = self._context.get('active_ids')

        if woo_tmpl_ids and len(woo_tmpl_ids) > 80:
            raise UserError("Error\n- System will not update more then 80 Products at a "
                            "time.\n- Please "
                            "select only 80 product for update.")

        instances = woo_instance_obj.search([('active', '=', True)])
        for instance in instances:
            woo_templates = woo_product_tmpl_obj.search(
                    [('woo_instance_id', '=', instance.id), ('id', 'in', woo_tmpl_ids),
                     ('exported_in_woo', '=', True)])
            if not woo_templates:
                continue
            odoo_products = woo_templates.woo_product_ids.mapped('product_id').ids
            woo_product_tmpl_obj.with_context(
                    updated_products_in_inventory=odoo_products).woo_update_stock(instance,
                                                                                  woo_templates)

    def update_export_category_tags_coupons_in_woo(self):
        """
        This common method will be called from wizard of Update/Export Category and Tags.
        @author: Maulik Barad on Date 14-Dec-2019.
        """
        process_type = self._context.get("process", "")
        if process_type == "update_category":
            self.update_product_categ()
        elif process_type == "export_category":
            self.export_product_categ()
        elif process_type == "update_tags":
            self.update_tags_in_woo()
        elif process_type == "export_tags":
            self.export_tags_in_woo()
        elif process_type == "export_coupon":
            self.export_woo_coupons()
        elif process_type == "update_coupon":
            self.update_woo_coupons()
        return {'type':'ir.actions.client',
                'tag':'reload'}

    def export_tags_in_woo(self):
        """
        Exports tags in WooCommerce, which are not exported.
        @author: Maulik Barad on Date 13-Dec-2019.
        """
        woo_tags_obj = self.env["woo.tags.ept"]
        common_log_book_id = self.env["common.log.book.ept"].create({"type":"export",
                                                                     "module":"woocommerce_ept",
                                                                     "woo_instance_id":self.woo_instance_id.id,
                                                                     "active":True})
        if self._context.get("process", "") == "export_tags":
            tags_need_to_export = woo_tags_obj.search(
                    [("id", "in", self._context.get("active_ids")),
                     ("exported_in_woo", "=", False)])
        else:
            tags_need_to_export = woo_tags_obj.search(
                    [("woo_instance_id", "=", self.woo_instance_id.id),
                     ("exported_in_woo", "=", False)])
        woo_tags_obj.woo_export_product_tags(tags_need_to_export.woo_instance_id,
                                             tags_need_to_export,
                                             common_log_book_id)

    def update_tags_in_woo(self):
        """
        Updates tags in WooCommerce, which are not exported.
        @author: Maulik Barad on Date 13-Dec-2019.
        """
        woo_tags_obj = self.env["woo.tags.ept"]
        common_log_book_id = self.env["common.log.book.ept"].create({"type":"export",
                                                                     "module":"woocommerce_ept",
                                                                     "woo_instance_id":self.woo_instance_id.id,
                                                                     "active":True})
        if self._context.get("process", "") == "update_tags":
            tags_need_to_export = woo_tags_obj.search(
                    [("id", "in", self._context.get("active_ids")),
                     ("exported_in_woo", "=", True)])
        else:
            tags_need_to_export = woo_tags_obj.search(
                    [("woo_instance_id", "=", self.woo_instance_id.id),
                     ("exported_in_woo", "=", True)])
        woo_tags_obj.woo_update_product_tags(tags_need_to_export.woo_instance_id,
                                             tags_need_to_export,
                                             common_log_book_id)

    def update_product_categ(self):
        """- This method used to search Woocommerce category for update.
            @param : self
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13/12/2019.
        """
        product_categ_obj = self.env['woo.product.categ.ept']
        woo_categ_ids = self._context.get('active_ids')
        if woo_categ_ids and self._context.get('process'):
            instances = self.env['woo.instance.ept'].search([('state', '=', 'confirmed')])
            for instance in instances:
                woo_product_categs = product_categ_obj.search(
                        [('woo_categ_id', '!=', False), ('woo_instance_id', '=', instance.id),
                         ('exported_in_woo', '=', True), ('id', 'in', woo_categ_ids)])
                woo_product_categs and product_categ_obj.update_product_categs_in_woo(instance,
                                                                                      woo_product_categs)
        else:
            woo_product_categs = product_categ_obj.search(
                    [('woo_categ_id', '!=', False),
                     ('woo_instance_id', '=', self.woo_instance_id.id),
                     ('exported_in_woo', '=', True)])
            woo_product_categs and product_categ_obj.update_product_categs_in_woo(
                    self.woo_instance_id,
                    woo_product_categs)
        return True

    def export_product_categ(self):
        """- This method used to search Woocommerce category for export.
            @param : self
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14/12/2019.
        """
        common_log_book_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env['common.log.lines.ept']
        product_categ_obj = self.env['woo.product.categ.ept']
        model_id = common_log_line_obj.get_model_id("woo.product.categ.ept")
        common_log_book_vals = {"type":"export",
                                "module":"woocommerce_ept",
                                "active":True}
        woo_categ_ids = self._context.get('active_ids')
        # This is called while export product categories from Action
        if woo_categ_ids and self._context.get('process'):
            instances = self.env['woo.instance.ept'].search([('state', '=', 'confirmed')])
            for instance in instances:
                woo_product_categs = product_categ_obj.search(
                        [('woo_instance_id', '=', instance.id), ('exported_in_woo', '=', False),
                         ('id', 'in', woo_categ_ids)])
                if woo_product_categs:
                    common_log_book_vals.update({"woo_instance_id":instance.id})
                    commom_log_book_id = common_log_book_obj.create(common_log_book_vals)
                    product_categ_obj.export_product_categs(instance, woo_product_categs,
                                                            commom_log_book_id, model_id)
                    if not commom_log_book_id.log_lines:
                        commom_log_book_id.unlink()
        # This is called while export product categories from WooCommerce Operations
        else:
            woo_product_categs = product_categ_obj.search(
                    [('woo_instance_id', '=', self.woo_instance_id.id),
                     ('exported_in_woo', '=', False)])
            if woo_product_categs:
                common_log_book_vals.update({"woo_instance_id":self.woo_instance_id.id})
                commom_log_book_id = common_log_book_obj.create(common_log_book_vals)
                product_categ_obj.export_product_categs(self.woo_instance_id, woo_product_categs,
                                                        commom_log_book_id,
                                                        model_id)
                if not commom_log_book_id.log_lines:
                    commom_log_book_id.unlink()
        return True

    def import_woo_coupon(self):
        """
        this method is used to import coupons from woo commerce.
        :return:
        @author: Nilesh Parmar on date 17 Dec 2019.
        """
        # this method used to import product category.
        self.sync_woo_product_category()
        common_log_line_obj = self.env['common.log.lines.ept']
        coupons_obj = self.env['woo.coupons.ept']
        model_id = common_log_line_obj.get_model_id("woo.coupons.ept")
        common_log_book_id = self.env["common.log.book.ept"].create(
                {"type":"import",
                 "module":"woocommerce_ept",
                 "woo_instance_id":self.woo_instance_id.id,
                 "active":True})
        coupon_queue = coupons_obj.sync_woo_coupons(self.woo_instance_id, common_log_book_id, model_id)
        if not common_log_book_id.log_lines:
            common_log_book_id.unlink()
        return coupon_queue

    def export_woo_coupons(self):
        """
        this methos is used to export coupons to woo commerce
        :return:
        @author: Nilesh Parmar on date 17 Dec 2019.
        """
        common_log_book_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env['common.log.lines.ept']
        coupons_obj = self.env['woo.coupons.ept']
        model_id = common_log_line_obj.get_model_id("woo.coupons.ept")
        common_log_book_vals = ({"type":"import",
                                 "module":"woocommerce_ept",
                                 "active":True})
        coupons_ids = self._context.get('active_ids')
        if coupons_ids and self._context.get('process'):
            instances = self.env['woo.instance.ept'].search([('state', '=', 'confirmed')])
            for instance in instances:
                woo_coupons = coupons_obj.search(
                        [('woo_instance_id', '=', instance.id), ('exported_in_woo', '=', False),
                         ('id', 'in', coupons_ids)])
                if not woo_coupons:
                    continue
                common_log_book_vals.update({"woo_instance_id":instance.id})
                common_log_book_id = common_log_book_obj.create(common_log_book_vals)
                coupons_obj.export_coupons(instance, woo_coupons, common_log_book_id, model_id)
                if not common_log_book_id.log_lines:
                    common_log_book_id.unlink()
        else:
            woo_coupons = coupons_obj.search(
                    [('woo_instance_id', '=', self.woo_instance_id.id),
                     ('exported_in_woo', '=', False)])
            common_log_book_vals.update({"woo_instance_id":self.woo_instance_id.id})
            common_log_book_id = common_log_book_obj.create(common_log_book_vals)
            if woo_coupons:
                coupons_obj.export_coupons(self.woo_instance_id, woo_coupons, common_log_book_id,
                                           model_id)
                if not common_log_book_id.log_lines:
                    common_log_book_id.unlink()

    def update_woo_coupons(self):
        """
        this method is used to update coupons in woo commerce
        :return:
        @author: Nilesh Parmar on date 17 Dec 2019.
        """
        coupon_obj = self.env['woo.coupons.ept']
        model_id = self.env["common.log.lines.ept"].get_model_id("woo.coupons.ept")
        common_log_book_id = self.env["common.log.book.ept"].create(
                {"type":"export",
                 "module":"woocommerce_ept",
                 "woo_instance_id":self.woo_instance_id.id,
                 "active":True})

        coupon_ids = self._context.get('active_ids')
        if coupon_ids and self._context.get('process'):
            coupon_ids = coupon_obj.search([('id', 'in', coupon_ids), ('coupon_id', '!=', False),
                                            ('exported_in_woo', '=', True)])
        else:
            coupon_ids = coupon_obj.search([('coupon_id', '!=', False),
                                            ('woo_instance_id', '=', self.woo_instance_id.id),
                                            ('exported_in_woo', '=', True)])
        if coupon_ids:
            coupon_obj.update_woo_coupons(coupon_ids.woo_instance_id, coupon_ids,
                                          common_log_book_id, model_id)

    def import_products_from_csv(self):
        """
        This method used to import products using CSV file which exported from Woo export products.
        @param : self : It contain the current class instance
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        :return: It will return the True the process is completed.
        Migration done by Haresh Mori @ Emipro on date 14 September 2020 .
        """
        woo_common_log_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id("woo.process.import.export")
        instance_id = self.woo_instance_id

        if not self.choose_file:
            raise UserError(_('Please Select the file for start process of Product Sync'))
        if self.file_name and not self.file_name.lower().endswith('.csv'):
            raise UserError(_("Please provide only CSV File to Import Products"))

        file_data = self.read_csv_file()

        required_field = ['template_name', 'product_name', 'product_default_code',
                          'woo_product_default_code', 'product_description', 'sale_description',
                          'PRODUCT_TEMPLATE_ID', 'PRODUCT_ID', 'CATEGORY_ID']
        for required_field in required_field:
            if not required_field in file_data.fieldnames:
                raise UserError(_("Required Column %s Is Not Available In CSV File") % required_field)

        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':instance_id.id,
                    'active':True,
                    'model_id':model_id,
                })

        row_no = 0
        product_tmpl_list = []
        for record in file_data:
            if not record['PRODUCT_TEMPLATE_ID'] or not record['PRODUCT_ID']:
                message = ""
                if not record['PRODUCT_TEMPLATE_ID']:
                    if message:
                        message += ', \n'
                    message += 'Product Template Id not available in Row Number %s' % row_no
                if not record['PRODUCT_ID']:
                    if message:
                        message += ', \n'
                    message += 'Product Id not available in Row Number %s' % row_no
                vals = {
                    'message':message,
                    'model_id':model_id,
                    'log_book_id':woo_common_log_id.id,
                }
                common_log_line_obj.create(vals)
                row_no += 1
                continue

            product_tmpl_id = record['PRODUCT_TEMPLATE_ID']
            if product_tmpl_id not in product_tmpl_list:
                woo_template = self.create_or_update_woo_template(instance_id, record)

            product_tmpl_list.append(product_tmpl_id)

            self.create_or_update_woo_variant(instance_id, record, woo_template)

            row_no += 1

        if not woo_common_log_id.log_lines:
            woo_common_log_id.unlink()

        return True

    def read_csv_file(self):
        """
            Read selected .csv file based on delimiter
            @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
            :return: It will return the object of csv file data
            Migration done by Haresh Mori @ Emipro on date 14 September 2020 .
        """
        self.write({'csv_data':self.choose_file})
        self._cr.commit()
        import_file = BytesIO(base64.decodebytes(self.csv_data))
        file_read = StringIO(import_file.read().decode())
        reader = csv.DictReader(file_read, delimiter=',')
        return reader

    def create_or_update_woo_template(self, instance_id, record):
        """ This method uses to create/update the Woocmmerce layer template.
            @param : self, instance_id
            @return: woo_template
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14 September 2020 .
            Task_id: 165896
        """
        product_tmpl_obj = self.env['product.template']
        woo_product_template = self.env['woo.product.template.ept']
        category_obj = self.env['product.category']
        woo_prepare_product_for_export_obj = self.env['woo.prepare.product.for.export.ept']
        woo_category_dict = {}
        woo_template = woo_product_template.search(
                [('woo_instance_id', '=', instance_id.id),
                 ('product_tmpl_id', '=', int(record['PRODUCT_TEMPLATE_ID']))])
        product_template = product_tmpl_obj.browse(int(record['PRODUCT_TEMPLATE_ID']))
        if len(product_template.product_variant_ids) == 1:
            product_type = 'simple'
        else:
            product_type = 'variable'
        woo_template_vals = {
            'product_tmpl_id':int(record['PRODUCT_TEMPLATE_ID']),
            'woo_instance_id':instance_id.id,
            'name':record['template_name'],
            'woo_product_type':product_type
        }

        if self.env["ir.config_parameter"].sudo().get_param(
                "woo_commerce_ept.set_sales_description"):
            woo_template_vals.update({'woo_description':record.get('sale_description'),
                                      'woo_short_description':record.get('product_description')})

        categ_id = category_obj.browse(int(record.get('CATEGORY_ID'))) if record.get(
                'CATEGORY_ID') else ''

        if categ_id:
            woo_category_dict = woo_prepare_product_for_export_obj.create_categ_in_woo(categ_id, instance_id.id, woo_category_dict)
            woo_categ_id = woo_prepare_product_for_export_obj.update_category_info(categ_id, instance_id.id)
            woo_template_vals.update({'woo_categ_ids':[(6, 0, woo_categ_id.ids)]})

        if not woo_template:
            woo_template = woo_product_template.create(woo_template_vals)
        else:
            woo_template.write(woo_template_vals)

        # For adding all odoo images into Woo layer.
        woo_prepare_product_for_export_obj.create_woo_template_images(woo_template)

        return woo_template

    def create_or_update_woo_variant(self, instance_id, record, woo_template):
        """ This method uses to create/update the Woocmmerce layer variant.
            @param : self, instance_id, record, woo_template
            @return: woo_template
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14 September 2020 .
            Task_id: 165896
        """
        woo_product_obj = self.env['woo.product.product.ept']
        woo_prepare_product_for_export_obj = self.env['woo.prepare.product.for.export.ept']
        woo_variant = woo_product_obj.search(
                [('woo_instance_id', '=', instance_id.id), ('product_id', '=', int(record['PRODUCT_ID'])),
                 ('woo_template_id', '=', woo_template.id)])

        woo_variant_vals = ({
            'woo_instance_id':instance_id.id,
            'product_id':int(record['PRODUCT_ID']),
            'woo_template_id':woo_template.id,
            'default_code':record['woo_product_default_code'],
            'name':record['product_name'],
        })

        if not woo_variant:
            woo_variant = woo_product_obj.create(woo_variant_vals)
        else:
            woo_variant.write(woo_variant_vals)

        # For adding all odoo images into Woo layer.
        woo_prepare_product_for_export_obj.create_woo_variant_images(woo_template.id, woo_variant)

        return woo_variant
