# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import logging, time
from datetime import datetime, timedelta
from odoo import models, fields


_logger = logging.getLogger("Woo")


class WooProductDataQueueLineEpt(models.Model):
    _name = "woo.product.data.queue.line.ept"
    _description = 'Woo Product Data Queue Line'

    woo_instance_id = fields.Many2one('woo.instance.ept', string='Instance')
    state = fields.Selection([('draft', 'Draft'), ('failed', 'Failed'),
                              ("cancelled", "Cancelled"), ('done', 'Done')],
                             default='draft')
    synced_date = fields.Datetime(readonly=True)
    last_process_date = fields.Datetime(readonly=True)
    woo_synced_data = fields.Char(string='WooCommerce Synced Data')
    woo_synced_data_id = fields.Char(string='Data Id')
    queue_id = fields.Many2one('woo.product.data.queue.ept', ondelete="cascade")
    common_log_lines_ids = fields.One2many("common.log.lines.ept", "woo_product_queue_line_id",
                                           help="Log lines created against which line.")
    woo_update_product_date = fields.Char('Product Update Date')
    name = fields.Char(string="Product", help="It contain the name of product")

    def sync_woo_product_data(self):
        """This method used to process synced Woo Commerce data.This method called from cron
            and manually from synced Woo Commerce data.
            @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
            Change by Nilesh Parmar 12/02/2020 for add the functionality to manage crash queue.
            if queue is crashed 3 times than create a schedule activity.
            Migration done by Haresh Mori @ Emipro on date 14 August 2020.
            Task_Id: 165892
        """
        woo_product_template_obj = self.env['woo.product.template.ept']
        common_log_book_obj = self.env['common.log.book.ept']
        product_data_queue_obj = self.env['woo.product.data.queue.ept']
        ir_model_obj = self.env['ir.model']
        start = time.time()
        product_queue_line_ids = False
        product_queue = False
        common_log_book_id = False
        if not self:
            query = """select queue.id
                from woo_product_data_queue_line_ept as queue_line
                inner join woo_product_data_queue_ept as queue on queue_line.queue_id = queue.id
                where queue_line.state='draft' and queue.is_action_require = 'False'
                ORDER BY queue_line.create_date ASC limit 1"""
            self._cr.execute(query)
            queue_id = self._cr.fetchone()
            if not queue_id:
                return
            product_queue = product_data_queue_obj.browse(queue_id)
            product_queue_line_ids = product_queue.queue_line_ids

            product_queue.queue_process_count += 1
            if product_queue.queue_process_count > 3:
                product_queue.is_action_require = True
                note = "<p>Attention %s queue is processed 3 times you need to process it manually.</p>" % (product_queue.name)
                product_queue.message_post(body=note)
                if product_queue.woo_instance_id.is_create_schedule_activity:
                    model = ir_model_obj.search([('model', '=', 'woo.product.data.queue.ept')])
                    common_log_book_obj.create_woo_schedule_activity(product_queue, model, True)
                return
        else:
            product_queue_line_ids = self
            if product_queue_line_ids:
                product_queue = product_queue_line_ids.queue_id

        self._cr.commit()
        if not product_queue_line_ids:
            return True

        woo_instance = product_queue_line_ids.woo_instance_id
        is_skip_products = product_queue.woo_skip_existing_products
        if product_queue.log_book_id:
            common_log_book_id = product_queue.log_book_id
        else:
            common_log_book_id = common_log_book_obj.create(
                {
                    'type': 'import',
                    'module': 'woocommerce_ept',
                    'woo_instance_id': woo_instance.id,
                    'active': True,
                    })
            product_queue.log_book_id = common_log_book_id.id
        # below two line add by Haresh Mori on date 7/1/2020, this is used to update
        # is_process_queue as False.
        self.env.cr.execute("""update woo_product_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        woo_product_template_obj.sync_products(product_queue_line_ids, woo_instance,
                                               common_log_book_id, is_skip_products)
        if common_log_book_id and not common_log_book_id.log_lines:
            common_log_book_id.unlink()
        end = time.time()
        _logger.info("Processed %s Products in %s seconds." % (
            str(len(product_queue_line_ids)), str(end - start)))
        return True

    def create_product_queue_schedule_activity(self, queue_id):
        """
                    this method is used to create a schedule activity for queue.
                    @:parameter : queue_id : it is object of queue
                    Author: Nilesh Parmar
                    Date: 28 january 2020.
                    task id : 160199
                    :return:
                """
        mail_activity_obj = self.env["mail.activity"]
        model_id = self.env["ir.model"].search([("model", "=", "woo.product.data.queue.ept")])
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