# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
import base64
import logging

from odoo import models, fields, _

_logger = logging.getLogger("WooCommerce")


class PrepareProductForExport(models.TransientModel):
    _inherit = "woo.prepare.product.for.export.ept"

    def export_direct_in_woo(self, product_templates):
        """ This method use to create/update Woo layer products.
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14 September 2020 .
            Task_id: 165896
        """
        woo_template_id = False
        woo_product_obj = self.env["woo.product.product.ept"]
        woo_template_obj = self.env["woo.product.template.ept"]
        woo_category_dict = {}
        variants = product_templates.product_variant_ids
        woo_instance = self.woo_instance_id
        sequence = 1
        for variant in variants:
            if not variant.default_code:
                continue
            woo_template = self.create_update_woo_template(variant, woo_instance, woo_template_id, woo_category_dict)

            # For add template images in layer.
            if isinstance(woo_template, int):
                woo_template = woo_template_obj.browse(woo_template)

            self.create_woo_template_images(woo_template)

            woo_variant = woo_product_obj.search([('woo_instance_id', '=', woo_instance.id),
                                                  ('product_id', '=', variant.id),
                                                  ('woo_template_id', '=', woo_template.id)])
            woo_variant_vals = self.prepare_variant_vals_for_woo_layer(woo_instance, variant, woo_template)
            if len(variant.product_template_attribute_value_ids) == 1:
                woo_variant_vals.update({
                    'sequence': variant.product_template_attribute_value_ids.product_attribute_value_id.sequence + 1})
            else:
                woo_variant_vals.update({'sequence': sequence})
                sequence += 1
            if not woo_variant:
                woo_variant = woo_product_obj.create(woo_variant_vals)
            else:
                woo_variant.write(woo_variant_vals)

            # For adding all odoo images into Woo layer.
            self.create_woo_variant_images(woo_template_id, woo_variant)

        return True

    def create_or_update_woo_variant(self, instance_id, record, woo_template):
        """ This method uses to create/update the Woocmmerce layer variant.
            @return: woo_template
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 14 September 2020 .
            Task_id: 165896
        """
        woo_product_obj = self.env['woo.product.product.ept']
        product_product_obj = self.env['product.product']
        woo_prepare_product_for_export_obj = self.env['woo.prepare.product.for.export.ept']
        woo_variant = woo_product_obj.search(
            [('woo_instance_id', '=', instance_id.id), ('product_id', '=', int(record['PRODUCT_ID'])),
             ('woo_template_id', '=', woo_template.id)])
        odoo_product = product_product_obj.browse(int(record['PRODUCT_ID']))
        woo_variant_vals = ({
            'woo_instance_id': instance_id.id,
            'product_id': int(record['PRODUCT_ID']),
            'woo_template_id': woo_template.id,
            'default_code': record['woo_product_default_code'],
            'name': record['product_name'],
        })
        if len(odoo_product.product_template_attribute_value_ids) == 1:
            woo_variant_vals.update({
                'sequence': odoo_product.product_template_attribute_value_ids.product_attribute_value_id.sequence + 1})
        if not woo_variant:
            woo_variant = woo_product_obj.create(woo_variant_vals)
        else:
            woo_variant.write(woo_variant_vals)

        # For adding all odoo images into Woo layer.
        woo_prepare_product_for_export_obj.create_woo_variant_images(woo_template.id, woo_variant)

        return woo_variant
