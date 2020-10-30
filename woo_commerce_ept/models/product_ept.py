# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta

import requests

from odoo import models, fields, api
from ..img_upload import img_file_upload

_logger = logging.getLogger("Woo")

class WooProductTemplateEpt(models.Model):
    _name = "woo.product.template.ept"
    _order = 'product_tmpl_id'
    _description = "Woo Product Template"

    @api.depends('woo_product_ids.exported_in_woo', 'woo_product_ids.variant_id')
    def _compute_total_sync_variants(self):
        """
        :param : self :- It is the browsable object of woo product template class
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        woo_product_obj = self.env['woo.product.product.ept']
        for template in self:
            variants = woo_product_obj.search(
                    [('id', 'in', template.woo_product_ids.ids), ('exported_in_woo', '=', True),
                     ('variant_id', '!=', False)])
            template.total_sync_variants = len(variants)

    name = fields.Char("Name", translate=True)
    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance", required=1)
    product_tmpl_id = fields.Many2one("product.template", "Product Template", required=1,
                                      ondelete="cascade")
    active = fields.Boolean("Active", default=True)
    woo_description = fields.Html("Description", translate=True)
    woo_short_description = fields.Html("Short Description", translate=True)
    taxable = fields.Boolean("Taxable", default=True)
    woo_tmpl_id = fields.Char("Woo Template Id", size=120)
    exported_in_woo = fields.Boolean("Exported In Woo")
    website_published = fields.Boolean('Available in the website', copy=False)
    created_at = fields.Datetime("Created At")
    updated_at = fields.Datetime("Updated At")
    total_variants_in_woo = fields.Integer("Total Varaints in Woo", default=0,
                                           help="Total Variants in WooCommerce,"
                                                "\nDisplay after sync products")
    total_sync_variants = fields.Integer("Total Sync Variants",
                                         compute="_compute_total_sync_variants", store=True)
    woo_product_ids = fields.One2many("woo.product.product.ept", "woo_template_id", "Products")

    woo_categ_ids = fields.Many2many('woo.product.categ.ept', 'woo_template_categ_rel',
                                     'woo_template_id',
                                     'woo_categ_id', "Categories")
    woo_tag_ids = fields.Many2many('woo.tags.ept', 'woo_template_tags_rel', 'woo_template_id',
                                   'woo_tag_id', "Tags")
    # woo_product_type = fields.Selection([('simple', 'Simple Product'),
    #                                      ('variable', 'Variable product')],
    #                                     string='Woo Product Type',
    #                                     compute="_compute_woo_product_type", store=True)
    woo_product_type = fields.Selection([('simple', 'Simple'),
                                         ('variable', 'Variable'),
                                         ('bundle', 'Bundle'),
                                         ('grouped', 'Grouped'),
                                         ('external', 'External')])
    woo_image_ids = fields.One2many("woo.product.image.ept", "woo_template_id")

    # @api.depends("woo_product_ids")
    # def _compute_woo_product_type(self):
    #     """
    #     This method will set the product's type by counting the variants of a product.
    #     """
    #     for record in self:
    #         if len(record.woo_product_ids) > 1:
    #             record.woo_product_type = "variable"
    #         else:
    #             record.woo_product_type = "simple"

    @api.onchange("product_tmpl_id")
    def on_change_product(self):
        for record in self:
            record.name = record.product_tmpl_id.name

    def write(self, vals):
        """
        This method use to archive/unarchive woo product variants base on woo product templates.
        :parameter: self, vals
        :return: res
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 09/12/2019.
        :Task id: 158502
        """
        woo_product_product_obj = self.env['woo.product.product.ept']
        if 'active' in vals.keys():
            for woo_template in self:
                woo_template.woo_product_ids and woo_template.woo_product_ids.write(
                        {'active':vals.get('active')})
                if vals.get('active'):
                    woo_variants = woo_product_product_obj.search(
                            [('woo_template_id', '=', woo_template.id),
                             ('woo_instance_id', '=', woo_template.woo_instance_id.id),
                             ('active', '=', False)])
                    woo_variants and woo_variants.write({'active':vals.get('active')})
        res = super(WooProductTemplateEpt, self).write(vals)
        return res

    @api.model
    def get_variant_image(self, instance, variant):
        """
         This method is used for get the image of product and upload that image in woo commerce
        :param instance: It contain the browsable object of the current instance
        :param variant: It contain the woo product variant
        :return: return the image response in dictionary
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        Migration done by Haresh Mori @ Emipro on date 21 September 2020 .
        """
        image_id = False
        variation_data = {}
        variant_images = variant.woo_image_ids

        if variant_images:
            if not variant_images[0].woo_image_id:
                res = img_file_upload.upload_image(instance, variant_images[0].image,
                                                   "%s_%s" % (variant.name, variant.id),variant_images[0].image_mime_type)
                image_id = res and res.get('id', False) or ''
            else:
                image_id = variant_images[0].woo_image_id

        if image_id:
            variation_data.update({"image":{'id':image_id}})
            variant_images[0].woo_image_id = image_id
            
        return variation_data

    @api.model
    def get_variant_data(self, variant, instance, update_image):
        """
        This method is used for prepare the product variant data with its image and return it into
        dictionary format
        :param variant: It contain the woo product variant
        :param instance: It contain the browsable object of the current instance
        :param update_image: It contain Either True or False
        :return: It will return the product variant details and its type is Dict.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        att = []
        woo_attribute_obj = self.env['woo.product.attribute.ept']
        variation_data = {}
        att_data = {}
        for attribute_value in variant.product_id.product_template_attribute_value_ids:
            if instance.woo_attribute_type == 'select':
                woo_attribute = woo_attribute_obj.search(
                        [('name', '=', attribute_value.attribute_id.name),
                         ('woo_instance_id', '=', instance.id),
                         ('exported_in_woo', '=', True)], limit=1)
                if not woo_attribute:
                    woo_attribute = woo_attribute_obj.search(
                            [('attribute_id', '=', attribute_value.attribute_id.id),
                             ('woo_instance_id', '=', instance.id),
                             ('exported_in_woo', '=', True)], limit=1)
                att_data = {
                    'id':woo_attribute and woo_attribute.woo_attribute_id,
                    'option':attribute_value.name
                }
            if instance.woo_attribute_type == 'text':
                att_data = {
                    'name':attribute_value.attribute_id.name,
                    'option':attribute_value.name
                }
            att.append(att_data)
        if update_image:
            variation_data.update(self.get_variant_image(instance, variant))

        weight = self.convert_weight_by_uom(variant.product_id.weight, instance)

        variation_data.update(
                {
                    'attributes':att, 'sku':str(variant.default_code),
                    'weight':str(weight), "manage_stock":variant.woo_is_manage_stock
                })
        return variation_data

    @api.model
    def get_product_price(self, instance, variant):
        """
        It will get the product price based on pricelist and return it
        :param instance: It contain the browsable object of the current instance
        :param variant: It contain the woo product variant
        :return: It will return the product regular price and sale price into Dict Format.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        price = instance.woo_pricelist_id.get_product_price_ept(variant.product_id)
        return {'regular_price':str(price), 'sale_price':str(price)}

    def prepare_batches(self, data):
        """
        This method is used for create batches
        :param data:  It can be either object or list
        :return: list of batches
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd
        :Task id: 156886
        """
        batches = []
        start, end = 0, 100
        if len(data) > 100:
            while True:
                data_batch = data[start:end]
                if not data_batch:
                    break
                temp = end + 100
                start, end = end, temp
                if data_batch:
                    batches.append(data_batch)
        else:
            batches.append(data)
        return batches

    @api.model
    def woo_update_stock(self, instance, woo_templates):
        """
        This method is used for export stock from odoo to Woocommerce.
        :param instance: Instance Object
        :param woo_templates: Object of Woo Product Template
        :return: Boolean
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd On Data 19-Nov-2019
        :Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 10 September 2020 .
        """
        common_log_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        model = "woo.product.product.ept"
        model_id = common_log_line_obj.get_model_id(model)
        log_lines = []

        product_ids = woo_templates.mapped('woo_product_ids').mapped('product_id')
        product_stock = self.check_stock_type(instance, product_ids)
        variable_products = woo_templates.filtered(lambda x:x.woo_product_type == 'variable')
        simple_products = woo_templates.filtered(lambda x:x.woo_product_type == 'simple')
        if variable_products:
            log_lines += self.export_stock_variable_products(variable_products, product_stock,
                                                             instance, model_id)
        if simple_products:
            log_lines += self.export_stock_simple_products(simple_products, product_stock, instance,
                                                           model_id)

        instance.write({'last_inventory_update_time':datetime.now()})
        if log_lines:
            common_log_obj.create({
                'type':'export',
                'module':'woocommerce_ept',
                'woo_instance_id':instance.id,
                'active':True,
                'log_lines':[(6, 0, log_lines)],
            })
        return True

    def check_stock_type(self, instance, product_ids):
        """
        This Method relocates check type of stock.
        :param instance: This arguments relocates instance of Woocommerce.
        :param product_ids: This argumentes product listing id of odoo.
        :param prod_obj: This argument relocates product object of common connector.
        :param warehouse:This arguments relocates warehouse of Woocmmerce.
        :return: This Method return prouct listing stock.
        Migration done by Haresh Mori @ Emipro on date 11 September 2020 .
        """
        prod_obj = self.env['product.product']
        warehouse = instance.woo_warehouse_id
        products_stock = False
        if product_ids:
            if instance.woo_stock_field.name == 'free_qty':
                products_stock = prod_obj.get_qty_on_hand_ept(warehouse, product_ids.ids)
            elif instance.woo_stock_field.name == 'virtual_available':
                products_stock = prod_obj.get_forecasted_qty_ept(warehouse, product_ids.ids)
        return products_stock

    def export_stock_variable_products(self, woo_variable_products, product_stock, instance,
                                       model_id):
        """ This method used to export stock for variable products.
            @param : self,woo_variable_products,product_stock,instance
            @return: log_lines
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11 September 2020 .
            Task_id: 165895
        """
        log_lines = []
        common_log_line_obj = self.env["common.log.lines.ept"]
        wcapi = instance.woo_connect()
        _logger.info('==Start process of variable product for export stock')
        for template in woo_variable_products:
            info = {'id':template.woo_tmpl_id, 'variations':[]}
            for variant in template.woo_product_ids.filtered(lambda
                                                                     x:x.product_id.type == 'product' and x.woo_is_manage_stock and x.variant_id):
                if variant.product_id.id in self._context.get('updated_products_in_inventory'):
                    quantity = product_stock.get(variant.product_id.id)
                    if variant.fix_stock_type == 'fix' :
                        if variant.fix_stock_value < quantity :
                            quantity = variant.fix_stock_value
                    if variant.fix_stock_type == 'percentage':
                        percentage_stock = int((quantity * variant.fix_stock_value) / 100.0)
                        if percentage_stock < quantity:
                            quantity= percentage_stock

                    info.get('variations').append({
                        'id':variant.variant_id,
                        'manage_stock':True,
                        'stock_quantity':int(quantity)
                    })
            if info.get('variations'):
                variant_batches = self.prepare_batches(info.get('variations'))
                for woo_variants in variant_batches:
                    _logger.info(
                            'Export Stock||Variations batch processing for woo template name: %s' % (
                                template.name))
                    res = wcapi.post('products/%s/variations/batch' % (info.get('id')),
                                     {'update':woo_variants})
                    _logger.info(
                            'Export Stock||Variations batch process completed [status: %s] for Woo template name: %s' % (
                                res.status_code, template.name))
                    if res.status_code not in [200, 201]:
                        log_id = common_log_line_obj.create({
                            'model_id':model_id,
                            'message':"Update woo template: %s Stock\n%s" % (
                                template.name, res.content),
                        })
                        log_lines.append(log_id.id)
        _logger.info('==End process of variable product for export stock')
        return log_lines

    def export_stock_simple_products(self, woo_simple_products, product_stock, instance,
                                     model_id):
        """ This method used to export stock for simple products.
            @param : self,woo_simple_products,product_stock,instance
            @return: log_lines
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 11 September 2020 .
            Task_id: 165895
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        wcapi = instance.woo_connect()
        _logger.info('==Start process of simple product for export stock')
        batches = self.prepare_batches(woo_simple_products)
        log_lines = []
        for woo_products in batches:
            batch_update = {'update':[]}
            batch_update_data = []
            for template in woo_products:
                info = {'id':template.woo_tmpl_id, 'variations':[]}
                variant = template.woo_product_ids[0]
                if variant.woo_is_manage_stock:
                    quantity = product_stock.get(variant.product_id.id)
                    if variant.fix_stock_type == 'fix' :
                        if variant.fix_stock_value < quantity :
                            quantity = variant.fix_stock_value
                    if variant.fix_stock_type == 'percentage':
                        percentage_stock = int((quantity * variant.fix_stock_value) / 100.0)
                        if percentage_stock < quantity:
                            quantity= percentage_stock
                    info.update({'manage_stock':True, 'stock_quantity':int(quantity)})
                    batch_update_data.append(info)
            if batch_update_data:
                batch_update.update({'update':batch_update_data})
                _logger.info('products batch processing')
                res = wcapi.post('products/batch', batch_update)
                _logger.info('products batch completed [status: %s]', res.status_code)
                if not isinstance(res, requests.models.Response):
                    log_id = common_log_line_obj.create({
                        'model_id':model_id,
                        'message':"Update Product Stock \nResponse is not in proper format :: %s" % (
                            res),
                    })
                    log_lines.append(log_id.id)
                if res.status_code not in [200, 201]:
                    log_id = common_log_line_obj.create({
                        'model_id':model_id,
                        'message':res.content,
                    })
                    log_lines.append(log_id.id)
                try:
                    response = res.json()
                except Exception as e:
                    log_id = common_log_line_obj.create({
                        'model_id':model_id,
                        'message':"Json Error : While update product stock to WooCommerce for instance %s. \n%s" % (
                            instance.name, e),
                    })
                    log_lines.append(log_id.id)
                if response.get('data', {}) and response.get('data', {}).get('status') != 200:
                    message = response.get('message')
                    log_id = common_log_line_obj.create({
                        'model_id':model_id,
                        'message':message
                    })
                    log_lines.append(log_id.id)
        _logger.info('==End process of simple product for export stock')
        return log_lines

    def woo_unpublished(self):
        """
        This method is used for unpublish product from woo commerce store
        :param : self :- It is the browsable object of woo product template class
        :return: It will return True If product successfully unpublished from woo
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        instance = self.woo_instance_id
        woo_common_log_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':instance.id,
                    'active':True,
                })
        wcapi = instance.woo_connect()
        if self.woo_tmpl_id:
            data = {'status':'draft'}
            if instance.woo_version == 'v3':
                data = {'product':data}
            res = wcapi.put('products/%s' % (self.woo_tmpl_id), data)
            # res = wcapi.post('products/batch', {'update': [data]})
            if not isinstance(res, requests.models.Response):
                message = "Unpublish Product \nResponse is not in proper format :: %s" % (res)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return True
            if res.status_code not in [200, 201]:
                common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                                woo_common_log_id, False)
                return True
            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While Unpublish Product with id %s from WooCommerce " \
                          "for instance %s. \n%s" % (self.woo_tmpl_id, instance.name, e)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return False
            if instance.woo_version == 'v3':
                errors = response.get('errors', '')
                if errors:
                    message = errors[0].get('message')
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)

                else:
                    self.write({'website_published':False})
            else:
                if response.get('data', {}) and response.get('data', {}).get('status') not in [200,
                                                                                               201]:
                    message = response.get('message')
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)

                else:
                    self.write({'website_published':False})
        return True

    def woo_published(self):
        """
        This method is used for publish product in woo commerce store
        :param : self :- It is the browsable object of woo product template class
        :return: It will return True If product successfully published in woo
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        instance = self.woo_instance_id
        woo_common_log_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        woo_common_log_id = woo_common_log_obj.create(
                {
                    'type':'import',
                    'module':'woocommerce_ept',
                    'woo_instance_id':instance.id,
                    'active':True,
                })
        wcapi = instance.woo_connect()
        if self.woo_tmpl_id:
            data = {'status':'publish'}
            if instance.woo_version == 'v3':
                data = {'product':data}
            res = wcapi.put('products/%s' % (self.woo_tmpl_id), data)
            # res = wcapi.post('products/batch', {'update': [data]})
            if not isinstance(res, requests.models.Response):
                message = "Publish Product \nResponse is not in proper format :: %s" % (res)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return True
            if res.status_code not in [200, 201]:
                common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                                woo_common_log_id, False)
                return True
            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While Publish Product with id %s from WooCommerce " \
                          "for instance %s. \n%s" % (self.woo_tmpl_id, instance.name, e)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return False
            if instance.woo_version == 'v3':
                errors = response.get('errors', '')
                if errors:
                    message = errors[0].get('message')
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                else:
                    self.write({'website_published':True})
            else:
                if response.get('data', {}) and response.get('data', {}).get('status') not in [200,
                                                                                               201]:
                    message = response.get('message')
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                else:
                    self.write({'website_published':True})
        return True

    def import_all_attribute_terms(self, wcapi, instance, woo_attribute_id, woo_common_log_id,
                                   model_id, page):
        """
        This method is used for get the attribute value response as per request by page wise and return it
        :param wcapi: It contain the connection object between odoo and woo
        :param instance: It contain the browsable object of the current instance
        :param woo_attribute_id: It contain the Woo product Attribute and its type is Object
        :param woo_common_log_id: It contain the common log book id and its type is Object
        :param model_id: It contain the id of the model class
        :param page: It contain the page number of woo commerce and its type if Integer
        :return: It will return response based on send request
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        res = wcapi.get("products/attributes/%s/terms" % (
            woo_attribute_id.woo_attribute_id), params={'per_page':100, 'page':page})

        if not isinstance(res, requests.models.Response):
            message = "Get All Attribute Terms \nResponse is not in proper format :: %s" % (
                res)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id,
                                                            False)
            return []
        if res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                            woo_common_log_id,
                                                            False)
            return []
        try:
            response = res.json()
        except Exception as e:
            message = "Json Error : While import product attribute terms from WooCommerce for " \
                      "instance %s. \n%s " % (instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id,
                                                            False)
            return []

        return response

    def sync_woo_attribute_term(self, instance, woo_common_log_id, attribute_ids = False):
        """
         This method is used for send the request in woo and get the response of product attribute Values
         and create that attribute Value into woo commerce connector of odoo
        :param instance: It contain the browsable object of the current instance
        :param woo_common_log_id: It contain the log book id and its type is object
        :return: It will return True if the process is successfully completed.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id("woo.product.attribute.term.ept")
        obj_woo_attribute = self.env['woo.product.attribute.ept']
        obj_woo_attribute_term = self.env['woo.product.attribute.term.ept']
        odoo_attribute_value_obj = self.env['product.attribute.value']

        wcapi = instance.woo_connect()
        if not attribute_ids:
            woo_attributes = obj_woo_attribute.search([('woo_instance_id', '=', instance.id)])
        else:
            woo_attributes = obj_woo_attribute.search([('woo_instance_id', '=', instance.id),('woo_attribute_id', 'in',attribute_ids)])
        attributes_term_data = []
        for woo_attribute in woo_attributes:
            response = wcapi.get("products/attributes/%s/terms" % (woo_attribute.woo_attribute_id),
                    params={'per_page':100})
            try:
                attributes_term_data = response.json()
            except Exception as e:
                message = "Json Error : While import product attribute terms from WooCommerce " \
                          "for instance %s. \n%s " % (instance.name, e)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id,
                                                                False)
                return False

            if not isinstance(attributes_term_data, list):
                message = "Response is not in proper format :: %s" % (attributes_term_data)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id,
                                                                False)
                continue
            total_pages = response and response.headers.get('x-wp-totalpages') or 1
            if int(total_pages) >= 2:
                for page in range(2, int(total_pages) + 1):
                    attributes_term_data = attributes_term_data + self.import_all_attribute_terms(
                            wcapi, instance, woo_attribute, woo_common_log_id, model_id, page)
            if response.status_code in [201, 200]:
                for attribute_term in attributes_term_data:
                    woo_attribute_term = obj_woo_attribute_term.search(
                            [('woo_attribute_term_id', '=', attribute_term.get('id')),
                             ('woo_instance_id', '=', instance.id), ('exported_in_woo', '=', True)],
                            limit=1)
                    if woo_attribute_term:
                        continue
                    odoo_attribute_value = odoo_attribute_value_obj.search(
                            [('name', '=ilike', attribute_term.get('name')),
                             ('attribute_id', '=', woo_attribute.attribute_id.id)], limit=1)
                    if not odoo_attribute_value:
                        odoo_attribute_value = odoo_attribute_value.with_context(
                                active_id=False).create({
                            'name':attribute_term.get('name'),
                            'attribute_id':woo_attribute.attribute_id.id
                        })
                    woo_attribute_term = obj_woo_attribute_term.search(
                            [('attribute_value_id', '=', odoo_attribute_value.id),
                             ('attribute_id', '=', woo_attribute.attribute_id.id),
                             ('woo_attribute_id', '=', woo_attribute.id),
                             ('woo_instance_id', '=', instance.id),
                             ('exported_in_woo', '=', False)],
                            limit=1)
                    if woo_attribute_term:
                        woo_attribute_term.write({
                            'woo_attribute_term_id':attribute_term.get(
                                    'id'),
                            'count':attribute_term.get('count'),
                            'slug':attribute_term.get('slug'),
                            'exported_in_woo':True
                        })
                    else:
                        obj_woo_attribute_term.create({
                            'name':attribute_term.get('name'),
                            'woo_attribute_term_id':attribute_term.get(
                                    'id'),
                            'slug':attribute_term.get('slug'),
                            'woo_instance_id':instance.id,
                            'attribute_value_id':odoo_attribute_value.id,
                            'woo_attribute_id':woo_attribute.woo_attribute_id,
                            'attribute_id':woo_attribute.attribute_id.id,
                            'exported_in_woo':True,
                            'count':attribute_term.get('count')})
            else:
                common_log_line_obj.woo_product_export_log_line(attribute_term.content, model_id,
                                                                woo_common_log_id,
                                                                False)
                continue
        return True

    def woo_import_all_attributes(self, wcapi, instance, woo_common_log_id, model_id, page):
        """
        This method is used for get the attribute response as per request by page wise and return it
        :param wcapi: It contain the connection object between odoo and woo
        :param instance: It contain the browsable object of the current instance
        :param woo_common_log_id: It contain the log book id and its type is object
        :param model_id: It contain the id of the model class
        :param page: It contain the page number of woo commerce and its type if Integer
        :return: It will return the response of product attribute into Dict Format.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        res = wcapi.get('products/attributes', params={'per_page':100, 'page':page})

        if not isinstance(res, requests.models.Response):
            message = "Get All Attibutes \nResponse is not in proper format :: %s" % (res)
            common_log_line_obj.woo_product_export_log_line(message, model_id, woo_common_log_id,
                                                            False)
            return []
        if res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                            woo_common_log_id, False)
            return []
        try:
            response = res.json()
        except Exception as e:
            message = "Json Error : While import product attributes from WooCommerce for " \
                      "instance %s. \n%s " % (instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id, woo_common_log_id,
                                                            False)
            return []

        if instance.woo_version == 'v3':
            errors = response.get('errors', '')
            if errors:
                message = errors[0].get('message')
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id,
                                                                False)
                return []
            return response.get('product_attributes')
        else:
            return response

    def sync_woo_attribute(self, instance, woo_common_log_id):
        """
        This method is used for send the request in woo and get the response of product attribute
         and create that attribute into woo commerce connector of odoo
        :param instance: It contain the browsable object of the current instance
        :param woo_common_log_id: It contain the common log book id and its type is Object
        :return: It will return True if the process successfully completed.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id("woo.product.attribute.ept")
        obj_woo_attribute = self.env['woo.product.attribute.ept']
        odoo_attribute_obj = self.env['product.attribute']
        wcapi = instance.woo_connect()
        response = wcapi.get("products/attributes", params={'per_page':100})
        try:
            attributes_data = response.json()
        except Exception as e:
            message = "Json Error : While import product attributes from WooCommerce for " \
                      "instance %s. \n%s " % (instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id, woo_common_log_id,
                                                            False)
            return False
        if not isinstance(attributes_data, list):
            message = "Response is not in proper format :: %s" % (attributes_data)
            common_log_line_obj.woo_product_export_log_line(message, model_id, woo_common_log_id,
                                                            False)
            return True
        total_pages = response and response.headers.get('x-wp-totalpages') or 1
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                attributes_data = attributes_data + self.woo_import_all_attributes(wcapi, instance,
                                                                                   woo_common_log_id,
                                                                                   model_id, page)
        if response.status_code in [201, 200]:
            for attribute in attributes_data:
                woo_attribute = obj_woo_attribute.search(
                        [('woo_attribute_id', '=', attribute.get('id')),
                         ('woo_instance_id', '=', instance.id), ('exported_in_woo', '=', True)],
                        limit=1)
                if woo_attribute:
                    continue
                odoo_attribute = odoo_attribute_obj.search(
                        [('name', '=ilike', attribute.get('name'))], limit=1)
                if not odoo_attribute:
                    odoo_attribute = odoo_attribute.create({'name':attribute.get('name')})
                woo_attribute = obj_woo_attribute.search([('attribute_id', '=', odoo_attribute.id),
                                                          ('woo_instance_id', '=', instance.id),
                                                          ('exported_in_woo', '=', False)], limit=1)
                if woo_attribute:
                    woo_attribute.write({
                        'woo_attribute_id':attribute.get('id'),
                        'order_by':attribute.get('order_by'),
                        'slug':attribute.get('slug'), 'exported_in_woo':True,
                        'has_archives':attribute.get('has_archives')
                    })
                else:
                    obj_woo_attribute.create(
                            {
                                'name':attribute.get('name'),
                                'woo_attribute_id':attribute.get('id'),
                                'order_by':attribute.get('order_by'),
                                'slug':attribute.get('slug'), 'woo_instance_id':instance.id,
                                'attribute_id':odoo_attribute.id,
                                'exported_in_woo':True, 'has_archives':attribute.get('has_archives')
                            })
        else:
            common_log_line_obj.create(
                    {
                        'message':attributes_data.content,
                        'log_book_id':woo_common_log_id and woo_common_log_id.id or False,
                        'model_id':model_id,
                        'res_id':self and self.id or False
                    })
            return True
        self.sync_woo_attribute_term(instance, woo_common_log_id)
        return True

    def import_all_woo_products(self, instance, common_log_id, page):
        """
        :param wcapi: it contain the response of woo commerce product api and its type is object
        :param instance: It contain the browsable object of class woo_instance_ept
        :param comman_log_id: It contain the new log detail and its type is object
        :param model_id: It contain the id of the model
        :param page: It contain the products page number of woo commerce and its type is Integer
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        Migration done by Haresh Mori @ Emipro on date 14 August 2020.
        Task_Id: 165891
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        wcapi = instance.woo_connect()
        res = wcapi.get('products', params={'per_page':100, 'page':page})
        if not isinstance(res, requests.models.Response):
            message = "Get All Products\nResponse is not in proper format :: %s" % (res)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            common_log_id, False)
            return []
        if res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                            common_log_id, False)
            return []
        try:
            response = res.json()
        except Exception as e:
            message = "Json Error : While Import Product from WooCommerce for instance %s.\n%s" % (
                instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            common_log_id, False)
            return []
        return response

    def get_products_from_woo_v1_v2_v3(self, instance, common_log_id, template_id=False,
                                       import_all=False):
        """
        This method used to call submethods related to woo produts import from Woocommerce to Odoo.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        Migration done by Haresh Mori @ Emipro on date 13 August 2020.
        Task_Id: 165892
        """
        bus_bus_obj = self.env['bus.bus']
        process_import_export_obj = self.env["woo.process.import.export"]
        woo_process_import_export_obj = process_import_export_obj.browse(
                self._context.get('import_export_record'))
        results, total_pages = self.get_templates_from_woo(instance, common_log_id,
                                                           template_id=template_id)
        product_queues = []
        if results:
            if int(total_pages) >= 2:
                # Below method used to process first request product data and then base on total
                # page we call same method to process the response.
                total_result = self.process_product_response(results, instance, common_log_id,
                                                             template_id=False,
                                                             import_all=import_all)
                if total_result:
                    queues = woo_process_import_export_obj.woo_import_products(total_result)
                    product_queues += queues.mapped('id')
                    message = "Product Queue created ", queues.mapped('name')
                    bus_bus_obj.sendone((self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                                        {'type':'simple_notification',
                                         'title':'Woocomerce Connector', 'message':message,
                                         'sticky':False, 'warning':True})
                    self._cr.commit()
                for page in range(2, int(total_pages) + 1):
                    results = self.import_all_woo_products(instance, common_log_id, page)
                    if results:
                        total_result = self.process_product_response(results, instance,
                                                                     common_log_id,
                                                                     template_id=False,
                                                                     import_all=import_all)
                        if total_result:
                            queues = woo_process_import_export_obj.woo_import_products(total_result)
                            product_queues += queues.mapped('id')
                            message = "Product Queue created ", queues.mapped('name')
                            bus_bus_obj.sendone(
                                    (self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                                    {'type':'simple_notification', 'title':'Woocomerce Connector',
                                     'message':message, 'sticky':False, 'warning':True})
                            self._cr.commit()
            else:
                total_result = self.process_product_response(results, instance, common_log_id,
                                                             template_id=False,
                                                             import_all=import_all)
                if total_result and not template_id:
                    queues = woo_process_import_export_obj.woo_import_products(total_result)
                    product_queues += queues.mapped('id')
                    message = "Product Queue created ", queues.mapped('name')
                    bus_bus_obj.sendone(
                            (self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                            {'type':'simple_notification', 'title':'Woocomerce Connector',
                             'message':message, 'sticky':False, 'warning':True})
                    self._cr.commit()
                else:
                    return total_result
        return product_queues

    def get_templates_from_woo(self, instance, common_log_id, template_id):
        """This method used to get product templates from Woocommerce to Odoo.
            @param : self,instance,common_log_id, template_id
            @return: results, total_pages
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 17 August 2020.
            Task_id:165892
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        wcapi = instance.woo_connect()
        results = []
        if template_id:
            res = wcapi.get('products/%s' % (template_id))
        else:
            res = wcapi.get('products', params={'per_page':100})
        if not isinstance(res, requests.models.Response):
            message = "Get Products\nResponse is not in proper format :: %s" % (res)
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, False)
            return [], 0
        if res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(res.content, model_id, common_log_id,
                                                            False)
            return [], 0
        total_pages = res.headers.get('x-wp-totalpages', 0)
        try:
            res = res.json()
        except Exception as e:
            message = "Json Error : While Import Product from WooCommerce for instance %s.\n%s" % (
                instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, False)
            return [], 0
        if template_id:
            results = [res]
        else:
            results = res
        return results, total_pages

    def process_product_response(self, results, instance, common_log_id, template_id=False,
                                 import_all=False):
        """This method used to get variations from Woocommerce store for uniqe template.
            @param : self,result,wcapi,instance
            @return: variants
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13 August 2020.
            Task_id:165892
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        product_data_queue_obj = self.env['woo.product.data.queue.ept']
        wcapi = instance.woo_connect()
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        total_results = []
        if instance.woo_version == 'wc/v2' or instance.woo_version == 'wc/v3':
            available_queue = False
            product_data_queue_line_ids = False
            if not template_id and not import_all:
                product_data_queues = product_data_queue_obj.search(
                        [('woo_instance_id', '=', instance.id)])
                if product_data_queues:
                    available_queue = True
                    product_data_queue_line_ids = product_data_queues.queue_line_ids
            already_exist_result = False
            for result in results:
                flag = False
                variants = []
                woo_id = result.get('id')
                date_modified = result.get('date_modified', False)
                # Added the code to skip the product which is already create or available in queue
                if available_queue:
                    already_exist_results = product_data_queue_line_ids.filtered(
                            lambda x:int(x.woo_synced_data_id) == woo_id)
                    already_exist_results.sorted(lambda x:x.id, True)

                    for already_exist_result in already_exist_results:
                        if already_exist_result.state in ["draft", "done"]:
                            if already_exist_result.woo_update_product_date == date_modified:
                                flag = True
                                break
                            if already_exist_result.state == "draft":
                                break
                        already_exist_result = False
                        break
                if flag:
                    continue
                if result.get('variations'):
                    variants = self.get_variations_from_woo(result, wcapi, instance)
                    if isinstance(variants, str):
                        common_log_line_obj.woo_product_export_log_line(variants, model_id,
                                                                        common_log_id, False)
                        continue
                result.update({'variations':variants})
                if already_exist_result:
                    already_exist_result.write({
                        'woo_synced_data':json.dumps(result),
                        'woo_update_product_date':date_modified
                    })
                else:
                    total_results.append(result)
        return total_results

    def get_variations_from_woo(self, result, wcapi, instance):
        """This method used to get variations from Woocommerce store for uniqe template.
            @param : self,result,wcapi,instance
            @return: variants
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13 August 2020.
            Task_id:165892
        """
        variants = []
        try:
            params = {"per_page":100}
            response = wcapi.get("products/%s/variations" % (result.get("id")),
                                 params=params)
            variants = response.json()

            total_pages = response.headers.get("X-WP-TotalPages")
            if int(total_pages) > 1:
                for page in range(2, int(total_pages) + 1):
                    params["page"] = page
                    response = wcapi.get("products/%s/variations" % (result.get("id")),
                                         params=params)
                    variants += response.json()

        except Exception as e:
            message = "Json Error : While Import Product Variants from WooCommerce " \
                      "for instance %s. \n%s" % (instance.name, e)
            return message
        return variants

    def search_odoo_product_variant(self, woo_instance, product_sku, variant_id):
        """
        :param woo_instance: It is the browsable object of woo commerce instance
        :param product_sku : It is the default code of product and its type is String
        :param variant_id : It is the id of the product variant and its type is Integer
        :return : It will returns the odoo product and woo product if it is exists
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        Modify by Haresh Mori on date 31/12/2019 modification adds active_test =False for searching an archived
        product for a webhook process.
        """
        odoo_product = self.env['product.product']
        woo_product_obj = self.env['woo.product.product.ept']

        woo_product = woo_product_obj.with_context(active_test=False).search(
                [('variant_id', '=', variant_id), ('woo_instance_id', '=', woo_instance.id)],
                limit=1)
        if not woo_product:
            woo_product = woo_product_obj.with_context(active_test=False).search(
                    [('default_code', '=', product_sku), ('woo_instance_id', '=', woo_instance.id)],
                    limit=1)
        if not woo_product:
            woo_product = woo_product_obj.with_context(active_test=False).search([(
                'product_id.default_code', '=', product_sku),
                ('woo_instance_id', '=', woo_instance.id)],
                    limit=1)
        if not woo_product:
            odoo_product = odoo_product.search([('default_code', '=', product_sku)],
                                               limit=1)
        return woo_product, odoo_product

    def woo_create_variant_product(self, product_template_dict, woo_instance):
        """
        :param product_template_dict: It contain the product template info with variants and its
                                    type is Dictionary
        :param woo_instance: It is the browsable object of woo commerce instance
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        ir_config_parameter_obj = self.env["ir.config_parameter"]
        product_attribute_obj = self.env['product.attribute']
        product_attribute_value_obj = self.env['product.attribute.value']
        product_template_obj = self.env['product.template']

        template_title = ''
        if product_template_dict.get('name', ''):
            template_title = product_template_dict.get('name')
        if product_template_dict.get('title', ''):
            template_title = product_template_dict.get('title')
        attrib_line_vals = []

        for attrib in product_template_dict.get('attributes'):
            if not attrib.get('variation'):
                continue
            attrib_name = attrib.get('name')
            attrib_values = attrib.get('options')
            attribute = product_attribute_obj.get_attribute(attrib_name, type='radio',
                                                            create_variant='always',
                                                            auto_create=True)
            attribute = attribute.filtered(lambda x:x.name == attrib_name)[0] if len(
                    attribute) > 1 else attribute
            attr_val_ids = []

            for attrib_vals in attrib_values:
                attrib_value = product_attribute_value_obj.get_attribute_values(attrib_vals,
                                                                                attribute.id,
                                                                                auto_create=True)
                attrib_value = attrib_value.filtered(lambda x:x.name == attrib_vals)[0] if len(
                        attrib_value) > 1 else attrib_value
                attr_val_ids.append(attrib_value.id)

            if attr_val_ids:
                attribute_line_ids_data = [0, False, {
                    'attribute_id':attribute.id,
                    'value_ids':[[6, False, attr_val_ids]]
                }]
                attrib_line_vals.append(attribute_line_ids_data)
        if attrib_line_vals:
            product_template_values = {
                'name':template_title,
                'type':'product',
                'attribute_line_ids':attrib_line_vals,
                "invoice_policy": "order",
            }
            if ir_config_parameter_obj.sudo().get_param(
                    "woo_commerce_ept.set_sales_description"):
                product_template_values.update(
                        {"description_sale":product_template_dict.get("description", "")})
            product_template = product_template_obj.create(product_template_values)

            available_odoo_products = self.woo_set_variant_sku(woo_instance, product_template_dict,
                                                               product_template,
                                                               sync_price_with_product=woo_instance.sync_price_with_product)
            if available_odoo_products:
                return product_template, available_odoo_products
            return False, False

    @api.model
    def find_template_attribute_values(self, template_attributes, variation_attributes,
                                       product_template, woo_instance):
        """
        Finds template's attribute values combination records and prepare domain for searching the odoo product.
        @author: Maulik Barad on Date 06-Dec-2019.
        @param template_attributes: Attributes of Woo template.
        @param variation_attributes: Attributes of Woo product.
        @param product_template: Odoo template.
        @param woo_instance: Instance of Woo.
        """
        template_attribute_value_domain = []
        for variation_attribute in variation_attributes:
            attribute_val = variation_attribute.get('option')
            attribute_name = variation_attribute.get('name')
            for attribute in template_attributes:
                if attribute.get('variation') and attribute.get('name'):
                    if attribute.get('name').replace(" ", "-").lower() == attribute_name:
                        attribute_name = attribute.get('name')
                        break
            product_attribute = self.env["product.attribute"].get_attribute(attribute_name,
                                                                            type="radio",
                                                                            create_variant="always",
                                                                            auto_create=True)
            if product_attribute:
                product_attribute_value = self.env[
                    "product.attribute.value"].get_attribute_values(attribute_val,
                                                                    product_attribute.id,
                                                                    auto_create=True)
                if product_attribute_value:
                    template_attribute_value_id = self.env[
                        'product.template.attribute.value'].search(
                            [('product_attribute_value_id', '=', product_attribute_value.id),
                             ('attribute_id', '=', product_attribute.id),
                             ('product_tmpl_id', '=', product_template.id)], limit=1)
                    if template_attribute_value_id:
                        domain = ('product_template_attribute_value_ids', '=',
                                  template_attribute_value_id.id)
                        template_attribute_value_domain.append(domain)
                    else:
                        return []

        return template_attribute_value_domain

    def woo_set_variant_sku(self, woo_instance, product_template_dict,
                            product_template, sync_price_with_product=False):
        """
        :param woo_instance: It contain the browsable object of the current instance
        :param product_template_dict: It contain the product template info with variants and
                                    type is Dictionary
        :param product_template: It is the browsable object of product template
        :param sync_price_with_product: It contain the value od price if it is sync or not with
                                        product and Its type is Boolean
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        odoo_product_obj = self.env['product.product']
        available_odoo_products = {}
        for variation in product_template_dict.get('variations'):
            odoo_product = False

            sku = variation.get('sku')
            price = variation.get('regular_price') or variation.get('sale_price') or 0.0
            woo_weight = float(variation.get("weight") or "0.0")
            variation_attributes = variation.get('attributes')

            if len(product_template.attribute_line_ids.ids) != len(variation_attributes):
                continue

            template_attribute_value_domain = self.find_template_attribute_values(
                    product_template_dict.get("attributes"), variation_attributes, product_template,
                    woo_instance)

            if template_attribute_value_domain:
                template_attribute_value_domain.append(
                        ('product_tmpl_id', '=', product_template.id))
                odoo_product = odoo_product_obj.search(template_attribute_value_domain)
                if odoo_product:
                    weight = self.convert_weight_by_uom(woo_weight, woo_instance,
                                                        import_process=True)
                    odoo_product.write({'default_code':sku, "weight":weight})
                    available_odoo_products.update({variation["id"]:odoo_product})
                    if sync_price_with_product:
                        pricelist_item = self.env['product.pricelist.item'].search(
                                [('pricelist_id', '=', woo_instance.woo_pricelist_id.id),
                                 ('product_id', '=', odoo_product.id)], limit=1)
                        if not pricelist_item:
                            woo_instance.woo_pricelist_id.write({
                                'item_ids':[(0, 0, {
                                    'applied_on':'0_product_variant',
                                    'product_id':odoo_product.id,
                                    'compute_price':'fixed',
                                    'fixed_price':price
                                })]
                            })
                        else:
                            if product_template.company_id and pricelist_item.currency_id.id != \
                                    product_template.company_id.currency_id.id:
                                instance_currency = pricelist_item.currency_id
                                product_company_currency = product_template.company_id.currency_id
                                #                                 date = self._context.get('date') or
                                #                                 fields.Date.today()
                                #                                 company = product_template.company_id
                                price = instance_currency.compute(float(price),
                                                                  product_company_currency)
                            #                                 price = instance_currency._convert(float(price),
                            #                                 product_company_currency, company, date)
                            pricelist_item.write({'fixed_price':price})
        if not available_odoo_products:
            product_template.unlink()
        return available_odoo_products

    def sync_woo_categ_with_product_v1_v2_v3(self, instance, woo_common_log_id, woo_categories,
                                             sync_images_with_product=True):
        """
        :param instance: It is the browsable object of the woo commerce instance
        :param woo_common_log_id: It contain the log id of the common log book and its type is object
        :param woo_categories: It contain the category details of products and and its type is Dict
        :param sync_images_with_product: It contain the either True or False and its type is Boolean
        :return: It will return the category ids into list format
        """
        obj_woo_product_categ = self.env['woo.product.categ.ept']
        categ_ids = []
        for woo_category in woo_categories:
            woo_product_categ = obj_woo_product_categ.search(
                    [('woo_categ_id', '=', woo_category.get('id')),
                     ('woo_instance_id', '=', instance.id)], limit=1)
            if not woo_product_categ:
                woo_product_categ = obj_woo_product_categ.search(
                        [('slug', '=', woo_category.get('slug')),
                         ('woo_instance_id', '=', instance.id)], limit=1)
            if woo_product_categ:
                woo_product_categ.write(
                        {
                            'woo_categ_id':woo_category.get('id'), 'name':woo_category.get('name'),
                            'display':woo_category.get('display'), 'slug':woo_category.get('slug'),
                            'exported_in_woo':True
                        })
                obj_woo_product_categ.sync_woo_product_category(instance, woo_common_log_id,
                                                                woo_product_categ=woo_product_categ,
                                                                sync_images_with_product=sync_images_with_product)
                categ_ids.append(woo_product_categ.id)
            else:
                woo_product_categ = obj_woo_product_categ.create(
                        {
                            'woo_categ_id':woo_category.get('id'), 'name':woo_category.get('name'),
                            'display':woo_category.get('display'), 'slug':woo_category.get('slug'),
                            'woo_instance_id':instance.id, 'exported_in_woo':True
                        })
                obj_woo_product_categ.sync_woo_product_category(instance, woo_common_log_id,
                                                                woo_product_categ=woo_product_categ,
                                                                sync_images_with_product=sync_images_with_product)
                woo_product_categ and categ_ids.append(woo_product_categ.id)
        return categ_ids

    def sync_woo_tags_with_product_v1_v2_v3(self, woo_instance, woo_tags):
        """
        :param woo_instance: It is the browsable object of the woo commerce instance
        :param woo_tags: It contain the tags details of products and and its type is Dict
        :param woo_log_id: It contain the log id of the common log book and its type is object
        :return: It will return the tags ids into list format
        """
        woo_product_tags_obj = self.env['woo.tags.ept']
        tag_ids = []
        for woo_tag in woo_tags:
            woo_product_tag = woo_product_tags_obj.search(
                    [('woo_tag_id', '=', woo_tag.get('id')),
                     ('woo_instance_id', '=', woo_instance.id)],
                    limit=1)
            if not woo_product_tag:
                woo_product_tag = woo_product_tags_obj.search(
                        [('slug', '=', woo_tag.get('slug')),
                         ('woo_instance_id', '=', woo_instance.id)],
                        limit=1)
            if woo_product_tag:
                woo_product_tag.write({
                    'name':woo_tag.get('name'), 'slug':woo_tag.get('slug'),
                    'exported_in_woo':True
                })
                tag_ids.append(woo_product_tag.id)
            else:
                woo_product_tag = woo_product_tags_obj.create(
                        {
                            'woo_tag_id':woo_tag.get('id'), 'name':woo_tag.get('name'),
                            'slug':woo_tag.get('slug'), 'woo_instance_id':woo_instance.id,
                            'exported_in_woo':True
                        })
                woo_product_tag and tag_ids.append(woo_product_tag.id)
        return tag_ids

    def is_product_importable(self, result, instance, odoo_product, woo_product):
        """
        :param result: It contain the products detail and its type is Dictionary
        :param instance: It is the browsable object of woo commerce instance
        :param odoo_product: It contain the product variant of odoo and its type is object
        :param woo_product: It contain the woo product variant and its type is object
        :return: It will return the message if error is occur
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd.
        """
        woo_skus = []
        odoo_skus = []
        variations = result.get('variations')

        # if instance.woo_version == "new" or instance.woo_version == 'new+':
        if instance.woo_version != 'v3':
            template_title = result.get('name')
        else:
            template_title = result.get('title')

        product_count = len(variations)

        importable = True
        message = ""

        if not odoo_product and not woo_product:
            if product_count != 0:
                attributes = 1
                for attribute in result.get('attributes'):
                    if attribute.get('variation'):
                        attributes *= len(attribute.get('options'))

            product_attributes = {}
            for variantion in variations:
                sku = variantion.get("sku")
                attributes = variantion.get('attributes')
                attributes and product_attributes.update({sku:attributes})
                sku and woo_skus.append(sku)
            if not product_attributes and result.get('type') == 'variable':
                message = "Attributes are not set in any variation of Product: %s and ID: %s." % (
                    template_title, result.get("id"))
                importable = False
                return importable, message
            if woo_skus:
                woo_skus = list(filter(lambda x:len(x) > 0, woo_skus))
            total_woo_sku = len(set(woo_skus))
            if not len(woo_skus) == total_woo_sku:
                duplicate_skus = list(
                        set([woo_sku for woo_sku in woo_skus if woo_skus.count(woo_sku) > 1]))
                message = "Duplicate SKU(%s) found in Product: %s and ID: %s." % (duplicate_skus,
                                                                                  template_title,
                                                                                  result.get("id"))
                importable = False
                return importable, message
        woo_skus = []
        if odoo_product:
            odoo_template = odoo_product.product_tmpl_id
            if not (product_count == 0 and odoo_template.product_variant_count == 1):
                if product_count == odoo_template.product_variant_count:
                    for woo_sku, odoo_sku in zip(result.get('variations'),
                                                 odoo_template.product_variant_ids):
                        woo_skus.append(woo_sku.get('sku'))
                        odoo_sku.default_code and odoo_skus.append(odoo_sku.default_code)

                    woo_skus = list(filter(lambda x:len(x) > 0, woo_skus))
                    odoo_skus = list(filter(lambda x:len(x) > 0, odoo_skus))

                    total_woo_sku = len(set(woo_skus))
                    if not len(woo_skus) == total_woo_sku:
                        duplicate_skus = list(
                                set([woo_sku for woo_sku in woo_skus if
                                     woo_skus.count(woo_sku) > 1]))
                        message = "Duplicate SKU(%s) found in Product: %s and ID: %s." % (
                            duplicate_skus,
                            template_title, result.get("id"))
                        importable = False
                        return importable, message

        if woo_product:
            woo_skus = []
            for woo_sku in result.get('variations'):
                woo_skus.append(woo_sku.get('sku'))

            total_woo_sku = len(set(woo_skus))
            if not len(woo_skus) == total_woo_sku:
                duplicate_skus = list(
                        set([woo_sku for woo_sku in woo_skus if woo_skus.count(woo_sku) > 1]))
                message = "Duplicate SKU(%s) found in Product: %s and ID: %s." % (duplicate_skus,
                                                                                  template_title,
                                                                                  result.get("id"))
                importable = False
                return importable, message

        return importable, message

    def woo_sync_categ_with_product_v3(self, instance, common_log_id, woo_categories,
                                       sync_images_with_product=True):
        woo_product_categ = self.env['woo.product.categ.ept']
        categ_ids = []
        for woo_category in woo_categories:
            ctg = woo_category.lower().replace('\'', '\'\'')
            self._cr.execute(
                    "select id from woo_product_categ_ept where LOWER(name) = '%s' and woo_instance_id = %s limit 1" % (
                        ctg, instance.id))
            woo_product_categ_id = self._cr.dictfetchall()
            woo_categ = False
            if woo_product_categ_id:
                woo_categ = woo_product_categ.browse(woo_product_categ_id[0].get('id'))
                categ_ids.append(woo_categ.id)
                woo_categ = woo_product_categ.sync_woo_product_category(instance, common_log_id,
                                                                        woo_product_categ=woo_categ,
                                                                        sync_images_with_product=sync_images_with_product)
            else:
                woo_categ = woo_product_categ.sync_woo_product_category(instance, common_log_id,
                                                                        woo_product_categ_name=woo_category,
                                                                        sync_images_with_product=sync_images_with_product)
                woo_categ and categ_ids.append(woo_categ.id)
        return categ_ids

    def woo_sync_tags_with_product_v3(self, wcapi, instance, common_log_id, model_id, woo_tags):
        common_log_line_obj = self.env['common.log.lines.ept']
        woo_product_tags = self.env['woo.tags.ept']
        tag_ids = []
        for woo_tag in woo_tags:
            tag = woo_tag.lower().replace('\'', '\'\'')
            self._cr.execute(
                    "select id from woo_tags_ept where LOWER(name) = '%s' and woo_instance_id = %s limit 1" % (
                        tag, instance.id))
            woo_product_tag_id = self._cr.dictfetchall()
            woo_product_tag = False
            if woo_product_tag_id:
                woo_product_tag = woo_product_tags.browse(woo_product_tag_id[0].get('id'))
                tag_ids.append(woo_product_tag.id)
            else:
                tag_res = wcapi.get("products/tags?fields=id,name")
                if not isinstance(tag_res, requests.models.Response):
                    message = "Get Product Tags\nResponse is not in proper format :: %s" % (tag_res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id, False)
                    continue
                if tag_res.status_code not in [200, 201]:
                    common_log_line_obj.woo_product_export_log_line(tag_res.content, model_id,
                                                                    common_log_id, False)
                    continue
                try:
                    tag_response = tag_res.json()
                except Exception as e:
                    message = "Json Error : While Sync Product Tags from WooCommerce for instance" \
                              " %s. \n%s" % (instance.name, e)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id, False)
                    continue
                product_tags = tag_response.get('product_tags')
                if isinstance(product_tags, dict):
                    product_tags = [product_tags]
                for product_tag in product_tags:
                    tag_name = product_tag.get('name')
                    if tag_name == woo_tag:
                        single_tag_res = wcapi.get("products/tags/%s" % (product_tag.get('id')))
                        if not isinstance(single_tag_res, requests.models.Response):
                            message = "Get Product Tags\nResponse is not in proper format :: %s" % (
                                single_tag_res)
                            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                            common_log_id, False)
                            continue
                        try:
                            single_tag_response = single_tag_res.json()
                        except Exception as e:
                            message = "Json Error : While Sync Product Tag with id %s from " \
                                      "WooCommerce for instance %s. \n%s" % (
                                          woo_tag.woo_tag_id, instance.name, e)
                            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                            common_log_id, False)
                            continue
                        single_tag = single_tag_response.get('product_tag')

                        tag_vals = {
                            'name':woo_tag, 'woo_instance_id':instance.id,
                            'description':single_tag.get('description'),
                            'exported_in_woo':True, 'woo_tag_id':single_tag.get('id')
                        }

                        woo_product_tag = woo_product_tags.create(tag_vals)
                        woo_product_tag and tag_ids.append(woo_product_tag.id)
                        break
        return tag_ids

    @api.model
    def prepare_woo_template_vals(self, template_data, odoo_template_id, import_for_order,
                                  woo_instance, common_log_book_id):
        """
        Creates new Woo template.
        @author: Maulik Barad on Date 05-Dec-2019.
        @param template_data: Dictionary of template data.
        @param odoo_template_id:Odoo template id to give relation.
        @param import_for_order: True when importing product while order process. 
        @param woo_instance: Instance of Woo.
        @param common_log_book_id: Id of Common Log Book.
        """
        if import_for_order:
            woo_category_ids = self.sync_woo_categ_with_product_v1_v2_v3(woo_instance,
                                                                         common_log_book_id,
                                                                         template_data[
                                                                             "woo_categ_ids"],
                                                                         woo_instance.sync_images_with_product)
            woo_tag_ids = self.sync_woo_tags_with_product_v1_v2_v3(woo_instance,
                                                                   template_data["woo_tag_ids"])
        else:
            woo_category_ids = []
            woo_tag_ids = []
            for woo_category in template_data["woo_categ_ids"]:
                woo_categ = self.env["woo.product.categ.ept"].search(
                        [("woo_categ_id", "=", woo_category.get("id")),
                         ('woo_instance_id', '=', woo_instance.id)], limit=1).id
                woo_categ and woo_category_ids.append(woo_categ)
            for woo_tag in template_data["woo_tag_ids"]:
                product_tag = self.env["woo.tags.ept"].search(
                        [("woo_tag_id", "=", woo_tag.get("id")),
                         ('woo_instance_id', '=', woo_instance.id)], limit=1).id
                product_tag and woo_tag_ids.append(product_tag)

        template_data.update({
            "product_tmpl_id":odoo_template_id,
            "exported_in_woo":True,
            "woo_categ_ids":[(6, 0, woo_category_ids)],
            "woo_tag_ids":[(6, 0, woo_tag_ids)]
        })
        return template_data

    @api.model
    def update_product_images(self, template_images, variant_image, woo_template, woo_product,
                              woo_instance, template_image_updated, product_dict=False):
        """
        Imports/Updates images of Woo template and variant.
        @author: Maulik Barad on Date 12-Dec-2019.
        @param template_images: Images data of Woo template.
        @param variant_image: Image data of Woo variant.
        @param woo_template_id: Template in Woo layer.
        @param woo_product_id: Variant in Woo layer.
        @param woo_instance: Instance of Woo.
        @param template_image_updated: True when images of template is updated.
        """
        common_product_image_obj = self.env["common.product.image.ept"]
        woo_product_image_obj = woo_product_images = need_to_remove = self.env[
            "woo.product.image.ept"]

        if not template_image_updated:
            existing_common_template_images = {}

            if not woo_instance.woo_is_image_url:
                for odoo_image in woo_template.product_tmpl_id.ept_image_ids:
                    if not odoo_image.image:
                        continue
                    key = hashlib.md5(odoo_image.image).hexdigest()
                    if not key:
                        continue
                    existing_common_template_images.update({key:odoo_image.id})
                for template_image in template_images:
                    image_id = template_image["id"]
                    url = template_image.get('src')
                    woo_product_image = woo_product_image_obj.search(
                            [("woo_template_id", "=", woo_template.id),
                             ("woo_variant_id", "=", False),
                             ("woo_image_id", "=", image_id)])
                    if not woo_product_image:
                        try:
                            response = requests.get(url, stream=True, verify=False, timeout=10)
                            if response.status_code == 200:
                                image = base64.b64encode(response.content)
                                key = hashlib.md5(image).hexdigest()
                                if key in existing_common_template_images.keys():
                                    woo_product_image = woo_product_image_obj.create({
                                        "woo_template_id":woo_template.id,
                                        "woo_image_id":image_id,
                                        "odoo_image_id":existing_common_template_images[key]})
                                else:
                                    if not woo_template.product_tmpl_id.image_1920:
                                        woo_template.product_tmpl_id.image_1920 = image
                                        common_product_image = woo_template.product_tmpl_id.ept_image_ids.filtered(
                                                lambda
                                                    x:x.image == woo_template.product_tmpl_id.image_1920)
                                    else:
                                        common_product_image = common_product_image_obj.create({
                                            "name":woo_template.name,
                                            "template_id":woo_template.product_tmpl_id.id,
                                            "image":image,
                                            "url":url})
                                    woo_product_image = woo_product_image_obj.search([
                                        ("woo_template_id", "=", woo_template.id),
                                        ("odoo_image_id", "=", common_product_image.id)])
                                    if woo_product_image:
                                        woo_product_image.woo_image_id = image_id
                        except Exception:
                            pass
                    woo_product_images += woo_product_image
                all_woo_product_images = woo_product_image_obj.search(
                        [("woo_template_id", "=", woo_template.id),
                         ("woo_variant_id", "=", False)])
                need_to_remove += (all_woo_product_images - woo_product_images)
            _logger.info("Images Updated for Template {0}".format(woo_template.name))
        if variant_image:
            existing_common_variant_images = {}
            if not woo_instance.woo_is_image_url:
                for odoo_image in woo_product.product_id.ept_image_ids:
                    if not odoo_image.image:
                        continue
                    key = hashlib.md5(odoo_image.image).hexdigest()
                    if not key:
                        continue
                    existing_common_variant_images.update({key:odoo_image.id})
                image_id = variant_image["id"]
                url = variant_image.get('src')
                woo_product_image = woo_product_image_obj.search(
                        [("woo_variant_id", "=", woo_product.id),
                         ("woo_image_id", "=", image_id)])
                if not woo_product_image:
                    try:
                        response = requests.get(url, stream=True, verify=False, timeout=10)
                        if response.status_code == 200:
                            image = base64.b64encode(response.content)
                            key = hashlib.md5(image).hexdigest()
                            if key in existing_common_variant_images.keys():
                                woo_product_image = woo_product_image_obj.create({
                                    "woo_template_id":woo_template.id,
                                    "woo_variant_id":woo_product.id,
                                    "woo_image_id":image_id,
                                    "odoo_image_id":existing_common_variant_images[key]})
                            else:
                                if not woo_product.product_id.image_1920 or product_dict.get(
                                        'is_image') == True:
                                    woo_product.product_id.image_1920 = image
                                    common_product_image = woo_product.product_id.ept_image_ids.filtered(
                                            lambda x:x.image == woo_product.product_id.image_1920)
                                else:
                                    common_product_image = common_product_image_obj.create({
                                        "name":woo_template.name,
                                        "template_id":woo_template.product_tmpl_id.id,
                                        "product_id":woo_product.product_id.id,
                                        "image":image,
                                        "url":url})
                                woo_product_image = woo_product_image_obj.search(
                                        [("woo_template_id", "=", woo_template.id),
                                         ("woo_variant_id", "=", woo_product.id),
                                         ("odoo_image_id", "=", common_product_image.id)])
                                if woo_product_image:
                                    woo_product_image.woo_image_id = image_id
                    except Exception:
                        pass
            all_woo_product_images = woo_product_image_obj.search(
                    [("woo_template_id", "=", woo_template.id),
                     ("woo_variant_id", "=", woo_product.id)])
            need_to_remove += (all_woo_product_images - woo_product_image)
        need_to_remove.unlink()
        _logger.info("Images Updated for Variant {0}".format(woo_product.name))
        return True

    @api.model
    def sync_products(self, product_data_queue_lines, woo_instance, common_log_book_id,
                      skip_existing_products=False, order_queue_line=False,
                      is_process_from_queue=True):
        """
        This method used to Creates/Updates products from Woocommerce to Odoo.
        @param : self, product_data_queue_lines, woo_instance, common_log_book_id,skip_existing_products=False, order_queue_line=False
        @return: True
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 21 August 2020.
        Task_id:165892
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        queue_counter = 0
        model_id = common_log_line_obj.get_model_id(self._name)
        if order_queue_line:
            self.env["woo.process.import.export"].sync_woo_attributes(woo_instance)

        for product_data_queue_line in product_data_queue_lines:
            if is_process_from_queue:
                if queue_counter == 10:
                    if not order_queue_line:
                        product_queue_id = product_data_queue_line and \
                                           product_data_queue_line.queue_id or False
                        if product_queue_id:
                            product_queue_id.is_process_queue = True
                    self._cr.commit()
                    queue_counter = 0
            queue_counter += 1
            line_failed = False  # For not making done the queue line, which is already failed.
            template_updated = False
            if is_process_from_queue:
                data, product_queue_id, sync_category_and_tags = self.prepare_product_response(
                        order_queue_line, product_data_queue_line)
            else:
                data = product_data_queue_lines[0]
                product_queue_id = False
                sync_category_and_tags = False
                product_data_queue_line = self.env["woo.product.data.queue.line.ept"]
            woo_product_template_id = data.get("id")
            woo_template = self.with_context(active_test=False).search(
                    [("woo_tmpl_id", "=", woo_product_template_id),
                     ("woo_instance_id", "=", woo_instance.id)], limit=1)
            template_info = self.prepare_template_vals(woo_instance, data)
            template_title = data.get("name")
            _logger.info(
                    "Process started for Product- %s||%s||Queue %s." % (woo_product_template_id,
                                                                        template_title,
                                                                        product_queue_id if order_queue_line else product_data_queue_line.queue_id.name))
            if data["variations"]:
                new_woo_template = self.variation_product_sync(woo_instance, data,
                                                               common_log_book_id,
                                                               product_data_queue_line,
                                                               order_queue_line,
                                                               woo_template, product_queue_id,
                                                               sync_category_and_tags,
                                                               template_info,
                                                               skip_existing_products)
                if new_woo_template:
                    woo_template = new_woo_template
            if data["type"] == "simple" or data["type"] == "bundle":
                new_woo_template = self.simple_product_sync(woo_instance, data, common_log_book_id,
                                                            product_queue_id, template_info,
                                                            product_data_queue_line,
                                                            template_updated,
                                                            skip_existing_products=skip_existing_products,
                                                            order_queue_line=order_queue_line)
                if not new_woo_template:
                    continue
                elif not isinstance(new_woo_template, bool):
                    woo_template = new_woo_template
            if not order_queue_line:
                if woo_template and not line_failed:
                    product_data_queue_line.write({"state":"done",
                                                   "last_process_date":datetime.now()})
                else:
                    message = "Misconfiguration at Woocommerce store for product named - '%s'.\n " \
                              "- It seems this might be a variation product, but variations are " \
                              "not defined at store." % (template_title)
                    common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                    product_data_queue_line if not order_queue_line
                                                                    else order_queue_line,
                                                                    common_log_book_id)
                    _logger.info(
                            "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                                    woo_product_template_id, product_queue_id, message))
                    product_data_queue_line.write(
                            {"state":"failed", "last_process_date":datetime.now()})
                # Below two-line add by Haresh on date 6/1/2020 to manage the which queue is running in the background
                product_data_queue_line.queue_id.is_process_queue = False
            _logger.info(
                    "Process done for Product-{0}||{1}||Queue {2}.".format(woo_product_template_id,
                                                                           template_title,
                                                                           product_queue_id if order_queue_line else
                                                                           product_data_queue_line.queue_id.name))
        return True

    def prepare_product_response(self, order_queue_line, product_data_queue_line):
        """ This method used Prepare a product response from order data queue or product data queue.
            @param : self,order_queue_line,product_data_queue_line
            @return: data,product_queue_id,sync_category_and_tags
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 24 August 2020.
            Task_id:165892
        """
        sync_category_and_tags = False
        if order_queue_line:
            data = product_data_queue_line
            product_queue_id = "from Order"
            sync_category_and_tags = True
        else:
            product_queue_id = product_data_queue_line.queue_id.id
            if product_data_queue_line.queue_id.created_by == "webhook":
                sync_category_and_tags = True
            data = json.loads(product_data_queue_line.woo_synced_data)
        return data, product_queue_id, sync_category_and_tags

    def prepare_template_vals(self, woo_instance, product_response):
        """ This method used Prepare a template vals.
            @param : self,data
            @return: template_info_vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 21 August 2020.
            Task_id:165892
        """
        template_info_vals = {
            "name":product_response.get("name"),
            "woo_tmpl_id":product_response.get("id"),
            "woo_instance_id":woo_instance.id,
            "woo_short_description":product_response.get("short_description", ""),
            "woo_description":product_response.get("description", ""),
            "website_published":True if product_response["status"] == "publish" else False,
            "taxable":True if product_response["tax_status"] == "taxable" else False,
            "woo_categ_ids":product_response.get("categories"),
            "woo_tag_ids":product_response.get("tags"),
            "total_variants_in_woo":len(product_response["variations"]),
            "woo_product_type":product_response["type"],
            "active":True
        }
        if product_response.get("date_created"):
            template_info_vals.update(
                    {"created_at":product_response.get("date_created").replace("T", " ")})
        if product_response.get("date_modified"):
            template_info_vals.update(
                    {"updated_at":product_response.get("date_modified").replace("T", " ")})
        return template_info_vals

    def available_woo_odoo_products(self, woo_instance, woo_template, product_response):
        """ This method used to prepare a dictionary of available odoo and Woocomerce products.
            @param : self,woo_instance,woo_template,product_response
            @return: available_woo_products,available_odoo_products
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 21 August 2020.
            Task_id:165892
        """
        available_woo_products = {}
        available_odoo_products = {}
        odoo_template = woo_template.product_tmpl_id
        for variant in product_response["variations"]:
            woo_product, odoo_product = self.search_odoo_product_variant(woo_instance,
                                                                         variant["sku"],
                                                                         variant["id"])
            if woo_product:
                available_woo_products.update({variant["id"]:woo_product})
                woo_template = woo_product.woo_template_id
            if odoo_product:
                available_odoo_products.update({variant["id"]:odoo_product})
                odoo_template = odoo_product.product_tmpl_id
            woo_product = odoo_product = False
        return available_woo_products, available_odoo_products, odoo_template

    def prepare_woo_variant_vals(self, woo_instance, variant, template_title):
        """ This method used to prepare woo variant vals.
            @param : self,woo_instance,variant,template_title
            @return: available_woo_products,available_odoo_products
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 21 August 2020.
            Task_id:165892
        """
        variant_info = {
            "name":template_title, "default_code":variant.get("sku"),
            "variant_id":variant.get("id"), "woo_instance_id":woo_instance.id,
            "exported_in_woo":True,
            "product_url":variant.get("permalink", ""),
            "woo_is_manage_stock":variant["manage_stock"],
            "active":True
        }
        # As the date_created field will be empty, when product is not published.
        if variant.get("date_created"):
            variant_info.update({"created_at":variant.get("date_created").replace("T", " ")})
        if variant.get("date_modified"):
            variant_info.update({"updated_at":variant.get("date_modified").replace("T", " ")})

        return variant_info

    def template_attribute_process(self, woo_instance, odoo_template, variant, template_title,
                                   common_log_book_id, data, product_data_queue_line,
                                   order_queue_line):
        """ This method use to create new attribute if customer only add the attribute value other wise it will create a mismatch logs.
            @param :self,woo_instance,odoo_template,variant,template_title,common_log_book_id,data,product_data_queue_line,order_queue_line
            @return: odoo_product, True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 21 August 2020.
            Task_id:165892
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id(self._name)
        if odoo_template.attribute_line_ids:
            # If the new variant has other attribute than available in odoo template, then exception
            # activity will be generated.
            # else it will add new value in current attribute, and will relate with the new odoo
            # variant.
            woo_attribute_ids = []
            odoo_attributes = odoo_template.attribute_line_ids.attribute_id.ids
            for attribute in variant.get("attributes"):
                attribute = self.env["product.attribute"].get_attribute(
                        attribute["name"])
                woo_attribute_ids.append(attribute.id)
            woo_attribute_ids.sort()
            odoo_attributes.sort()
            if odoo_attributes != woo_attribute_ids:
                message = "- Product %s has tried adding a new attribute for sku '%s' in Odoo.\n- " \
                          "System will not allow adding new attributes to a product." % (
                              template_title, variant.get("sku"))
                common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                product_data_queue_line if not
                                                                order_queue_line else order_queue_line,
                                                                common_log_book_id)

                if not order_queue_line:
                    product_data_queue_line.state = "failed"
                    line_failed = True
                if woo_instance.is_create_schedule_activity:
                    common_log_book_id.create_woo_schedule_activity()
                return False

            template_attribute_value_domain = self.find_template_attribute_values(
                    data.get("attributes"), variant.get("attributes"),
                    odoo_template, woo_instance)
            if not template_attribute_value_domain:
                for woo_attribute in variant.get("attributes"):
                    attribute_id = self.env["product.attribute"].get_attribute(
                            woo_attribute["name"],
                            type="radio",
                            create_variant="always",
                            auto_create=True)
                    value_id = self.env[
                        "product.attribute.value"].get_attribute_values(
                            woo_attribute["option"],
                            attribute_id.id,
                            auto_create=True)
                    attribute_line = odoo_template.attribute_line_ids.filtered(
                            lambda x:x.attribute_id.id == attribute_id.id)
                    if not value_id.id in attribute_line.value_ids.ids:
                        attribute_line.value_ids = [(4, value_id.id, False)]
                odoo_template._create_variant_ids()
                template_attribute_value_domain = self.find_template_attribute_values(
                        data.get("attributes"), variant.get("attributes"),
                        odoo_template, woo_instance)
            template_attribute_value_domain.append(
                    ("product_tmpl_id", "=", odoo_template.id))
            odoo_product = self.env["product.product"].search(
                    template_attribute_value_domain)
            if not odoo_product.default_code:
                odoo_product.default_code = variant["sku"]
            return odoo_product

        template_vals = {"name":template_title, "type":"product",
                         "default_code":variant["sku"]}
        if self.env["ir.config_parameter"].sudo().get_param(
                "woo_commerce_ept.set_sales_description"):
            template_vals.update({"description_sale":variant.get("description", "")})

        self.env["product.template"].create(template_vals)
        odoo_product = self.env["product.product"].search(
                [("default_code", "=", variant["sku"])])
        return odoo_product

    def variation_product_sync(self, woo_instance, product_response, common_log_book_id,
                               product_data_queue_line, order_queue_line,
                               woo_template, product_queue_id, sync_category_and_tags,
                               template_info, skip_existing_products):
        """ This method use to create variation product.
            @param :self,woo_instance,product_response,common_log_book_id,product_data_queue_line,order_queue_line,
                    woo_template,product_queue_id,sync_category_and_tags,template_info,skip_existing_products
            @return: woo_template
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 24 August 2020.
            Task_id:165892
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id(self._name)
        template_title = product_response.get("name")
        woo_product_template_id = product_response.get("id")
        template_images_updated = False
        template_updated = False
        # woo_instance = woo_instance
        # common_log_book_id = common_log_book_id
        # product_response = product_response
        # product_data_queue_line = product_data_queue_line
        # order_queue_line = order_queue_line
        available_woo_products, available_odoo_products, odoo_template = self.available_woo_odoo_products(
                woo_instance, woo_template, product_response)
        product_dict = {}
        for variant in product_response["variations"]:
            variant_id = variant.get("id")
            product_sku = variant.get("sku")
            variant_price = variant.get("regular_price") or variant.get("sale_price") or 0.0

            woo_product = available_woo_products.get(variant_id)
            odoo_product = False
            if woo_product:
                odoo_product = woo_product.product_id
                # Do not update already imported product.
                if skip_existing_products:
                    continue
            # Checks for if the product is importable or not by checking the attributes.
            is_importable, message = self.is_product_importable(product_response, woo_instance,
                                                                odoo_product, woo_product)
            if not is_importable:
                common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                product_data_queue_line if not order_queue_line
                                                                else order_queue_line,
                                                                common_log_book_id)
                _logger.info(
                        "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                                woo_product_template_id, product_queue_id, message))
                if not order_queue_line:
                    product_data_queue_line.state = "failed"
                    line_failed = True
                break
            if not product_sku:
                message = "No SKU found for a Variant of {0}.".format(template_title)
                common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                product_data_queue_line if not order_queue_line
                                                                else order_queue_line,
                                                                common_log_book_id)
                _logger.info(
                        "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                                woo_product_template_id, product_queue_id, message))
                continue
            variant_info = self.prepare_woo_variant_vals(woo_instance, variant, template_title)
            if not woo_product:
                if not woo_template:
                    if not odoo_template and woo_instance.auto_import_product:
                        odoo_template, available_odoo_products = self.woo_create_variant_product(
                                product_response, woo_instance)
                    if not odoo_template:
                        message = "%s Template Not found for sku %s in Odoo." % (
                            template_title, product_sku)
                        common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                        product_data_queue_line if not
                                                                        order_queue_line else order_queue_line,
                                                                        common_log_book_id)
                        _logger.info(
                                "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                                        woo_product_template_id, product_queue_id, message))
                        if not order_queue_line:
                            product_data_queue_line.state = "failed"
                            line_failed = True
                        break

                    woo_template_vals = self.prepare_woo_template_vals(template_info,
                                                                       odoo_template.id,
                                                                       sync_category_and_tags,
                                                                       woo_instance,
                                                                       common_log_book_id)
                    woo_template = self.create(woo_template_vals)
                elif not template_updated:
                    woo_template_vals = self.prepare_woo_template_vals(template_info,
                                                                       odoo_template.id,
                                                                       sync_category_and_tags,
                                                                       woo_instance,
                                                                       common_log_book_id)
                    woo_template.write(woo_template_vals)
                template_updated = True

                odoo_product = available_odoo_products.get(variant_id)
                if not odoo_product:
                    if not woo_instance.auto_import_product:
                        message = "Product %s Not found for sku %s in Odoo." % (
                            template_title, product_sku)
                        common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                        product_data_queue_line if not
                                                                        order_queue_line else order_queue_line,
                                                                        common_log_book_id)
                        _logger.info(
                                "Product {0} Not found for sku {1} of Queue {2} in Odoo.".format(
                                        template_title, product_sku, product_queue_id))
                        if not order_queue_line:
                            product_data_queue_line.state = "failed"
                            line_failed = True
                        continue
                    new_odoo_product = self.template_attribute_process(woo_instance, odoo_template,
                                                                       variant,
                                                                       template_title,
                                                                       common_log_book_id,
                                                                       product_response,
                                                                       product_data_queue_line,
                                                                       order_queue_line)
                    if not new_odoo_product:
                        break
                    elif not isinstance(new_odoo_product, bool):
                        odoo_product = new_odoo_product

                variant_info.update({"product_id":odoo_product.id,
                                     "woo_template_id":woo_template.id})
                woo_product = self.env["woo.product.product.ept"].create(variant_info)
            else:
                if not template_updated:
                    woo_template_vals = self.prepare_woo_template_vals(template_info,
                                                                       woo_product.product_id.product_tmpl_id.id,
                                                                       sync_category_and_tags,
                                                                       woo_instance,
                                                                       common_log_book_id)
                    woo_template.write(woo_template_vals)
                    template_updated = True
                woo_product.write(variant_info)
            update_price = woo_instance.sync_price_with_product
            update_images = woo_instance.sync_images_with_product
            if update_price:
                woo_instance.woo_pricelist_id.set_product_price_ept(woo_product.product_id.id,
                                                                    variant_price)
            if update_images:
                if not woo_template.product_tmpl_id.image_1920:
                    product_dict.update(
                            {'product_tmpl_id':woo_template.product_tmpl_id, 'is_image':True})
                self.update_product_images(product_response["images"], variant["image"],
                                           woo_template,
                                           woo_product, woo_instance, template_images_updated,
                                           product_dict)
                template_images_updated = True
        return woo_template

    def simple_product_sync(self, woo_instance, product_response, common_log_book_id,
                            product_queue_id, template_info, product_data_queue_line,
                            template_updated,
                            skip_existing_products, order_queue_line):
        """ This method use to create or update a simple products.
            @param :self,woo_instance,product_response,common_log_book_id,template_info,product_queue_id,product_data_queue_line,template_updated,
                    skip_existing_products,order_queue_line
            @return: True, Woo_template
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 22 August 2020.
            Task_id:165892
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id(self._name)
        update_price = woo_instance.sync_price_with_product
        update_images = woo_instance.sync_images_with_product
        template_title = product_response.get("name")
        woo_product_template_id = product_response.get("id")
        product_sku = product_response["sku"]
        variant_price = product_response.get("regular_price") or product_response.get(
                "sale_price") or 0.0
        template_images_updated = False
        sync_category_and_tags = False
        woo_template = False
        odoo_template = False
        if order_queue_line:
            sync_category_and_tags = True
        if not product_sku:
            message = "Value of SKU/Internal Reference is not set for product '{0}'" \
                      ", in the Woocommerce store.".format(template_title)
            common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                            product_data_queue_line if not order_queue_line
                                                            else order_queue_line,
                                                            common_log_book_id)
            _logger.info(
                    "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                            woo_product_template_id, product_queue_id, message))
            if not order_queue_line:
                product_data_queue_line.write(
                        {"state":"failed", "last_process_date":datetime.now()})
                line_failed = True
            return False

        woo_product, odoo_product = self.search_odoo_product_variant(woo_instance,
                                                                     product_sku,
                                                                     woo_product_template_id)

        if woo_product and not odoo_product:
            woo_template = woo_product.woo_template_id
            odoo_product = woo_product.product_id
            # Skip already imported product.
            if skip_existing_products:
                product_data_queue_line.state = "done"
                return False

        if odoo_product:
            odoo_template = odoo_product.product_tmpl_id

        is_importable, message = self.is_product_importable(product_response, woo_instance,
                                                            odoo_product, woo_product)
        if not is_importable:
            common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                            product_data_queue_line if not order_queue_line
                                                            else order_queue_line,
                                                            common_log_book_id)
            _logger.info(
                    "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                            woo_product_template_id, product_queue_id, message))
            if not order_queue_line:
                product_data_queue_line.state = "failed"
                line_failed = True
            return False
        variant_info = self.prepare_simple_product_variant_vals(woo_instance, product_response,
                                                                woo_product_template_id)
        if not woo_product:
            if not woo_template:
                if not odoo_template and woo_instance.auto_import_product:
                    woo_weight = float(product_response.get("weight") or "0.0")
                    weight = self.convert_weight_by_uom(woo_weight, woo_instance,
                                                        import_process=True)
                    template_vals = {
                        "name":template_title,
                        "type":"product",
                        "default_code":product_response["sku"],
                        "weight":weight,
                        "invoice_policy": "order",
                    }
                    if self.env["ir.config_parameter"].sudo().get_param(
                            "woo_commerce_ept.set_sales_description"):
                        template_vals.update(
                                {"description_sale":product_response.get("description", "")})

                    odoo_template = self.env["product.template"].create(template_vals)
                    odoo_product = odoo_template.product_variant_ids
                if not odoo_template:
                    message = "%s Template Not found for sku %s in Odoo." % (
                        template_title, product_sku)
                    common_log_line_obj.woo_create_product_log_line(message, model_id,
                                                                    product_data_queue_line if not
                                                                    order_queue_line else order_queue_line,
                                                                    common_log_book_id)
                    _logger.info(
                            "Process Failed of Product {0}||Queue {1}||Reason is {2}".format(
                                    woo_product_template_id, product_queue_id, message))
                    if not order_queue_line:
                        product_data_queue_line.state = "failed"
                        line_failed = True
                    return False

                woo_template_vals = self.prepare_woo_template_vals(template_info,
                                                                   odoo_template.id,
                                                                   sync_category_and_tags,
                                                                   woo_instance,
                                                                   common_log_book_id)
                woo_template = self.create(woo_template_vals)
                template_updated = True

            variant_info.update(
                    {"product_id":odoo_product.id, "woo_template_id":woo_template.id})
            woo_product = self.env["woo.product.product.ept"].create(variant_info)
        else:
            if not template_updated:
                woo_template_vals = self.prepare_woo_template_vals(template_info,
                                                                   woo_template.product_tmpl_id.id,
                                                                   sync_category_and_tags,
                                                                   woo_instance,
                                                                   common_log_book_id)
                woo_template.write(woo_template_vals)
                template_updated = True
            woo_product.write(variant_info)
        if update_price:
            woo_instance.woo_pricelist_id.set_product_price_ept(woo_product.product_id.id,
                                                                variant_price)
        if update_images:
            self.update_product_images(product_response["images"], {}, woo_template, woo_product,
                                       woo_instance, template_images_updated)
            template_images_updated = True
        if woo_template:
            return woo_template
        return True

    def prepare_simple_product_variant_vals(self, woo_instance, product_response,
                                            woo_product_template_id):
        """ This method is used to prepare a simple product variant vals.
            @param : self,woo_instance,product_response,woo_product_template_id
            @return: variant_info
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 22 August 2020.
            Task_id:165892
        """
        template_title = product_response.get("name")
        variant_info = {
            "name":template_title, "default_code":product_response.get("sku"),
            "variant_id":woo_product_template_id, "woo_instance_id":woo_instance.id,
            "exported_in_woo":True,
            "product_url":product_response.get("permalink", ""),
            "woo_is_manage_stock":product_response["manage_stock"],
            "updated_at":product_response.get("date_modified").replace("T", " "),
            "active":True
        }
        if product_response.get("date_created"):
            variant_info.update(
                    {"created_at":product_response.get("date_created").replace("T", " ")})
        if product_response.get("date_modified"):
            variant_info.update(
                    {"updated_at":product_response.get("date_modified").replace("T", " ")})
        return variant_info

    @api.model
    def update_products_in_woo(self, instance, templates, update_price, publish, update_image,
                                   update_basic_detail, common_log_id):
        """
         This method is used for update the product data in woo commerce
        :param instance: It contain the browsable object of the current instance
        :param templates: It contain the browsable object of the woo product template
        :param update_price: It contain wither True or False and its type is Boolean
        :param publish: It contain wither True or False and its type is Boolean
        :param update_image: It contain wither True or False and its type is Boolean
        :param update_basic_detail: It contain wither True or False and its type is Boolean
        :param common_log_id: It contain the log book id and its type is object
        :return: It will return True if the product update process is successfully completed
        Migration done by Haresh Mori @ Emipro on date 19 September 2020 .
        """

        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        wcapi = instance.woo_connect()

        if not instance.is_export_update_images:
            update_image = False
        batches = []

        if len(templates) > 100:
            batches += self.browse(self.prepare_batches(templates.ids))
        else:
            batches.append(templates)

        for templates in batches:
            batch_update = {'update':[]}
            batch_update_data = []

            for template in templates:
                data = {'id':template.woo_tmpl_id, 'variations':[],
                        "type":template.woo_product_type}
                if not publish:
                    data.update(
                            {'status':'publish' if template.website_published else 'draft'})
                elif publish == 'publish':
                    data.update({'status':'publish'})
                else:
                    data.update({'status':'draft'})

                flag, data = self.prepare_product_update_data(template, update_image, update_basic_detail, data)

                data, flag = self.prepare_product_variant_dict(instance, template, data,
                                                               update_basic_detail,
                                                               update_price, update_image,
                                                               common_log_id, model_id)
                flag and batch_update_data.append(data)
                data = {}
            if batch_update_data:
                _logger.info("==> Start the woo template batch for update")
                batch_update.update({'update':batch_update_data})
                res = wcapi.post('products/batch', batch_update)
                _logger.info("==> End the woo template batch for update")
                if not isinstance(res, requests.models.Response):
                    _logger.info("==> Receive error while updating template batch, Please check log details")
                    message = "Update Product \nResponse is not in proper format :: %s" % (
                        res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    False)
                    continue
                if res.status_code not in [200, 201]:
                    _logger.info("==> Receive error while updating template batch, Please check log details")
                    message = "Update Product \n%s" % (res.content)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    False)
                    continue
                else:
                    if publish == 'publish':
                        templates.write({'website_published':True})
                    elif publish == 'unpublish':
                        templates.write({'website_published':False})
                try:
                    response = res.json()
                except Exception as e:
                    _logger.info("==> Receive error while convert reponse in Json, Please check log details")
                    message = "Json Error : While update products to WooCommerce for instance %s." \
                              " \n%s" % (instance.name, e)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    False)
                    continue
                if response.get('data', {}) and response.get('data', {}).get('status') != 200:
                    _logger.info("==> Receive error, Please check log details")
                    message = "Update Product \n%s" % (response.get('message'))
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    False)
                    continue
                for product in response.get("update"):
                    if product.get("error"):
                        _logger.info("==> Receive error, Please check log details")
                        message = "Update Product \n%s" % (product.get("error").get('message'))
                        common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                        common_log_id,
                                                                        False)
        return True

    def auto_update_stock(self, ctx):
        """
        This method is call when auto import stock cron in enable
        This method is call update_stock() method which is responsible to update stock in WooCommerce.
        :return: Boolean
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 16-11-2019.
        :Task id: 156886
        """
        woo_instance_id = ctx.get('woo_instance_id', False)
        instance = self.woo_instance_id.browse(woo_instance_id)
        if not instance:
            return True
        self.update_stock(instance, instance.last_inventory_update_time)
        return True

    def update_stock(self, instance, export_stock_from_date):
        """
        This method is used for export stock from Odoo to WooCommerce according to stock move.
        @parameter : self, instance, export_stock_from_date
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd on date 16-11-2019.
        :Task id: 156886
        Migration done by Haresh Mori @ Emipro on date 10 September 2020 .
        Task_Id: 165895
        """
        product_obj = self.env['product.product']
        woo_product_product_obj = self.env['woo.product.product.ept']

        if not export_stock_from_date:
            export_stock_from_date = datetime.now() - timedelta(30)
        odoo_products = product_obj.get_products_based_on_movement_date_ept(export_stock_from_date,
                                                                            instance.company_id)
        instance.last_inventory_update_time = datetime.now()
        woo_templates = woo_product_product_obj.search([('product_id', 'in', odoo_products), (
            'woo_is_manage_stock', '=', True)]).woo_template_id.filtered(
                lambda x:x.woo_instance_id == instance and x.exported_in_woo == True)
        if woo_templates:
            self.with_context(updated_products_in_inventory=odoo_products).woo_update_stock(
                    instance, woo_templates)
        else:
            _logger.info(
                    "==There is no product movement found between date time from: '%s'  to '%s' for export stock." % (
                        export_stock_from_date, datetime.now()))
        return True

    @api.model
    def get_gallery_images(self, instance, woo_template, template):
        tmpl_images = []
        position = 0
        gallery_img_keys = {}
        key = False
        gallery_images = woo_template.woo_image_ids.filtered(lambda x:not x.woo_variant_id)
        for br_gallery_image in gallery_images:
            image_id = br_gallery_image.woo_image_id
            # img_url = ''
            # if instance.woo_is_image_url:
            #     if br_gallery_image.response_url:
            #         try:
            #             img = requests.get(br_gallery_image.response_url, stream=True, verify=False,
            #                                timeout=10)
            #             if img.status_code == 200:
            #                 img_url = br_gallery_image.response_url
            #             elif br_gallery_image.url:
            #                 img_url = br_gallery_image.url
            #         except Exception:
            #             img_url = br_gallery_image.url or ''
            #     elif br_gallery_image.url:
            #         img_url = br_gallery_image.url
            # else:
            if br_gallery_image.image and not image_id:
                key = hashlib.md5(br_gallery_image.image).hexdigest()
                if not key:
                    continue
                if key in gallery_img_keys:
                    continue
                else:
                    gallery_img_keys.update({key:br_gallery_image.id})
                res = img_file_upload.upload_image(instance, br_gallery_image.image,
                                                   "%s_%s_%s" % (
                                                       template.name, template.categ_id.name,
                                                       template.id),br_gallery_image.image_mime_type)
                image_id = res and res.get('id', False) or ''
            if image_id:
                # if instance.woo_is_image_url:
                #     tmpl_images.append({'src':img_url, 'position':position})
                # else:
                tmpl_images.append({'id':image_id, 'position':position})
                position += 1
                br_gallery_image.woo_image_id = image_id
        return tmpl_images

    def woo_export_or_update_product_categories(self, wcapi, woo_template, instance, common_log_id,
                                                model_id):
        """
        :param wcapi: It is the object of connection with woo commerce rest api
        :param woo_template: It contain the browsable object of the woo product template
        :param instance: It contain the browsable object of the current instance
        :param old: It contain the api version of woo commerce and Its type is Boolean
        :param common_log_id: It contain the browsable object of the common log book ept
        :param model_id: It contain the id if the model class
        :return: It will return the list of tag ids
        @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
        """
        categ_ids = []
        common_log_line_obj = self.env['common.log.lines.ept']
        for woo_categ in woo_template.woo_categ_ids:
            if not woo_categ.woo_categ_id:
                woo_categ.sync_woo_product_category(instance, common_log_id,
                                                    woo_product_categ=woo_categ)
                woo_categ.woo_categ_id and categ_ids.append(woo_categ.woo_categ_id)
            else:
                categ_res = wcapi.get("products/categories/%s" % (woo_categ.woo_categ_id))
                if not isinstance(categ_res, requests.models.Response):
                    message = "Get Product Category \nResponse is not in proper format :: %s" % \
                              (categ_res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    woo_template.product_tmpl_id)
                    continue
                try:
                    categ_res = categ_res.json()
                except Exception as e:
                    message = "Json Error : While import product category from WooCommerce for " \
                              "instance %s. \n%s" % (instance.name, e)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    woo_template.product_tmpl_id)
                    continue
                if categ_res and categ_res.get('id'):
                    categ_ids.append(woo_categ.woo_categ_id)
                else:
                    if woo_template.exported_in_woo:
                        woo_categ.export_product_categs(instance, [woo_categ], common_log_id,
                                                        model_id)
                    else:
                        woo_categ.sync_woo_product_category(instance, common_log_id,
                                                            woo_product_categ=woo_categ)
                    woo_categ.woo_categ_id and categ_ids.append(woo_categ.woo_categ_id)
        return categ_ids

    def woo_export_or_update_product_tags(self, wcapi, woo_template, instance, common_log_id,
                                          model_id):
        """
        :param wcapi: It is the object of connection with woo commerce rest api
        :param woo_template: It contain the browsable object of the woo product template
        :param instance: It contain the browsable object of the current instance
        :param common_log_id: It contain the browsable object of the common log book ept
        :param model_id: It contain the id if the model class
        :return: It will return the list of tag ids
        @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
        Migration done by Haresh Mori @ Emipro on date 16 September 2020 .
        """
        tag_ids = []
        common_log_line_obj = self.env['common.log.lines.ept']
        for woo_tag in woo_template.woo_tag_ids:
            if not woo_tag.woo_tag_id:
                woo_tag.woo_export_product_tags(instance, woo_tag, common_log_id, model_id)
                woo_tag.woo_tag_id and tag_ids.append(woo_tag.woo_tag_id)
            else:
                tag_res = wcapi.get("products/tags/%s" % (woo_tag.woo_tag_id))
                if not isinstance(tag_res, requests.models.Response):
                    message = "Get Product Tags \nResponse is not in proper format :: %s" % (
                        tag_res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    woo_template.product_tmpl_id)
                    continue
                try:
                    tag_res = tag_res.json()
                except Exception as e:
                    message = "Json Error : While import product tag from WooCommerce for " \
                              "instance %s. \n%s" % (instance.name, e)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    woo_template.product_tmpl_id)
                    continue
                if tag_res and tag_res.get('id'):
                    tag_ids.append(woo_tag.woo_tag_id)
                else:
                    woo_tag.woo_export_product_tags(instance, woo_tag, common_log_id, model_id)
                    woo_tag.woo_tag_id and tag_ids.append(woo_tag.woo_tag_id)
        return tag_ids

    def export_product_attributes_in_woo(self, instance, common_log_id, model_id, attribute):
        """
        This method is called when attribute type is select
        Find the existing product attribute if it is available then return It else create a new
        product attribute in woo commerce and get response and based on this response create
        that attribute and its value in the woo commerce connector of odoo and return arrribute id
        in Dict Format
        :param instance: It contain the browsable object of the current instance
        :param common_log_id: It contain the common log book id and its type is Object
        :param model_id: It contain the id of the model class
        :param attribute: It contain the product attribute
        :return: It will return the attribute id into Dict Format.
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        wcapi = instance.woo_connect()
        obj_woo_attribute = self.env['woo.product.attribute.ept']
        woo_attribute = obj_woo_attribute.search(
                [('attribute_id', '=', attribute.id), ('woo_instance_id', '=', instance.id),
                 ('exported_in_woo', '=', True)], limit=1)
        if woo_attribute and woo_attribute.woo_attribute_id:
            return {attribute.id:woo_attribute.woo_attribute_id}
        attribute_data = {
            'name':attribute.name,
            'type':'select',
        }
        attribute_res = wcapi.post("products/attributes", attribute_data)
        if not isinstance(attribute_res, requests.models.Response):
            message = "Export Product Attributes \nResponse is not in proper format :: %s" % attribute_res
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, False)
            return False
        if attribute_res.status_code == 400:
            self.sync_woo_attribute(instance, common_log_id)
            woo_attribute = obj_woo_attribute.search(
                    [('attribute_id', '=', attribute.id), ('woo_instance_id', '=', instance.id),
                     ('exported_in_woo', '=', True)], limit=1)
            if woo_attribute and woo_attribute.woo_attribute_id:
                return {attribute.id:woo_attribute.woo_attribute_id}
        if attribute_res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(attribute_res.content, model_id,
                                                            common_log_id, False)
            return False
        attribute_response = attribute_res.json()
        woo_attribute_id = attribute_response.get('id')
        woo_attribute_name = attribute_response.get('name')
        woo_attribute_slug = attribute_response.get('slug')
        woo_attribute_order_by = attribute_response.get('order_by')
        has_archives = attribute_response.get('has_archives')
        obj_woo_attribute.create({
            'name':attribute and attribute.name or woo_attribute_name,
            'woo_attribute_id':woo_attribute_id,
            'order_by':woo_attribute_order_by,
            'slug':woo_attribute_slug, 'woo_instance_id':instance.id,
            'attribute_id':attribute.id,
            'exported_in_woo':True, 'has_archives':has_archives
        })
        return {attribute.id:woo_attribute_id}

    @api.model
    def get_product_attribute(self, template, instance, common_log_id, model_id):
        """
        :param template: It contain the browsable object of the product template
        :param instance: It contain the browsable object of the current instance
        :param common_log_id: It contain the common log book browsable object
        :param model_id: It contain the if of the model class and Its type Integer
        :return: It will return the attributes and Its type is List of Dictionary and return True
                or False for is_variable field
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        """
        position = 0
        is_variable = False
        attributes = []
        for attribute_line in template.attribute_line_ids:
            options = []
            for option in attribute_line.value_ids:
                options.append(option.name)
            variation = False
            if attribute_line.attribute_id.create_variant in ['always', 'dynamic']:
                variation = True
            attribute_data = {
                'name':attribute_line.attribute_id.name,
                'slug':attribute_line.attribute_id.name.lower(),
                'position':position,
                'visible':True,
                'variation':variation,
                'options':options
            }
            if instance.woo_attribute_type == 'select':
                attrib_data = self.export_product_attributes_in_woo(instance, common_log_id,
                                                                    model_id,
                                                                    attribute_line.attribute_id)
                if not attrib_data:
                    break
                attribute_data.update({'id':attrib_data.get(attribute_line.attribute_id.id)})
            elif instance.woo_attribute_type == 'text':
                attribute_data.update({'name':attribute_line.attribute_id.name})
            position += 1
            if attribute_line.attribute_id.create_variant in ['always', 'dynamic']:
                is_variable = True
            attributes.append(attribute_data)
        return attributes, is_variable

    def prepare_product_variant_dict(self, instance, template, data, basic_detail, update_price,
                                     update_image, common_log_id, model_id):
        """
        This method is used for prepare the product variant dict based on parameters.
        Maulik : Updates variant in this method. Creates new variant, if not exported in woo.
                 Also updating the attributes in template for the new variant.
        :param instance: It contain the browsable object of the current instance.
        :param template: It contain the woo product template
        :param data: It contain the basic detail of woo product template and Its type is Dict
        :param basic_detail: It contain Either True or False and its type is Boolean
        :param update_price: It contain Either True or False and its type is Boolean
        :param update_image: It contain Either True or False and its type is Boolean
        :param common_log_id: It contain the log book id and its type is object
        :param model_id: It contain the id of the model class
        :return: It will return the updated data dictionary
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        Migration done by Haresh Mori @ Emipro on date 21 September 2020 .
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        wcapi = instance.woo_connect()
        variants_to_create = []
        flag = True
        for variant in template.woo_product_ids:
            # var_url = ''
            price = 0.0
            if variant.variant_id:
                info = {'id':variant.variant_id}

                if basic_detail:
                    weight = self.convert_weight_by_uom(variant.product_id.weight, instance)
                    info.update({'sku':variant.default_code, 'weight':str(weight),
                                 "manage_stock":variant.woo_is_manage_stock})
            else:
                attributes = \
                    self.get_product_attribute(template.product_tmpl_id, instance, common_log_id,
                                               model_id)[0]
                info = self.get_variant_data(variant, instance, False)

            if update_image:
                info.update(self.get_variant_image(instance, variant))

            if update_price:
                price = instance.woo_pricelist_id.get_product_price(variant.product_id, 1.0,
                                                                    partner=False,
                                                                    uom_id=variant.product_id.uom_id.id)
                info.update({'regular_price':str(price), 'sale_price':str(price)})

            if template.woo_tmpl_id != variant.variant_id:
                if variant.variant_id:
                    data.get('variations').append(info)
                else:
                    variants_to_create.append(info)
                flag = True
            elif template.woo_tmpl_id == variant.variant_id:
                del data['variations']
                if basic_detail:
                    data.update({'sku':variant.default_code,
                                 "manage_stock":variant.woo_is_manage_stock})
                if update_price:
                    data.update({'regular_price':str(price), 'sale_price':str(price)})
                flag = True

        if data.get('variations'):
            variant_batches = self.prepare_batches(data.get('variations'))
            for woo_variants in variant_batches:
                _logger.info('variations batch processing')
                res = wcapi.post('products/%s/variations/batch' % (data.get('id')),
                                 {'update':woo_variants})
                _logger.info('variations batch process completed [status: %s]', res.status_code)
                if res.status_code in [200, 201]:
                    del data['variations']
                if res.status_code not in [200, 201]:
                    message = "Update Product Variations\n%s" % (res.content)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    False)
        if variants_to_create:
            """Needed to update the attributes of template for adding new variant, while update
            process."""
            _logger.info("Updating attributes of %s in Woo.." % (template.name))
            if data.get("variations"):
                del data['variations']
            data.update({"attributes":attributes})
            res = wcapi.put("products/%s" % (data.get("id")), data)

            _logger.info("Creating variants in Woo..")
            res = wcapi.post('products/%s/variations/batch' % (data.get('id')),
                             {'create':variants_to_create})
            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While update products to WooCommerce for instance %s." \
                          " \n%s" % (instance.name, e)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                common_log_id,
                                                                False)
                return data, flag
            for product in response.get("create"):
                if product.get("error"):
                    message = "Update Product \n%s" % (product.get("error").get('message'))
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    common_log_id,
                                                                    False)
                else:
                    variant_id = product.get("id")
                    sku = product.get("sku")
                    variant = template.woo_product_ids.filtered(lambda x:x.default_code == sku)
                    if variant:
                        variant.write({"variant_id":variant_id, "exported_in_woo":True})

            self.sync_woo_attribute_term(instance, common_log_id)

        return data, flag

    def prepare_product_update_data(self, template, update_image, update_basic_detail, data):
        """
         This method is used for prepare the products details into Dictionary based on parameters
        :param wcapi: It contain the connection object between odoo and woo
        :param template: It contain the woo product template
        :param instance: It contain the browsable object of the current instance
        :param update_image: It contain Either True or False and its type is Boolean
        :param update_basic_detail: It contain Either True or False and its type is Boolean
        :param data: It contain the basic detail of woo product template and Its type is Dict
        :param common_log_id: It contain the common log book id and its type is Object
        :param model_id: It contain the id of the model class
        :return: It will return the updated product dictionary
        @author: Dipak Gogiya @Emipro Technologies Pvt. Ltd
        Migration done by Haresh Mori @ Emipro on date 21 September 2020 .
        """
        instance = template.woo_instance_id
        flag = False
        tmpl_images = []
        if update_image:
            tmpl_images += self.get_gallery_images(instance, template, template.product_tmpl_id)
            data.update({"images":tmpl_images})
            flag = True

        if update_basic_detail:

            weight = self.convert_weight_by_uom(template.product_tmpl_id.weight, instance)

            description = ''
            short_description = ''
            if template.woo_description:
                woo_template_id = template.with_context(lang=instance.woo_lang_id.code)
                description = woo_template_id.woo_description

            if template.woo_short_description:
                woo_template_id = template.with_context(lang=instance.woo_lang_id.code)
                short_description = woo_template_id.woo_short_description
            data.update({
                'name':template.name,
                'enable_html_description':True,
                'enable_html_short_description':True, 'description':description,
                'short_description':short_description,
                'weight':str(weight),
                'taxable':template.taxable and 'true' or 'false'
            })
            woo_categ_ids = list(map(int,template.woo_categ_ids.mapped("woo_categ_id")))
            if all(woo_categ_ids):
                categ_ids = [{'id': cat_id} for cat_id in woo_categ_ids]
                data.update({'categories':categ_ids})

            woo_tag_ids = list(map(int,template.woo_tag_ids.mapped("woo_tag_id")))
            if all(woo_tag_ids):
                tag_ids = [{'id': tag_id} for tag_id in woo_tag_ids]
                data.update({'tags':tag_ids})

        return flag, data

    @api.model
    def export_products_in_woo(self, instance, woo_templates, update_price, publish, update_image, basic_detail, common_log_id):
        """
        :param instance: It contain the browesable object of the current instance
        :param woo_templates: It contain the browsable object of the woo product templates
        :param update_price: It contain either True or False and its type is Boolean
        :param publish: It contain either True or False and its type is Boolean
        :param update_image: It contain either True or False and its type is Boolean
        :param basic_detail: It contain either True or False and its type is Boolean
        :param common_log_id: It contain the browsable object of common log book ept model
        :return: It will return the True if the process is successfully complete
         @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
         Migration done by Haresh Mori @ Emipro on date 15 September 2020 .
        """
        start = time.time()
        wcapi = instance.woo_connect()
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id('woo.product.template.ept')
        if not instance.is_export_update_images:
            update_image = False
        for woo_template in woo_templates:
            _logger.info("== Start the export woo product: '%s'" % woo_template.name)
            data = self.prepare_product_data(woo_template, publish, update_price, update_image, basic_detail, common_log_id, model_id)
            variants = data.get('variations') or []
            variants and data.update({'variations':[]})

            response = self.export_woo_template(woo_template, data, common_log_id)
            if not response:
                continue
            response_variations = []
            woo_tmpl_id = response.get('id')

            if woo_tmpl_id and variants:
                response_variations = self.export_woo_variants(variants, woo_tmpl_id, wcapi,
                                                               woo_template, model_id)

            self.woo_update_template_variant_data(response_variations, woo_template, common_log_id, response, woo_tmpl_id, publish)

            attribute_ids = []
            for variant in variants:
                for attribute in variant.get('attributes'):
                    attribute_ids.append(int(attribute.get('id')))
            self.sync_woo_attribute_term(instance, common_log_id,list(set(attribute_ids)))

            _logger.info("== End the export woo product: '%s' process" % woo_template.name)
            self._cr.commit()
        end = time.time()
        _logger.info("Exported total templates  %s  in %s seconds." % (len(woo_templates), str(end - start)))
        return True

    def prepare_product_data(self, woo_template, publish, update_price,
                             update_image, basic_detail, common_log_id, model_id):
        """ This method use to prepare a data for the export product.
            @param : elf, wcapi, instance, woo_template, publish, update_price,
                         update_image, basic_detail, template, common_log_id, model_id
            @return: data
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 15 September 2020 .
            Task_id: 165897
        """
        template = woo_template.product_tmpl_id
        instance = woo_template.woo_instance_id
        data = {}
        if basic_detail:
            description = ''
            short_description = ''
            if woo_template.woo_description:
                woo_template_id = woo_template.with_context(lang=instance.woo_lang_id.code)
                description = woo_template_id.woo_description

            if woo_template.woo_short_description:
                woo_template_id = woo_template.with_context(lang=instance.woo_lang_id.code)
                short_description = woo_template_id.woo_short_description

            weight = self.convert_weight_by_uom(template.weight, instance)

            data = {
                'enable_html_description':True, 'enable_html_short_description':True,
                'type':'simple', 'name':woo_template.name,
                'description':description, 'weight':str(weight),
                'short_description':short_description,
                'taxable':woo_template.taxable and 'true' or 'false',
                'shipping_required':'true'
            }
            woo_categ_ids = list(map(int,woo_template.woo_categ_ids.mapped("woo_categ_id")))
            if all(woo_categ_ids):
                categ_ids = [{'id': cat_id} for cat_id in woo_categ_ids]
                data.update({'categories':categ_ids})

            woo_tag_ids = list(map(int,woo_template.woo_tag_ids.mapped("woo_tag_id")))
            if all(woo_tag_ids):
                tag_ids = [{'id': tag_id} for tag_id in woo_tag_ids]
                data.update({'tags':tag_ids})

            attributes, is_variable = self.get_product_attribute(template, instance, common_log_id,
                                                                 model_id)
            if is_variable:
                data.update({'type':'variable'})

            if template.attribute_line_ids:
                variations = []
                for variant in woo_template.woo_product_ids:
                    variation_data = {}
                    product_variant = self.get_variant_data(variant, instance, update_image)
                    variation_data.update(product_variant)
                    if update_price:
                        if data.get('type') == 'simple':
                            data.update(self.get_product_price(instance, variant))
                        else:
                            variation_data.update(self.get_product_price(instance, variant))
                    variations.append(variation_data)
                default_att = variations and variations[0].get('attributes') or []
                data.update({
                    'attributes':attributes, 'default_attributes':default_att,
                    'variations':variations
                })
                if data.get('type') == 'simple':
                    data.update({'sku':str(variant.default_code),
                                 "manage_stock":variant.woo_is_manage_stock})
            else:
                variant = woo_template.woo_product_ids
                data.update(self.get_variant_data(variant, instance, update_image))
                if update_price:
                    data.update(self.get_product_price(instance, variant))

        if publish == 'publish':
            data.update({'status':'publish'})
        else:
            data.update({'status':'draft'})

        if update_image:
            tmpl_images = []
            tmpl_images += self.get_gallery_images(instance, woo_template, template)
            tmpl_images and data.update({"images":tmpl_images})
        return data

    def convert_weight_by_uom(self, weight, instance, import_process=False):
        """
        This method converts weight from Odoo's weight uom to Woo's uom.
        @author: Maulik Barad on Date 24-Jun-2020.
        @param weight: Weight in float.
        @param instance: Instance of Woo.
        @param import_process: In which process, we are converting the weight import or export.
        """
        woo_weight_uom = instance.weight_uom_id
        product_weight_uom = self.env.ref("uom.product_uom_lb") if self.env[
                                                                       "ir.config_parameter"].sudo().get_param(
                "product.weight_in_lbs") == '1' else self.env.ref("uom.product_uom_kgm")

        if woo_weight_uom != product_weight_uom:
            if import_process:
                weight = woo_weight_uom._compute_quantity(weight, product_weight_uom)
            else:
                weight = product_weight_uom._compute_quantity(weight, woo_weight_uom)
        return weight

    def export_woo_template(self, woo_template, data, common_log_id):
        """ This method use to export woo template in Woo commmerce store.
            @param : self
            @return:
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 16 September 2020 .
            Task_id: 165897
        """
        template = woo_template.product_tmpl_id
        instance = woo_template.woo_instance_id
        wcapi = instance.woo_connect()
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id(self._name)

        new_product = wcapi.post('products', data)
        if not isinstance(new_product, requests.models.Response):
            message = "Export Product\nResponse is not in proper format :: %s" % (new_product)
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, template)
            return False
        if new_product.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(new_product.content, model_id, common_log_id, template)
            return False
        try:
            response = new_product.json()
        except Exception as error:
            message = "Json Error : While export product to WooCommerce for instance %s. \n%s" % (
                instance.name, error)
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, template)
            return False
        if response.get('data', {}) and response.get('data', {}).get('status') not in [200,
                                                                                       201]:
            message = response.get('message')
            if response.get('code') == 'woocommerce_rest_product_sku_already_exists':
                message = "%s, ==> %s" % (message, data.get('name'))
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, template)
            return False
        if not isinstance(response, dict):
            message = "Export Product, Response is not in proper format"
            common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, template)
            return False

        return response

    def export_woo_variants(self, variants, woo_tmpl_id, wcapi, woo_template, common_log_id):
        """ This method use to export variations data in the Woocommerce store.
            @param : self, variants, woo_tmpl_id, wcapi
            @return: response_variations
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 16 September 2020 .
            Task_id: 165897
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id(self._name)
        response_variations = []
        vairant_batches = self.prepare_batches(variants)
        for woo_variants in vairant_batches:
            for variant in woo_variants:
                if variant.get('image'):
                    variant.update({'image':variant.get('image')})
            variant_response = wcapi.post("products/%s/variations/batch" % (woo_tmpl_id),
                                          {'create':woo_variants})
            if variant_response.status_code not in [200, 201]:
                common_log_line_obj.woo_product_export_log_line(variant_response.content,
                                                                model_id, common_log_id,
                                                                woo_template.product_tmpl_id)
                continue
            try:
                response_variations += variant_response.json().get('create')
            except Exception as error:
                message = "Json Error : While retrive product response from WooCommerce " \
                          "for instance %s. \n%s" % (woo_template.woo_instance_id.name, error)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                common_log_id,
                                                                woo_template.product_tmpl_id)
                continue

        return response_variations

    def woo_update_template_variant_data(self, response_variations, woo_template, common_log_id, response, woo_tmpl_id, publish):
        """ This method uses to write data in the woo template and its variants which data receive from the Woo-commerce store.
            @param : self
            @return:
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 16 September 2020 .
            Task_id: 165897
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        template = woo_template.product_tmpl_id
        model_id = common_log_line_obj.get_model_id(self._name)
        woo_product_product_ept = self.env['woo.product.product.ept']
        for response_variation in response_variations:
            if response_variation.get('error'):
                common_log_line_obj.woo_product_export_log_line(response_variation.get('error'),
                                                                model_id, common_log_id,
                                                                woo_template.product_tmpl_id)
                continue
            response_variant_data = {}
            variant_sku = response_variation.get('sku')
            variant_id = response_variation.get('id')
            variant_created_at = response_variation.get('date_created').replace('T', ' ')
            variant_updated_at = response_variation.get('date_modified').replace('T', ' ')
            woo_product = woo_product_product_ept.search(
                    [('default_code', '=', variant_sku),
                     ('woo_template_id', '=', woo_template.id),
                     ('woo_instance_id', '=', woo_template.woo_instance_id.id)])
            response_variant_data.update(
                    {
                        'variant_id':variant_id, 'created_at':variant_created_at,
                        'updated_at':variant_updated_at, 'exported_in_woo':True
                    })
            woo_product and woo_product.write(response_variant_data)
        created_at = response.get('date_created').replace('T', ' ')
        updated_at = response.get('date_modified').replace('T', ' ')

        if template.product_variant_count == 1 and not template.attribute_line_ids:
            woo_product = woo_template.woo_product_ids
            woo_product.write({
                'variant_id':woo_tmpl_id,
                'created_at':created_at or False,
                'updated_at':updated_at or False, 'exported_in_woo':True
            })
        total_variants_in_woo = response_variations and len(response_variations) or 1

        tmpl_data = {
            'woo_tmpl_id':woo_tmpl_id, 'created_at':created_at or False,
            'updated_at':updated_at or False, 'exported_in_woo':True,
            'total_variants_in_woo':total_variants_in_woo
        }
        tmpl_data.update(
                {'website_published':True}) if publish == 'publish' else tmpl_data.update(
                {'website_published':False})
        woo_template.write(tmpl_data)

class ProductProductEpt(models.Model):
    _name = "woo.product.product.ept"
    _order = 'product_id'
    _description = "WooCommerce Product"

    product_url = fields.Text("Product URL")
    name = fields.Char("Title")
    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance", required=1)
    default_code = fields.Char("Default Code")
    product_id = fields.Many2one("product.product", "Product", required=1, ondelete="cascade")
    woo_template_id = fields.Many2one("woo.product.template.ept", "Woo Template", required=1,
                                      ondelete="cascade")
    active = fields.Boolean('Active', default=True)
    exported_in_woo = fields.Boolean("Exported In Woo")
    variant_id = fields.Char("Variant Id", size=120)
    fix_stock_type = fields.Selection([('fix', 'Fix'), ('percentage', 'Percentage')],
                                      string='Fix Stock Type')
    fix_stock_value = fields.Float(string='Fix Stock Value', digits="Product UoS")
    created_at = fields.Datetime("Created At")
    updated_at = fields.Datetime("Updated At")
    woo_is_image_url = fields.Boolean("Is Image Url ?", related="woo_instance_id.woo_is_image_url")
    woo_is_manage_stock = fields.Boolean("Is Manage Stock?",
                                         help="Enable stock management at product level in WooCommerce",
                                         default=True)
    woo_image_ids = fields.One2many("woo.product.image.ept", "woo_variant_id")

    def toggle_active(self):
        """
        Archiving related woo product template if there is only one active woo product
        :parameter: self
        :return: res
        @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 09/12/2019.
        :Task id: 158502
        """
        with_one_active = self.filtered(
                lambda product:len(product.woo_template_id.woo_product_ids) == 1)
        for product in with_one_active:
            product.woo_template_id.toggle_active()
        return super(ProductProductEpt, self - with_one_active).toggle_active()
