# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import ast
import logging

import requests

_logger = logging.getLogger("Woo")

from odoo import models, fields, api


class WooCoupons(models.Model):
    _name = "woo.coupons.ept"
    _rec_name = "code"
    _description = "Woo Coupon"

    coupon_id = fields.Char("WooCommerce Id", size=120,help="WooCommerce coupon id")
    code = fields.Char("Code", required=1, help="Coupon code")
    description = fields.Text('Description', help="Coupon description.")
    discount_type = fields.Selection([('percent', 'Percentage Discount'),
                                      ('fixed_cart', 'Fixed Cart Discount'),
                                      ('fixed_product', 'Fixed Product Discount')
                                      ], "Discount Type", default="fixed_cart",
                                     help="Determines the type of discount that will be applied.")
    amount = fields.Float("Amount", help="The amount of discount.")
    free_shipping = fields.Boolean("Allow Free Shipping",
                                   help="Check this box if the coupon grants free shipping."
                                        "A free shipping method must be enabled in your shipping"
                                        "zone and be set to require \"a valid free shipping coupon\""
                                        "(see the \"Free Shipping Requires\""
                                        "setting in WooCommerce).")
    expiry_date = fields.Date("Expiry Date", help="Coupon expiry date")
    minimum_amount = fields.Float("Minimum Spend",
                                  help="Minimum order amount that needs to be in the cart before coupon applies.")
    maximum_amount = fields.Float("Maximum Spend", help="Maximum order amount allowed when using"
                                                        "the coupon.")
    individual_use = fields.Boolean("Individual Use",
                                    help="If true, the coupon can only be used individually."
                                         "Other applied coupons will be removed from the cart.")
    exclude_sale_items = fields.Boolean("Exclude Sale Items",
                                        help="Check this box if the coupon should not apply "
                                             "to items on sale. Per-item coupons will only work"
                                             "if the item is not on sale. Per-cart coupons will"
                                             "only work if there are no sale items in the cart.")
    product_ids = fields.Many2many("woo.product.template.ept", 'woo_product_tmpl_product_rel',
                                   'product_ids', 'woo_product_ids', "Products",
                                   help="List of product IDs the coupon can be used on.")
    product_variant_ids = fields.Many2many("woo.product.product.ept",
                                           'woo_prodcut_variant_product_rel',
                                           'product_variant_id', 'woo_product_id',
                                           string="Product Variants",
                                           help="List of product variants IDs the coupon can be used on.")

    exclude_product_ids = fields.Many2many("woo.product.template.ept",
                                           'woo_product_tmpl_exclude_product_rel',
                                           'exclude_product_ids', 'woo_product_ids',
                                           "Exclude Products", help="List of product IDs the coupon cannot be used on.")

    exclude_product_variant_ids = fields.Many2many("woo.product.product.ept",
                                                   'woo_prodcut_variant_exclude_product_rel',
                                                   'exclude_product_variant_id',
                                                   'exclude_woo_product_id',
                                                   string="Exclude Product Variants",
                                                   help="List of product variants IDs the coupon cannot be used on.")

    product_category_ids = fields.Many2many('woo.product.categ.ept',
                                            'woo_template_categ_incateg_rel',
                                            'product_category_ids', 'woo_categ_id',
                                            "Product Categories")
    excluded_product_category_ids = fields.Many2many('woo.product.categ.ept',
                                                     'woo_template_categ_exclude_categ_rel',
                                                     'excluded_product_category_ids',
                                                     'woo_categ_id', "Exclude Product Categories")
    email_restrictions = fields.Char("Email restrictions",
                                     help="List of email addresses that can use this coupon,"
                                          "Enter Email ids Separated by comma(,)", default="")
    usage_limit = fields.Integer("Usage limit per coupon",
                                 help="How many times the coupon can be used in total.")
    limit_usage_to_x_items = fields.Integer("Limit usage to X items",
                                            help="Max number of items in the cart the coupon can"
                                                 "be applied to.")
    usage_limit_per_user = fields.Integer("Usage limit per user",
                                          help="How many times the coupon can be used per"
                                               "customer.")
    usage_count = fields.Integer("Usage Count", help="Number of times the coupon has been used already.")
    used_by = fields.Char("Used By", help="List of user IDs (or guest email addresses)"
                                          "that have used the coupon.")
    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance", required=1)
    exported_in_woo = fields.Boolean("Exported in WooCommerce")
    active = fields.Boolean(string="Active", default=True)
    _sql_constraints = [('code_unique', 'unique(code,woo_instance_id)', "Code already exists."
                                                                        "Code must be unique!")]

    def create_woo_coupon_log_lines(self, message, common_log_book_id, queue_line=False):
        """
        Creates log line for the failed queue line.
        @param queue_line: Failed queue line.
        @param message: Cause of failure.
        @return: Created log line.
        @author: Nilesh Parmar
        """
        log_line_obj = self.env["common.log.lines.ept"]
        log_line_vals = {"message": message,
                         "model_id": log_line_obj.get_model_id(self._name)}
        if queue_line:
            log_line_vals.update({"woo_coupon_data_queue_line_id": queue_line.id})
            queue_line.state = "failed"
        if common_log_book_id:
            log_line_vals.update({"log_book_id": common_log_book_id.id})
        return log_line_obj.create(log_line_vals)

    def create_or_write_coupon(self, queue_lines, common_log_book_id=False):
        """
        this method is used to create new coupons or update the coupons which available in odoo.
        :param instance: instance of woo commerce
        :param coupons: coupons data and type list
        :return:
        @author : Nilesh Parmar on date 17 Dec 2019.
        """
        woo_product_categ_ept_obj = self.env["woo.product.categ.ept"]
        woo_product_template_ept_obj = self.env["woo.product.template.ept"]
        woo_product_product_obj = self.env['woo.product.product.ept']
        instance = queue_lines.instance_id
        woo_coupons = []
        commit_count = 0
        for queue_line in queue_lines:
            commit_count += 1
            if commit_count == 10:
                # This is used for commit every 10 coupons
                queue_line.coupon_data_queue_id.is_process_queue = True
                self._cr.commit()
                commit_count = 0
            coupon = ast.literal_eval(queue_line.coupon_data)
            coupon_id = coupon.get("id")
            if not coupon.get("code"):
                message = "Coupon code not available in coupon number %s" % (coupon_id)
                self.create_woo_coupon_log_lines(message, common_log_book_id, queue_line)
                continue
            code = coupon.get("code")
            if instance.woo_version == 'wc/v3':
                woo_product_categ = woo_product_categ_ept_obj.search(
                    [("woo_categ_id", "in", coupon.get("product_categories")),
                     ("woo_instance_id", "=", instance.id)]).ids
                product_category = [(6, False, woo_product_categ)] or ''
                exclude_woo_product_categ = woo_product_categ_ept_obj.search(
                    [("woo_categ_id", "in", coupon.get("excluded_product_categories")),
                     ("woo_instance_id", "=", instance.id)]).ids
                exclude_product_category = [(6, False, exclude_woo_product_categ)] or ''
                email_restriction = coupon.get("email_restrictions") or ''

            woo_coupon = self.with_context(active_test=False).search(
                ["&", "|", ('coupon_id', '=', coupon_id), ('code', '=', code), ('woo_instance_id', '=', instance.id)],
                limit=1)

            coupon_product_ids = coupon.get("product_ids")
            woo_product_ids = woo_product_template_ept_obj.search(
                [("woo_tmpl_id", "in", coupon_product_ids), ("woo_instance_id", "=", instance.id)])
            remain_products = list(set(coupon_product_ids) - set(list(map(int,woo_product_ids.mapped("woo_tmpl_id")))))
            woo_variant_ids = woo_product_product_obj.search(
                [("variant_id", "in", remain_products), ("woo_instance_id", "=", instance.id)])
            remain_products = list(set(remain_products) - set(list(map(int,woo_variant_ids.mapped("variant_id")))))

            coupon_exclude_product_id = coupon.get("excluded_product_ids")
            exclude_woo_product_ids = woo_product_template_ept_obj.search(
                [("woo_tmpl_id", "in", coupon_exclude_product_id),
                 ("woo_instance_id", "=", instance.id)])
            remain_exclude_products = list(
                set(coupon_exclude_product_id) - set(list(map(int,exclude_woo_product_ids.mapped("woo_tmpl_id")))))
            exclude_woo_variant_ids = woo_product_product_obj.search(
                [("variant_id", "in", remain_exclude_products),
                 ("woo_instance_id", "=", instance.id)])
            remain_exclude_products = list(set(remain_exclude_products) - set(list(map(int,exclude_woo_variant_ids.mapped("variant_id")))))

            if remain_products or remain_exclude_products:
                message = "System could not import coupon '{0}'. Some of the products are not imported in odoo.".format(
                    code)
                self.create_woo_coupon_log_lines(message, common_log_book_id, queue_line)
                continue

            email_ids = ""
            if email_restriction:
                email_ids = ",".join(email_restriction)

            vals = {
                'coupon_id': coupon_id,
                'code': code,
                'description': coupon.get("description"),
                'discount_type': coupon.get("discount_type"),
                'amount': coupon.get("amount"),
                'free_shipping': coupon.get("free_shipping"),
                'expiry_date': coupon.get("date_expires") or False,
                'minimum_amount': float(coupon.get("minimum_amount", 0.0)),
                'maximum_amount': float(coupon.get("maximum_amount", 0.0)),
                'individual_use': coupon.get("individual_use"),
                'exclude_sale_items': coupon.get("exclude_sale_items"),
                'product_ids': [(6, False, woo_product_ids.ids)],
                'product_variant_ids': [(6, False, woo_variant_ids.ids)],
                'exclude_product_ids': [(6, False, exclude_woo_product_ids.ids)],
                'exclude_product_variant_ids': [(6, False, exclude_woo_variant_ids.ids)] or '',
                'product_category_ids': product_category or '',
                'excluded_product_category_ids': exclude_product_category or '',
                'email_restrictions': email_ids,
                'usage_limit': coupon.get("usage_limit"),
                'limit_usage_to_x_items': coupon.get("limit_usage_to_x_items"),
                'usage_limit_per_user': coupon.get("usage_limit_per_user"),
                'usage_count': coupon.get("usage_count"),
                'used_by': coupon.get("used_by"),
                'woo_instance_id': instance.id,
                'exported_in_woo': True,
                'active': True
            }
            if not woo_coupon:
                woo_coupon = self.create(vals)
                queue_line.state = 'done'
            else:
                woo_coupon.write(vals)
                queue_line.state = 'done'
            woo_coupons += woo_coupon
            queue_line.coupon_data_queue_id.is_process_queue = False
        return woo_coupons

    def woo_import_all_coupons(self, wcapi, instance, page, common_log_book_id, model_id):
        """
        this method is used to import the all coupons from woo commerce.
        :param wcapi:
        :param instance: woo commerce instance
        :param page: coupons data page no
        :param common_log_book_id: common log book id for create a log.
        :param model_id:
        :return:
        @author : Nilesh Parmar on date 17 Dec 2019.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        res = wcapi.get("coupons", params={"per_page": 100, 'page': page})
        if not isinstance(res, requests.models.Response):
            message = "Get Coupons \nResponse is not in proper format :: %s" % (res)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            return True
        if res.status_code not in [200, 201]:
            message = res.content
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            return True
        try:
            result = res.json()
        except Exception as e:
            message = "Json Error : While import coupon from WooCommerce for instance %s. \n%s" % (
                instance.name, e),
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            return False
        return result

    def create_woo_coupon_data_queue(self, woo_instance, coupon_data, created_by="import"):
        """
        Creates coupon data queues from the data got from API.
        @param woo_instance: Instance of Woocommerce.
        @param coupon_data: Imported JSON data of coupons.
        @author : Nilesh Parmar update on date 31 Dec 2019.
        """
        woo_coupon_data_queue_obj = self.env["woo.coupon.data.queue.ept"]
        vals = {"woo_instance_id": woo_instance.id, "created_by":created_by}
        coupon_queues = []
        while coupon_data:
            data = coupon_data[:100]
            if data:
                coupon_data_queue = woo_coupon_data_queue_obj.create(vals)
                coupon_queues.append(coupon_data_queue.id)
                _logger.info("New coupon queue %s created." % (coupon_data_queue.name))
                coupon_data_queue.create_woo_data_queue_lines(data)
                _logger.info("Lines added in Coupon queue %s." % (coupon_data_queue.name))
                del coupon_data[:100]
        _logger.info("Import coupon process completed.")
        return coupon_queues

    def sync_woo_coupons(self, instance, common_log_book_id, model_id):
        common_log_line_obj = self.env["common.log.lines.ept"]
        wcapi = instance.woo_connect()
        res = wcapi.get('coupons', params={"per_page": 100})

        if not isinstance(res, requests.models.Response):
            message = "Get Coupons \nResponse is not in proper format :: %s" % (res)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            return True
        if res.status_code not in [200, 201]:
            message = res.content
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            return True
        results = []
        total_pages = res and res.headers.get('x-wp-totalpages', 0) or 1

        try:
            res = res.json()
        except Exception as e:
            message = "Json Error : While import coupon from WooCommerce for instance %s. \n%s" % (
                instance.name, e),
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            return False
        results = res

        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                results += self.woo_import_all_coupons(wcapi, instance, page, common_log_book_id, model_id)
        if not results:
            _logger.info("Coupons data not found from woo")
            return True
        coupon_queue  = self.create_woo_coupon_data_queue(instance, results)

        return coupon_queue

    @api.model
    def export_coupons(self, instance, woo_coupons, common_log_book_id, model_id):
        """
        this method used to export the coupons to woo commerce
        :param instance:
        :param woo_coupons:
        :param common_log_book_id:
        :param model_id:
        :return:
        @author: Nilesh Parmar on 16 Dec 2019
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        for instance in instance:
            wcapi = instance.woo_connect()
            coupons = []
            for woo_coupon in woo_coupons:
                woo_product_tmpl_ids = []
                woo_product_exclude_tmpl_ids = []
                woo_category_ids = []
                woo_exclude_category_ids = []
                for product_tmpl_id in woo_coupon.product_ids:
                    woo_product_tmpl_ids.append(product_tmpl_id.woo_tmpl_id)
                for product_variant in woo_coupon.product_variant_ids:
                    woo_product_tmpl_ids.append(product_variant.variant_id)
                for exclude_product_tmpl_id in woo_coupon.exclude_product_ids:
                    woo_product_exclude_tmpl_ids.append(exclude_product_tmpl_id.woo_tmpl_id)
                for exclude_variant in woo_coupon.exclude_product_variant_ids:
                    woo_product_exclude_tmpl_ids.append(exclude_variant.variant_id)
                for categ_id in woo_coupon.product_category_ids:
                    woo_category_ids.append(categ_id.woo_categ_id)
                for exclude_categ_id in woo_coupon.excluded_product_category_ids:
                    woo_exclude_category_ids.append(exclude_categ_id.woo_categ_id)
                email_ids = []
                if woo_coupon.email_restrictions:
                    email_ids = woo_coupon.email_restrictions.split(",")
                vals = {'code': woo_coupon.code,
                        'description': str(woo_coupon.description or '') or '',
                        'discount_type': woo_coupon.discount_type,
                        'free_shipping': woo_coupon.free_shipping,
                        'amount': str(woo_coupon.amount),
                        'date_expires': "{}".format(woo_coupon.expiry_date or ''),
                        'minimum_amount': str(woo_coupon.minimum_amount),
                        'maximum_amount': str(woo_coupon.maximum_amount),
                        'individual_use': woo_coupon.individual_use,
                        'exclude_sale_items': woo_coupon.exclude_sale_items,
                        'product_ids': woo_product_tmpl_ids,
                        'excluded_product_ids': woo_product_exclude_tmpl_ids,
                        'product_categories': woo_category_ids,
                        'excluded_product_categories': woo_exclude_category_ids,
                        'email_restrictions': email_ids,
                        'usage_limit': woo_coupon.usage_limit,
                        'limit_usage_to_x_items': woo_coupon.limit_usage_to_x_items,
                        'usage_limit_per_user': woo_coupon.usage_limit_per_user,
                        }
                coupons.append(vals)
            coupons_data = {"create": coupons}
            _logger.info("Exporting coupons to Woo of instance {0}".format(instance.name))
            res = wcapi.post("coupons/batch", coupons_data)
            if not res:
                message = "Export Coupons \nResponse is not in proper format :: %s" % (res)
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)

            if res.status_code not in [200, 201]:
                message = "Can not Export Coupons, %s" % (res.content),
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
                continue

            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While export coupon to WooCommerce for instance %s." \
                          "\n%s" % (instance.name, e)
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
                continue
            exported_coupons = response.get("create")
            for woo_coupon in exported_coupons:
                exported_coupon = woo_coupons.filtered(
                    lambda x: x.code.lower() == woo_coupon.get("code") and x.woo_instance_id == instance)
                if woo_coupon.get("id", False) and exported_coupon:
                    exported_coupon.write({"coupon_id": woo_coupon.get("id"),
                                           "exported_in_woo": True,
                                           "code":woo_coupon.get("code"),
                                           })
            _logger.info("Exported {0} coupons to Woo of instance {1}".format(len(exported_coupons), instance.name))

    def update_woo_coupons(self, instances, woo_coupons, common_log_book_id, model_id):
        common_log_line_obj = self.env["common.log.lines.ept"]
        for instance in instances:
            wcapi = instance.woo_connect()
            coupons = []
            for woo_coupon in woo_coupons:
                woo_product_tmpl_ids = []
                woo_product_exclude_tmpl_ids = []
                woo_category_ids = []
                woo_exclude_category_ids = []
                for product_tmpl_id in woo_coupon.product_ids:
                    woo_product_tmpl_ids.append(product_tmpl_id.woo_tmpl_id)
                for product_variant in woo_coupon.product_variant_ids:
                    woo_product_tmpl_ids.append(product_variant.variant_id)
                for exclude_product_tmpl_id in woo_coupon.exclude_product_ids:
                    woo_product_exclude_tmpl_ids.append(exclude_product_tmpl_id.woo_tmpl_id)
                for exclude_variant in woo_coupon.exclude_product_variant_ids:
                    woo_product_exclude_tmpl_ids.append(exclude_variant.variant_id)
                for categ_id in woo_coupon.product_category_ids:
                    woo_category_ids.append(categ_id.woo_categ_id)
                for exclude_categ_id in woo_coupon.excluded_product_category_ids:
                    woo_exclude_category_ids.append(exclude_categ_id.woo_categ_id)

                email_ids = []
                if woo_coupon.email_restrictions:
                    email_ids = woo_coupon.email_restrictions.split(",")

                vals = {'code': woo_coupon.code,
                        'description': str(woo_coupon.description or '') or '',
                        'discount_type': woo_coupon.discount_type,
                        'free_shipping': woo_coupon.free_shipping,
                        'amount': str(woo_coupon.amount),
                        'date_expires': "{}".format(woo_coupon.expiry_date or ''),
                        'minimum_amount': str(woo_coupon.minimum_amount),
                        'maximum_amount': str(woo_coupon.maximum_amount),
                        'individual_use': woo_coupon.individual_use,
                        'exclude_sale_items': woo_coupon.exclude_sale_items,
                        'product_ids': woo_product_tmpl_ids,
                        'excluded_product_ids': woo_product_exclude_tmpl_ids,
                        'product_categories': woo_category_ids,
                        'excluded_product_categories': woo_exclude_category_ids,
                        'email_restrictions': email_ids,
                        'usage_limit': woo_coupon.usage_limit,
                        'limit_usage_to_x_items': woo_coupon.limit_usage_to_x_items,
                        'usage_limit_per_user': woo_coupon.usage_limit_per_user,
                        }

                vals.update({'id': woo_coupon.coupon_id})
                coupons.append(vals)
            _logger.info("Exporting coupons to Woo of instance {0}".format(instance.name))
            res = wcapi.put("coupons/batch", {'update': coupons})
            if not isinstance(res, requests.models.Response):
                message = "Update Coupon \nResponse is not in proper format :: %s" % (
                    res)
                common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_book_id,
                                                                False)
                return False

            if res.status_code not in [200, 201]:
                if res.status_code == 500:
                    try:
                        response = res.json()
                    except Exception as e:
                        message = "Json Error : While updating coupon to WooCommerce for instance " \
                                  "%s. \n%s" % (instance.name, e)
                        common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
                    if isinstance(response, dict) and response.get("code") == "term_exists":
                        woo_coupon.write(
                            {"code": response.get("code"), "exported_in_woo": True})
                    else:
                        message = res.content
                        common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While updating Coupon to WooCommerce for instance %s. \n%s" \
                          % (instance.name, e)
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id, False)
                return False
