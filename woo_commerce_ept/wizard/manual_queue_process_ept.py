# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

from odoo import models, api


class WooManualQueueProcessEpt(models.TransientModel):
    """
    Common model for handling the manual queue processes.
    """
    _name = "woo.manual.queue.process.ept"
    _description = "Woo Manual Queue Process"

    def process_queue_manually(self):
        """
        It calls different methods queue type wise.
        @author: Maulik Barad on Date 08-Nov-2019.
        """
        queue_type = self._context.get("queue_type", "")
        if queue_type == "order":
            self.process_order_queue_manually()
        if queue_type == "customer":
            self.process_customer_queue_manually()
        if queue_type == "product":
            self.process_products_queue_manually()
        if queue_type == 'coupon':
            self.process_coupon_queue_manually()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload'}

    def process_order_queue_manually(self):
        """
        This method used to process the order queue manually.
        @author: Maulik Barad on Date 08-Nov-2019.
        """
        order_data_queue_obj = self.env['woo.order.data.queue.ept']
        order_queue_ids = order_data_queue_obj.browse(
            self._context.get('active_ids'))
        #Below two line add by Haresh Mori on date 7/1/2020, this is used to update
        # is_process_queue as False.
        self.env.cr.execute("""update woo_order_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for order_queue_id in order_queue_ids:
            order_queue_line_batch = order_queue_id.order_data_queue_line_ids.filtered(
                lambda x: x.state in ["draft", "failed"])
            order_queue_line_batch.process_order_queue_line()
        return True

    def process_customer_queue_manually(self):
        """This method is used for import customer manually instead of cron.It'll fetch only those queues which is not 'completed' and
            process only those queue lines which is not 'done'..
            @param : self
            @return: True
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 31 August 2020 .
            Task_id: 165956
        """
        customer_data_queue_obj = self.env['woo.customer.data.queue.ept']
        customer_queues = customer_data_queue_obj.browse(
            self._context.get('active_ids', False)).filtered(lambda x: x.state != "done")
        for customer_queue in customer_queues:
            customer_queue.queue_line_ids.with_context(line_ids=customer_queue.queue_line_ids.filtered(lambda x: x.state != 'done')).woo_customer_data_queue_to_odoo()
        return True

    def process_products_queue_manually(self):
        """
        This method used to process the products queue manually.
        @author: Dipak Gogiya
        """
        product_data_queue_obj = self.env['woo.product.data.queue.ept']
        product_queue_ids = product_data_queue_obj.browse(
            self._context.get('active_ids')).filtered(lambda x: x.state != 'done')
        #below two line add by Haresh Mori on date 7/1/2020, this is used to update
        # is_process_queue as False.
        self.env.cr.execute("""update woo_product_data_queue_ept set is_process_queue = False where is_process_queue = True""")
        self._cr.commit()
        for woo_product_queue_id in product_queue_ids:
            woo_product_queue_line_ids = woo_product_queue_id.queue_line_ids.filtered(
                lambda x: x.state in ['draft', 'failed'])
            if woo_product_queue_line_ids:
                woo_product_queue_line_ids.sync_woo_product_data()
        return True

    def process_coupon_queue_manually(self):
        """
        This method used to process the coupon queue manually.
        @author: Nilesh Parmar on Date 31 Dec 2019.
        """
        coupon_data_queue_obj = self.env['woo.coupon.data.queue.ept']
        coupon_queue_ids = coupon_data_queue_obj.browse(
            self._context.get('active_ids'))

        for coupon_queue_id in coupon_queue_ids:
            coupon_queue_line_batch = coupon_queue_id.coupon_data_queue_line_ids.filtered(
                lambda x: x.state in ["draft", "failed"])
            coupon_queue_line_batch and coupon_queue_line_batch.process_coupon_queue_line()
        return True
