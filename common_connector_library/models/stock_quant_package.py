# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, fields


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    tracking_no = fields.Char("Additional Reference",
                              help="This Field Is Used For The Store Tracking No")
