# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
import logging
from odoo import models, fields, api

_logger = logging.getLogger("WooCommerce")


class WooProductTemplateEpt(models.Model):
    _inherit = "woo.product.template.ept"

    def get_variant_data(self, variant, instance, update_image):
        """ Inherit the connector-based method to set the sequence of variant and also set the hex code in the meta
            data field.
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 8 January 2021 .
            Task_id: 169550 - Woo Commerce Color picker
        """
        variant_vals = super(WooProductTemplateEpt, self).get_variant_data(variant, instance, update_image)
        product_template_attribute_value = variant.product_id.product_template_attribute_value_ids.filtered(
            lambda attribute: attribute.display_type == 'color') or False
        if product_template_attribute_value and len(
            product_template_attribute_value) == 1 and product_template_attribute_value.product_attribute_value_id.html_color:
            meta_data = []
            meta_data.append({'key': 'markersnpens-color-picker',
                              'value': product_template_attribute_value.product_attribute_value_id.html_color})
            variant_vals.update({'meta_data': meta_data})
        variant_vals.update({'menu_order': variant.sequence})
        return variant_vals

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
        wc_api = instance.woo_connect()
        variants_to_create = []
        flag = True
        for variant in template.woo_product_ids:
            price = 0.0
            if variant.variant_id:
                info = {'id': variant.variant_id, 'menu_order': variant.sequence}
                # Below are used to set the color in the metadata field.
                product_template_attribute_value = variant.product_id.product_template_attribute_value_ids.filtered(
                    lambda attribute: attribute.display_type == 'color') or False
                if product_template_attribute_value and product_template_attribute_value.product_attribute_value_id.html_color:
                    meta_data = []
                    meta_data.append({'key': 'markersnpens-color-picker',
                                      'value': product_template_attribute_value.product_attribute_value_id.html_color})
                    info.update({'meta_data': meta_data})

                if basic_detail:
                    weight = self.convert_weight_by_uom(variant.product_id.weight, instance)
                    info.update({'sku': variant.default_code, 'weight': str(weight),
                                 "manage_stock": variant.woo_is_manage_stock})
            else:
                attributes = self.get_product_attribute(template.product_tmpl_id, instance, common_log_id, model_id)[0]
                info = self.get_variant_data(variant, instance, False)

            if update_image:
                info.update(self.get_variant_image(instance, variant))

            if update_price:
                price = instance.woo_pricelist_id.get_product_price(variant.product_id, 1.0, partner=False,
                                                                    uom_id=variant.product_id.uom_id.id)
                info.update({'regular_price': str(price), 'sale_price': str(price)})

            if template.woo_tmpl_id != variant.variant_id:
                if variant.variant_id:
                    data.get('variations').append(info)
                else:
                    variants_to_create.append(info)
                flag = True
            elif template.woo_tmpl_id == variant.variant_id:
                del data['variations']
                if basic_detail:
                    data.update({'sku': variant.default_code, "manage_stock": variant.woo_is_manage_stock})
                if update_price:
                    data.update({'regular_price': str(price), 'sale_price': str(price)})
                flag = True

        if data.get('variations'):
            variant_batches = self.prepare_batches(data.get('variations'))
            for woo_variants in variant_batches:
                _logger.info('variations batch processing')
                res = wc_api.post('products/%s/variations/batch' % (data.get('id')), {'update': woo_variants})
                _logger.info('variations batch process completed [status: %s]', res.status_code)
                if res.status_code in [200, 201]:
                    del data['variations']
                if res.status_code not in [200, 201]:
                    message = "Update Product Variations\n%s" % res.content
                    common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, False)
        if variants_to_create:
            """Needed to update the attributes of template for adding new variant, while update
            process."""
            _logger.info("Updating attributes of %s in Woo.." % template.name)
            if data.get("variations"):
                del data['variations']
            data.update({"attributes": attributes})
            res = wc_api.put("products/%s" % (data.get("id")), data)

            _logger.info("Creating variants in Woo..")
            res = wc_api.post('products/%s/variations/batch' % (data.get('id')), {'create': variants_to_create})
            try:
                response = res.json()
            except Exception as error:
                message = "Json Error : While update products to WooCommerce for instance %s. \n%s" % (
                    instance.name, error)
                common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, False)
                return data, flag
            for product in response.get("create"):
                if product.get("error"):
                    message = "Update Product \n%s" % (product.get("error").get('message'))
                    common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_id, False)
                else:
                    variant_id = product.get("id")
                    variant = template.woo_product_ids.filtered(lambda x: x.default_code == product.get("sku"))
                    if variant:
                        variant.write({"variant_id": variant_id, "exported_in_woo": True})

            self.sync_woo_attribute_term(instance, common_log_id)

        return data, flag

    def prepare_woo_variant_vals(self, woo_instance, variant, template_title=""):
        """ Inherit the connector-based method to set the sequence of variant while sync products from Woocommerce
            store to Odoo.
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 8 January 2021 .
            Task_id: 169550 - Woo Commerce Color picker
        """
        variant_vals = super(WooProductTemplateEpt, self).prepare_woo_variant_vals(woo_instance, variant,
                                                                                   template_title)
        variant_vals.update({"sequence": variant.get("menu_order")})
        return variant_vals


class ProductProductEpt(models.Model):
    _inherit = "woo.product.product.ept"
    _order = 'sequence, id'
    # Here we have taken a sequence field to manage variant sequence.
    sequence = fields.Integer(help="It is used to identify the variant sequence.", default=1)
