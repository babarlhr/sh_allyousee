# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import json, logging, time
from datetime import datetime, timedelta
from odoo import models, fields

_logger = logging.getLogger("Woo")


class WooCustomerDataQueueLineEpt(models.Model):
    _name = "woo.customer.data.queue.line.ept"
    _description = 'Woo Customer Data Queue Line'
    _rec_name = "woo_synced_data_id"
    woo_instance_id = fields.Many2one('woo.instance.ept', string='Instance',
                                      help="Determines that queue line associated with particular instance")
    state = fields.Selection([('draft', 'Draft'), ('failed', 'Failed'), ("cancelled", "Cancelled"),
                              ('done', 'Done')], default='draft')
    last_process_date = fields.Datetime(readonly=True)
    woo_synced_data = fields.Char(string='WooCommerce Synced Data')
    woo_synced_data_id = fields.Char(string='Woo Customer Id')
    queue_id = fields.Many2one('woo.customer.data.queue.ept')
    common_log_lines_ids = fields.One2many("common.log.lines.ept",
                                           "woo_customer_data_queue_line_id",
                                           help="Log lines created against which line.")
    name = fields.Char(string="Customer", help="Customer Name of Woo Commerce")

    def woo_customer_data_queue_to_odoo(self):
        """ This method used to call child methods of sync customer in odoo from queue line response.
            @param : self
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 29 August 2020 .
            Task_id: 165956
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        partner_obj = self.env['res.partner']
        model_id = common_log_line_obj.get_model_id("res.partner")
        log_lines = []
        self.env.cr.execute("""update woo_customer_data_queue_ept set is_process_queue = False 
        where is_process_queue = True""")
        self._cr.commit()
        start = time.time()
        queue_lines = self.find_customer_queue_lines()
        if not queue_lines:
            return
        commit_count = 0
        parent_partner = False
        for customer_queue_line in queue_lines:
            commit_count += 1
            if commit_count == 10:
                customer_queue_line.queue_id.is_process_queue = True
                self._cr.commit()
                commit_count = 0
            instance = customer_queue_line.woo_instance_id
            customer_val = json.loads(customer_queue_line.woo_synced_data)
            _logger.info("Start processing Woo customer Id %s for instance %s.===" % (customer_val.get('id', False),instance.name))

            if customer_val:
                parent_partner = partner_obj.woo_create_contact_customer(customer_val,instance)
            if parent_partner:
                partner_obj.woo_create_or_update_customer(customer_val.get('billing'),instance,parent_partner,'invoice')
                partner_obj.woo_create_or_update_customer(customer_val.get('shipping'),instance,parent_partner,'delivery')
                customer_queue_line.write({'state': 'done', 'last_process_date': datetime.now()})
            else:
                customer_queue_line.write({'state': 'failed', 'last_process_date': datetime.now()})
                log_line_id = common_log_line_obj.create({
                    'model_id': model_id,
                    'message': "Please check customer name or addresses in WooCommerce.",
                    'woo_customer_data_queue_line_id': customer_queue_line.id
                })
                log_lines.append(log_line_id.id)
            customer_queue_line.queue_id.is_process_queue = False
            _logger.info("End processing Woo customer Id %s for instance %s.===" % (customer_val.get('id', False),instance.name))
        queues = queue_lines.queue_id
        queues and self.set_log_line_with_queue_line(queues)
        end = time.time()
        _logger.info("Processed %s Customers in %s seconds." % (str(len(queue_lines)), str(end - start)))
        return True

    def find_customer_queue_lines(self):
        """ This method used to find the customer queue lines which needs to process.
            @param : self
            @return: queue_lines
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 31 August 2020 .
            Task_id: 165956
        """
        woo_customer_data_queue_obj = self.env["woo.customer.data.queue.ept"]
        common_log_obj = self.env["common.log.book.ept"]
        ir_model_obj = self.env['ir.model']
        queue_lines = self
        customer_queue_ids = []
        if self._context.get('line_ids', False):
            queue_lines = self._context.get('line_ids')
        elif not self:
            query = """select queue.id
                from woo_customer_data_queue_line_ept as queue_line
                inner join woo_customer_data_queue_ept as queue on queue_line.queue_id = queue.id
                where queue_line.state='draft' and queue.is_action_require = 'False'
                ORDER BY queue_line.create_date ASC limit 500"""
            self._cr.execute(query)
            customer_queue_list = self._cr.fetchall()

            for result in customer_queue_list:
                customer_queue_ids.append(result[0])

            if not customer_queue_ids:
                return False
            customer_queues = woo_customer_data_queue_obj.browse(list(set(customer_queue_ids)))
            for customer_queue in customer_queues:
                customer_queue.queue_process_count += 1
                if customer_queue.queue_process_count > 3:
                    customer_queue.is_action_require = True
                    note = "<p>Attention %s queue is processed 3 times you need to process it manually.</p>" % (customer_queue.name)
                    customer_queue.message_post(body=note)
                    if customer_queue.woo_instance_id.is_create_schedule_activity:
                        model = ir_model_obj.search([('model', '=', 'woo.customer.data.queue.ept')])
                        common_log_obj.create_woo_schedule_activity(customer_queue, model, True)
                    continue
                queue_lines += customer_queue.queue_line_ids
                self._cr.commit()

        return queue_lines

    def set_log_line_with_queue_line(self, queues):
        """ This method use set a log line with the customer queue line.
            @param : self, queues
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 31 August 2020 .
            Task_id: 165956
        """
        common_log_obj = self.env["common.log.book.ept"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        log_lines = []
        for queue in queues:
            q_dict = {}
            q_line = queue.queue_line_ids
            log_lines = common_log_line_obj.search([
                ('woo_customer_data_queue_line_id', 'in', q_line.mapped('id')),
                ('log_book_id', '=', False)
            ]) if log_lines else False
            if log_lines:
                if queue.common_log_book_id:
                    queue.common_log_book_id.write({'log_lines': [(6, 0, log_lines.ids)]})
                else:
                    common_log_id = common_log_obj.create({
                        'type': 'import',
                        'module': 'woocommerce_ept',
                        'woo_instance_id': queue.woo_instance_id.id,
                        'active': True,
                        'log_lines': [(6, 0, log_lines.ids)]
                    })
                    q_dict.update({'common_log_book_id': common_log_id.id})
            q_dict and queue.write(q_dict)

    def create_customer_queue_schedule_activity(self, queue_id):
        """
            this method is used to create a schedule activity for queue.
            @:parameter : queue_id : it is object of queue
            Author: Nilesh Parmar
            Date: 13 february 2020.
            :return:
        """
        ir_model_obj = self.env["ir.model"]
        mail_activity_obj = self.env["mail.activity"]
        model_id = ir_model_obj.search([("model", "=", "woo.customer.data.queue.ept")])
        activity_type_id = queue_id.woo_instance_id.activity_type_id.id
        date_deadline = datetime.strftime(datetime.now() + timedelta(
            days=queue_id.woo_instance_id.date_deadline), "%Y-%m-%d")
        if queue_id:
            note = "Attention %s queue is processed 3 times you need to process it manually" % (queue_id.name)
            for user_id in queue_id.woo_instance_id.user_ids:
                mail_activity = mail_activity_obj.search([("res_model_id", "=", model_id.id),
                                                          ("user_id", "=", user_id.id),
                                                          ("res_name", "=", queue_id.name),
                                                          ("activity_type_id", "=", activity_type_id)])
                if not mail_activity:
                    vals = {"activity_type_id": activity_type_id,
                            "note": note,
                            "res_id": queue_id.id,
                            "user_id": user_id.id,
                            "res_model_id": model_id.id,
                            "date_deadline": date_deadline}
                    try:
                        mail_activity_obj.create(vals)
                    except:
                        _logger.info("Unable to create schedule activity, Please give proper "
                                     "access right of this user :%s  " % (user_id.name))
        return True