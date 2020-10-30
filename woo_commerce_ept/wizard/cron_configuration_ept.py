# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta
from datetime import datetime

from odoo import models, fields, api
from odoo.exceptions import Warning

_intervalTypes = {
    'days': lambda interval: relativedelta(days=interval),
    'hours': lambda interval: relativedelta(hours=interval),
    'weeks': lambda interval: relativedelta(days=7 * interval),
    'months': lambda interval: relativedelta(months=interval),
    'minutes': lambda interval: relativedelta(minutes=interval),
}


class WooCronConfigurationEpt(models.TransientModel):
    """
    Common model for managing cron configuration.
    """
    _name = "woo.cron.configuration.ept"
    _description = "Woo Cron Configuration"

    def _get_woo_instance(self):
        """
        This method is used to get instance from context.
        :return: Instance
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd 16-Nov-2019
        :Task id: 156886
        """
        return self.env.context.get('active_id', False)

    woo_instance_id = fields.Many2one('woo.instance.ept', 'Woo Instance',
                                      default=_get_woo_instance, readonly=True)
    # auto stock process fields
    woo_stock_auto_export = fields.Boolean('Woo Stock Auto Update.', default=False,
                                           help="Check if you want to automatically update stock levels from Odoo to WooCommerce.")
    woo_update_stock_interval_number = fields.Integer('Woo Update Stock Interval Number', help="Repeat every x.",
                                                      default=10)
    woo_update_stock_interval_type = fields.Selection([('minutes', 'Minutes'),
                                                       ('hours', 'Hours'), ('days', 'Days'),
                                                       ('weeks', 'Weeks'), ('months', 'Months')],
                                                      'Woo Update Stock Interval Unit')
    woo_update_stock_next_execution = fields.Datetime('Woo Update Stock Next Execution', help='Next execution time')
    woo_update_stock_user_id = fields.Many2one('res.users', string="Woo User", help='Woo Stock Update User',
                                               default=lambda self: self.env.user)

    # Auto Import Order
    woo_auto_import_order = fields.Boolean("Auto Import Order from Woo?",
                                           help="Imports orders at certain interval.")
    woo_import_order_interval_number = fields.Integer(help="Repeat every x.", default=10)
    woo_import_order_interval_type = fields.Selection([('minutes', 'Minutes'),
                                                       ('hours', 'Hours'),
                                                       ('days', 'Days'),
                                                       ('weeks', 'Weeks'),
                                                       ('months', 'Months')])
    woo_import_order_next_execution = fields.Datetime(help="Next execution time of Auto Import Order Cron.")
    woo_import_order_user_id = fields.Many2one('res.users',
                                               help="Responsible User for Auto imported orders.",
                                               default=lambda self: self.env.user)
    # Auto Update Order
    woo_auto_update_order_status = fields.Boolean(string="Auto Update Order Status in Woo?",
                                           help="Automatically update order status to WooCommerce.")
    woo_update_order_status_interval_number = fields.Integer(help="Repeat every x.", default=10)
    woo_update_order_status_interval_type = fields.Selection([('minutes', 'Minutes'),
                                                       ('hours', 'Hours'),
                                                       ('days', 'Days'),
                                                       ('weeks', 'Weeks'),
                                                       ('months', 'Months')])
    woo_update_order_status_next_execution = fields.Datetime(help="Next execution time of Auto Update Order Cron.")
    woo_update_order_status_user_id = fields.Many2one('res.users',
                                               help="Responsible User for Auto updating order status.",
                                               default=lambda self: self.env.user)

    @api.onchange("woo_instance_id")
    def onchange_woo_instance_id(self):
        """
        This method execute on change of instance id
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd 16-Nov-2019
        :Task id: 156886
        """
        instance = self.woo_instance_id
        self.woo_stock_auto_export = instance.woo_stock_auto_export if instance else False
        self.woo_auto_import_order = instance.auto_import_order if instance else False
        self.woo_auto_update_order_status = instance.auto_update_order_status if instance else False

        try:
            inventory_cron = instance and self.env.ref(
                'woo_commerce_ept.ir_cron_update_woo_stock_instance_%d' % (instance.id), raise_if_not_found=False)
            self.woo_update_stock_interval_number = inventory_cron.interval_number or False
            self.woo_update_stock_interval_type = inventory_cron.interval_type or False
            self.woo_update_stock_next_execution = inventory_cron.nextcall or False
            self.woo_update_stock_user_id = inventory_cron.user_id or False
        except:
            inventory_cron = False

        try:
            import_order_cron = self.env.ref(
                'woo_commerce_ept.ir_cron_woo_import_order_instance_%d' % (instance.id), raise_if_not_found=False)
            self.woo_import_order_interval_number = import_order_cron.interval_number
            self.woo_import_order_interval_type = import_order_cron.interval_type
            self.woo_import_order_next_execution = import_order_cron.nextcall
            self.woo_import_order_user_id = import_order_cron.user_id
        except:
            import_order_cron = False

        try:
            update_order_status_cron = self.env.ref(
                'woo_commerce_ept.ir_cron_woo_update_order_status_instance_%d' % (instance.id), raise_if_not_found=False)
            self.woo_update_order_status_interval_number = update_order_status_cron.interval_number
            self.woo_update_order_status_interval_type = update_order_status_cron.interval_type
            self.woo_update_order_status_next_execution = update_order_status_cron.nextcall
            self.woo_update_stock_user_id = update_order_status_cron.user_id
        except:
            update_order_status_cron = False

    def save(self):
        """
        This method is used for save values of auto process fields.
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd 16-Nov-2019
        :Task id: 156886
        """
        ir_action_obj = self.env["ir.actions.actions"]
        instance = self.woo_instance_id
        if instance:
            values = {"woo_stock_auto_export":self.woo_stock_auto_export,
                      "auto_import_order":self.woo_auto_import_order,
                      "auto_update_order_status":self.woo_auto_update_order_status}
            instance.write(values)
            self.setup_woo_update_stock_cron(instance)
            self.setup_woo_import_order_cron(instance)
            self.setup_woo_update_order_status_cron(instance)
            # Below code is used for only onboarding panel purpose.
            if self._context.get('is_calling_from_onboarding_panel', False):
                action = ir_action_obj._for_xml_id(
                    "woo_commerce_ept.woo_onboarding_confirmation_wizard_action")
                action['context'] = {'woo_instance_id': instance.id}
                return action
        return True

    def setup_woo_import_order_cron(self, instance):
        """
        Configure the cron for auto import order.
        @author: Maulik Barad on Date 16-Nov-2019.
        """
        ir_model_obj = self.env['ir.model.data']
        if self.woo_auto_import_order:
            try:
                import_order_cron = self.env.ref('woo_commerce_ept.ir_cron_woo_import_order_instance_%d' % (instance.id), raise_if_not_found=False)
            except:
                import_order_cron = False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.woo_import_order_interval_type](self.woo_import_order_interval_number)
            vals = {
                'active': True,
                'interval_number': self.woo_import_order_interval_number,
                'interval_type': self.woo_import_order_interval_type,
                'nextcall': self.woo_import_order_next_execution or nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                'code': "model.import_woo_orders(%d)" % (instance.id),
                'user_id': self.woo_import_order_user_id.id
            }
            if import_order_cron:
                import_order_cron.write(vals)
            else:
                try:
                    import_order_cron = self.env.ref('woo_commerce_ept.ir_cron_woo_import_order')
                except:
                    import_order_cron = False
                if not import_order_cron:
                    raise Warning(
                        'Core settings of WooCommerce are deleted, please upgrade WooCommerce Connector module to back this settings.')

                name = instance.name + ' : ' + import_order_cron.name
                vals.update({'name': name})
                new_cron = import_order_cron.copy(default=vals)
                ir_model_obj.create({
                    'module': 'woo_commerce_ept',
                    'name': 'ir_cron_woo_import_order_instance_%d' % (instance.id),
                    'model': 'ir.cron',
                    'res_id': new_cron.id,
                    'noupdate': True
                })
        else:
            try:
                import_order_cron = self.env.ref('woo_commerce_ept.ir_cron_woo_import_order_instance_%d' % (instance.id))
                import_order_cron.write({'active': False})
            except:
                import_order_cron = False
        return True

    def setup_woo_update_order_status_cron(self, instance):
        """
        Configure the cron for auto update order status.
        @author: Maulik Barad on Date 16-Nov-2019.
        """
        ir_model_obj = self.env['ir.model.data']
        if self.woo_auto_update_order_status:
            try:
                update_order_status_cron = self.env.ref('woo_commerce_ept.ir_cron_woo_update_order_status_instance_%d' % (instance.id), raise_if_not_found=False)
            except:
                update_order_status_cron = False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.woo_update_order_status_interval_type](self.woo_update_order_status_interval_number)
            vals = {
                'active': True,
                'interval_number': self.woo_update_order_status_interval_number,
                'interval_type': self.woo_update_order_status_interval_type,
                'nextcall': self.woo_update_order_status_next_execution or nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                'code': "model.update_woo_order_status(%d)" % (instance.id),
                'user_id': self.woo_update_order_status_user_id.id
            }
            if update_order_status_cron:
                update_order_status_cron.write(vals)
            else:
                try:
                    update_order_status_cron = self.env.ref('woo_commerce_ept.ir_cron_woo_update_order_status')
                except:
                    update_order_status_cron = False
                if not update_order_status_cron:
                    raise Warning(
                        'Core settings of WooCommerce are deleted, please upgrade WooCommerce Connector module to back this settings.')

                name = instance.name + ' : ' + update_order_status_cron.name
                vals.update({'name': name})
                new_cron = update_order_status_cron.copy(default=vals)
                ir_model_obj.create({
                    'module': 'woo_commerce_ept',
                    'name': 'ir_cron_woo_update_order_status_instance_%d' % (instance.id),
                    'model': 'ir.cron',
                    'res_id': new_cron.id,
                    'noupdate': True
                })
        else:
            try:
                update_order_status_cron = self.env.ref('woo_commerce_ept.ir_cron_woo_update_order_status_instance_%d' % (instance.id))
                update_order_status_cron.write({'active': False})
            except:
                update_order_status_cron = False
        return True

    def setup_woo_update_stock_cron(self, instance):
        """
        This method is used for create or write cron of stock export process.
        :param instance: WooCommerce Instance
        :return: Boolean
        @author: Pragnadeep Pitroda @Emipro Technologies Pvt. Ltd 16-Nov-2019
        :Task id: 156886
        """
        ir_model_obj = self.env['ir.model.data']
        if self.woo_stock_auto_export:
            try:
                inventory_cron = self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock_instance_%d' % (instance.id))
            except:
                inventory_cron = False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.woo_update_stock_interval_type](self.woo_update_stock_interval_number)
            vals = {
                'active': True,
                'interval_number': self.woo_update_stock_interval_number,
                'interval_type': self.woo_update_stock_interval_type,
                'nextcall': self.woo_update_stock_next_execution or nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                'code': "model.auto_update_stock(ctx={'woo_instance_id':%d})" % (instance.id),
                'user_id': self.woo_update_stock_interval_type and self.woo_update_stock_user_id.id
            }
            if inventory_cron:
                inventory_cron.write(vals)
            else:
                try:
                    update_stock_cron = self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock')
                except:
                    update_stock_cron = False
                if not update_stock_cron:
                    raise Warning(
                        'Core settings of WooCommerce are deleted, please upgrade WooCommerce Connector module to back this settings.')

                name = instance.name + ' : ' + update_stock_cron.name
                vals.update({'name': name})
                new_cron = update_stock_cron.copy(default=vals)
                ir_model_obj.create({
                    'module': 'woo_commerce_ept',
                    'name': 'ir_cron_update_woo_stock_instance_%d' % (instance.id),
                    'model': 'ir.cron',
                    'res_id': new_cron.id,
                    'noupdate': True
                })
        else:
            try:
                inventory_cron = self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock_instance_%d' % (instance.id))
            except:
                inventory_cron = False
            if inventory_cron:
                inventory_cron.write({'active': False})
        return True

    @api.model
    def action_woo_open_cron_configuration_wizard(self):
        """
           Usage: Return the action for open the cron configuration wizard
           @Task:  166918 - Odoo v14 : Dashboard analysis
           @author: Dipak Gogiya
           :return: True
        """
        """ Called by onboarding panel above the Instance."""
        instance_obj = self.env['woo.instance.ept']
        ir_action_obj = self.env["ir.actions.actions"]
        action = ir_action_obj._for_xml_id(
            "woo_commerce_ept.action_wizard_woo_cron_configuration_ept")
        instance = instance_obj.search_woo_instance()
        action['context'] = {'is_calling_from_onboarding_panel': True}
        if instance:
            action.get('context').update({'default_woo_instance_id': instance.id,
                                 'is_instance_exists': True})
        return action
