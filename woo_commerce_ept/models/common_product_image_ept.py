# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

from odoo import models, api
import base64
from odoo.tools.mimetypes import guess_mimetype

class ProductImageEpt(models.Model):
    """
    Inherited for adding images in related Woo products, when images will be added Odoo products.
    @author: Maulik Barad on Date 11-Dec-2019.
    """
    _inherit = "common.product.image.ept"

    @api.model
    def create(self, vals):
        """
        Inherited for adding images in Woo products.
        @author: Maulik Barad on Date 11-Dec-2019.
        """
        result = super(ProductImageEpt, self).create(vals)
        if self.user_has_groups('woo_commerce_ept.group_woo_ept'):
            woo_product_product_obj = self.env["woo.product.product.ept"]
            woo_product_template_obj = self.env["woo.product.template.ept"]
            woo_product_image_obj = self.env["woo.product.image.ept"]
            woo_product_image_vals = {"odoo_image_id":result.id}

            if vals.get("product_id", False):
                woo_variants = woo_product_product_obj.search_read([("product_id", "=", vals.get("product_id"))], ["id", "woo_template_id"])
                mimetype = guess_mimetype(base64.b64decode(result.image))
                for woo_variant in woo_variants:
                    woo_product_image_vals.update({"woo_variant_id":woo_variant["id"], "woo_template_id":woo_variant["woo_template_id"][0],"image_mime_type":mimetype,"sequence":0})
                    woo_product_image_obj.create(woo_product_image_vals)
            elif vals.get("template_id", False):
                woo_templates = woo_product_template_obj.search_read([("product_tmpl_id", "=", vals.get("template_id"))], ["id"])
                mimetype = guess_mimetype(base64.b64decode(result.image))
                for woo_template in woo_templates:
                    woo_product_image_vals.update({"woo_template_id":woo_template["id"], "sequence":result.sequence, "image_mime_type":mimetype})
                    woo_product_image_obj.create(woo_product_image_vals)

        return result

    def write(self, vals):
        """
        Inherited for adding images in Woo products.
        @author: Maulik Barad on Date 11-Dec-2019.
        """
        result = super(ProductImageEpt, self).write(vals)
        if self.user_has_groups('woo_commerce_ept.group_woo_ept'):
            woo_product_images = self.env["woo.product.image.ept"]
            woo_product_product_obj = self.env["woo.product.product.ept"]
            for record in self:
                woo_product_images += woo_product_images.search([("odoo_image_id", "=", record.id)])
            if woo_product_images:
                if not vals.get("product_id", ""):
                    woo_product_images.write({"woo_variant_id":False})
                elif vals.get("product_id", ""):
                    for woo_product_image in woo_product_images:
                        woo_variant = woo_product_product_obj.search_read([("product_id", "=", vals.get("product_id")), ("woo_template_id", "=", woo_product_image.woo_template_id.id)], ["id"])
                        if woo_variant:
                            woo_product_image.write({"woo_variant_id":woo_variant["id"]})
        return result
