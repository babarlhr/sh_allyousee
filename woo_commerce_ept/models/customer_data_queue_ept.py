# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import json
from odoo import models, fields, api


class WooCustomerDataQueueEpt(models.Model):
    _name = "woo.customer.data.queue.ept"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Woo Customer Data Queue"

    name = fields.Char(string='Name')
    woo_instance_id = fields.Many2one("woo.instance.ept", string="Instances",
                                      help="Determines that queue line associated with particular instance")
    state = fields.Selection([('draft', 'Draft'), ('partial', 'Partial Done'),
                              ("failed", "Failed"), ('done', 'Done')],
                             default='draft', compute="_compute_state", store=True, tracking=True)
    queue_line_ids = fields.One2many('woo.customer.data.queue.line.ept', 'queue_id', readonly=1)
    customers_count = fields.Integer(string='Total Customers', compute='_compute_lines')
    draft_state_count = fields.Integer(string='Draft', compute='_compute_lines')
    done_state_count = fields.Integer(string='Done', compute='_compute_lines')
    failed_state_count = fields.Integer(string='Failed', compute='_compute_lines')
    cancelled_line_count = fields.Integer(compute='_compute_lines')
    common_log_book_id = fields.Many2one("common.log.book.ept",
                                         help="""Related Log book which has all logs for current queue.""")
    common_log_lines_ids = fields.One2many(related="common_log_book_id.log_lines")
    created_by = fields.Selection([("import", "By Import Process"), ("webhook", "By Webhook")],
                                  help="Identify the process that generated a queue.", default="import")
    is_process_queue = fields.Boolean('Is Processing Queue',default = False)
    running_status = fields.Char(default = "Running...")
    queue_process_count = fields.Integer(string="Queue Process Times",
                                         help="it is used know queue how many time processed")
    is_action_require = fields.Boolean(default=False,
                                       help="it is used to find the action require queue")

    @api.depends("queue_line_ids.state")
    def _compute_lines(self):
        """
        Computes customer queue lines by different states.
        @author: Maulik Barad on Date 25-Dec-2019.
        """
        for record in self:
            queue_lines = record.queue_line_ids
            record.customers_count = len(queue_lines)
            record.draft_state_count = len(queue_lines.filtered(lambda x: x.state == "draft"))
            record.done_state_count = len(queue_lines.filtered(lambda x: x.state == "done"))
            record.failed_state_count = len(queue_lines.filtered(lambda x: x.state == "failed"))
            record.cancelled_line_count = len(queue_lines.filtered(lambda x: x.state == "cancelled"))

    @api.depends("queue_line_ids.state")
    def _compute_state(self):
        """
        Computes state of Customer queue from queue lines' state.
        @author: Maulik Barad on Date 25-Dec-2019.
        """
        for record in self:
            if (record.done_state_count + record.cancelled_line_count) == record.customers_count:
                record.state = "done"
            elif record.draft_state_count == record.customers_count:
                record.state = "draft"
            elif record.failed_state_count == record.customers_count:
                record.state = "failed"
            else:
                record.state = "partial"

    @api.model
    def create(self, vals):
        """
        Inherited and create a sequence and new customer queue
        :param vals: It will contain the updated data and its type is Dictionary
        :return: It will return the object of newly created customer queue
        """
        ir_sequence_obj = self.env['ir.sequence']
        record_name = "/"
        sequence_id = self.env.ref("woo_commerce_ept.woo_customer_data_queue_ept_sequence").id
        if sequence_id:
            record_name = ir_sequence_obj.browse(sequence_id).next_by_id()
        vals.update({"name": record_name})
        return super(WooCustomerDataQueueEpt, self).create(vals)

    def action_force_done(self):
        """
        Cancels all draft and failed queue lines.
        @author: Maulik Barad on Date 25-Dec-2019. 
        """
        need_to_cancel_queue_lines = self.queue_line_ids.filtered(lambda x: x.state in ["draft", "failed"])
        need_to_cancel_queue_lines.write({"state":"cancelled"})
        return True

    def create_customer_data_queue(self, instance, customer, created_by="import"):
        """
        :param instance: It will contain the browsable object of the woo instance
        :param customer: customer response from woocommerce
        :return: It will return the newly created queue object
        @author: Dipak Gogiya on Date 31-Dec-2019.
        """
        customer_data_queue_line_obj = self.env['woo.customer.data.queue.line.ept']
        customer_data_queue_obj = self.env['woo.customer.data.queue.ept']
        queue_vals = {'woo_instance_id': instance.id, "created_by":created_by}
        queue = customer_data_queue_obj.create(queue_vals)
        sync_vals = {
            'woo_instance_id': instance.id,
            'queue_id': queue.id,
            'woo_synced_data': json.dumps(customer),
            'woo_synced_data_id': customer.get('id'),
            'name': customer.get('billing').get('first_name') + customer.get('billing').get(
                'last_name') if customer.get('billing') else ''
            }
        customer_data_queue_line_obj.create(sync_vals)
        return queue
