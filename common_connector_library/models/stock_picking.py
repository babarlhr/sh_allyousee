# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tools import float_round
from odoo.tools.float_utils import float_compare

from odoo import fields, models, _


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def get_set_product(self, product):
        try:
            bom_obj = self.env['mrp.bom']
            bom_point = bom_obj.sudo()._bom_find(product=product)
            from_uom = product.uom_id
            to_uom = bom_point.product_uom_id
            factor = from_uom._compute_quantity(1,
                                                to_uom) / bom_point.product_qty
            bom, lines = bom_point.explode(product, factor,
                                           picking_type=bom_point.picking_type_id)
            return lines
        except:
            return {}



    """Below method added to merge auto invoice workflow with common
    connector
    Added by twinkalc 29 july 2020
    """
    def _action_done(self):
        """
        Added comment by Udit
        create and paid invoice on the basis of auto invoice work flow
        when invoicing policy is 'delivery'.
        """
        result = super(StockPicking, self)._action_done()
        for picking in self:
            if picking.sale_id.invoice_status == 'invoiced':
                continue
            order = picking.sale_id
            work_flow_process_record = order and order.auto_workflow_process_id
            if work_flow_process_record and picking.mapped('move_line_ids').filtered(lambda l: l.product_id.invoice_policy == 'delivery') \
                    and work_flow_process_record.create_invoice \
                    and picking.picking_type_id.code == 'outgoing':
                order.validate_and_paid_invoices_ept(work_flow_process_record)
        return result


    """
    Method Parameter :- picking id,order_line_field_key
    For Ex:- if use shopify shopify_line_id set in sale order line..
            use order_line_field_key = shopify_line_id
    For Ex:- picking_id = 25
    This way call Method :-  self.env['stock.picking'].get_tracking_numbers(25,'shopify_line_id')
    Method return :-
            {'default_code' :[{
                                'order_line_field_key':'',
                                'tracking_no':tracking_no,
                                'qty':qty
                                },
                              {
                                'order_line_field_key':'',
                                'tracking_no':tracking_no,
                                'qty':qty
                                }
                            ],
            'default_code' :[{
                                'order_line_field_key':'',
                                'tracking_no':tracking_no,
                                'qty':qty
                            }],
            }"""
    def get_traking_number_for_phantom_type_product(self, picking, order_line_field=False):
        line_items = {}
        update_move_ids = []
        move_obj = self.env['stock.move']
        picking_obj = self.env['stock.picking'].browse(picking)
        phantom_product_dict = {}
        move_lines = picking_obj.move_lines
        for move in move_lines:
            if move.sale_line_id.product_id.id != move.product_id.id:
                if move.sale_line_id in phantom_product_dict and \
                        move.product_id.id not in phantom_product_dict.get(move.sale_line_id):
                    phantom_product_dict.get(move.sale_line_id).append(move.product_id.id)
                else:
                    phantom_product_dict.update({move.sale_line_id: [move.product_id.id]})
        for sale_line_id, product_ids in phantom_product_dict.items():
            moves = move_obj.search([('picking_id', '=', picking_obj.id), ('state', '=', 'done'),
                                     ('product_id', 'in', product_ids)])
            line_id = sale_line_id.search_read([("id", "=", sale_line_id.id)],
            [order_line_field])[0].get(order_line_field)
            tracking_no = picking_obj.carrier_tracking_ref
            for move in moves:
                if not tracking_no:
                    for move_line in move.move_line_ids:
                        tracking_no = move_line.result_package_id \
                                      and move_line.result_package_id.tracking_no or False

            update_move_ids += moves.ids
            product_qty = sale_line_id.product_qty or 0.0
            default_code = sale_line_id.product_id.default_code
            if default_code in line_items:
                for line in line_items.get(default_code):
                    if tracking_no in line.get('tracking_no'):
                        quantity = line.get('quantity')
                        product_qty = quantity + product_qty
                        line.update({'quantity': product_qty, 'line_id': line_id,
                                     'tracking_no': tracking_no})
                else:
                    line_items.get(default_code).append(
                        {'quantity': product_qty, 'line_id': line_id, 'tracking_no': tracking_no})
            else:
                line_items.update({default_code: []})
                line_items.get(default_code).append(
                    {'quantity': product_qty, 'line_id': line_id, 'tracking_no': tracking_no})

        return line_items, update_move_ids

    def get_tracking_numbers(self, picking, order_line_field=False):
        move_line_obj = self.env['stock.move.line']
        line_items, update_move_ids = \
            self.get_traking_number_for_phantom_type_product(picking, order_line_field)
        stock_moves = self.env['stock.move'].search(
            [('id', 'not in', update_move_ids), ('picking_id', '=', picking)])
        for move in stock_moves:
            line_id = \
            move.sale_line_id.search_read([("id", "=", move.sale_line_id.id)], [order_line_field])[
                0].get(order_line_field)
            move_line = move_line_obj.search(
                [('move_id', '=', move.id), ('product_id', '=', move.product_id.id)])
            for move in move_line:
                if move.result_package_id:
                    tracking_no = False
                    if move.result_package_id.tracking_no:
                        tracking_no = move.result_package_id.tracking_no
                    product_qty = move.qty_done or 0.0
                    product_qty = int(product_qty)
                    default_code = move.product_id.default_code
                    if default_code in line_items:
                        for line in line_items.get(default_code):
                            if tracking_no in line.get('tracking_no'):
                                quantity = line.get('quantity')
                                product_qty = quantity + product_qty
                                line.update({'quantity': product_qty, 'line_id': line_id,
                                             'tracking_no': tracking_no})
                        else:
                            line_items.get(default_code).append(
                                {'quantity': product_qty, 'line_id': line_id,
                                 'tracking_no': tracking_no})
                    else:
                        line_items.update({default_code: []})
                        line_items.get(default_code).append(
                            {'quantity': product_qty, 'line_id': line_id,
                             'tracking_no': tracking_no})
        return line_items

    def send_to_shipper(self):
        """
        usage: If auto_processed_orders_ept = True passed in Context then we can not call send shipment from carrier
        This change is used in case of Import Shipped Orders for all connectors.
        @author: Keyur Kanani
        :return: True
        """
        context = dict(self._context)
        if context.get('auto_processed_orders_ept', False):
            return True
        else:
            return super(StockPicking, self).send_to_shipper()