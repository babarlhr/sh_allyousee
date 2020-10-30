# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models, api
import logging
_logger = logging.getLogger(__name__)


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    origin_country_ept = fields.Many2one('res.country', string='Origin Country',
                                         help="Warehouse country based on sales order warehouse "
                                              "country system will apply fiscal position")

    """
    Inherit this method
    ====================
    Because of select fiscal position based on warehouse (origin country)
    """
    @api.model
    def _get_fpos_by_region(self, country_id=False, state_id=False, zipcode=False, vat_required=False):
        origin_country_id = self._context.get('origin_country_ept', False)
        if not origin_country_id:
            return super(AccountFiscalPosition,self)._get_fpos_by_region(country_id,state_id,zipcode,vat_required)
        return self.search_fiscal_position_based_on_origin_country(origin_country_id, vat_required)

    """
    Search fisal position based on origin country
    Updated by twinkalc on 11 sep 2020 - [changes related to the pass domain 
    of company and is_amazon_fpos]
    """
    @api.model
    def search_fiscal_position_based_on_origin_country(self, origin_country_id, vat_required):
        domain = [('auto_apply', '=', True), ('vat_required', '=', vat_required),('company_id', 'in', [self.env.company.id, False]),\
                '|', ('origin_country_ept', '=', origin_country_id),('origin_country_ept', '=', False)]

        _logger.info(self.env.company.id)
        is_amazon_fpos = self._context.get('is_amazon_fpos', False)
        if is_amazon_fpos:
            domain.append(('is_amazon_fpos', '=', is_amazon_fpos))

        fiscal_position = self.search(domain + [('country_id', '=', origin_country_id)], limit=1)
        if fiscal_position:
            return fiscal_position
        fiscal_position = self.search(domain + [('country_group_id.country_ids', '=', origin_country_id)],
                                      limit=1)
        if fiscal_position:
            return fiscal_position
        fiscal_position = self.search(
            domain + [('country_id', '=', None), ('country_group_id', '=', None)], limit=1)
        if fiscal_position:
            return fiscal_position
