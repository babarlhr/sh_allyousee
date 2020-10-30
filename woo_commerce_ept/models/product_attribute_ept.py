# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class WooProductAttributeEpt(models.Model):
    _name = "woo.product.attribute.ept"
    _description = "Product Attribute"

    name = fields.Char('Name', required=1, translate=True)
    slug = fields.Char(string='Slug',
                       help="An alphanumeric identifier for the resource unique to its type.")
    order_by = fields.Selection(
        [('menu_order', 'Custom Ordering'), ('name', 'Name'), ('name_num', 'Name(numeric)'),
         ('id', 'Term ID')], default="menu_order", string='Default sort order')
    woo_attribute_id = fields.Char("Woo Attribute Id")
    exported_in_woo = fields.Boolean("Exported In Woo", default=False)
    attribute_id = fields.Many2one('product.attribute', 'Attribute', required=1, copy=False)
    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance", required=1)
    attribute_type = fields.Selection([('select', 'Select'), ('text', 'Text')],
                                      string='Attribute Type', default='select')
    has_archives = fields.Boolean(string="Enable Archives?",
                                  help="Enable/Disable attribute archives")