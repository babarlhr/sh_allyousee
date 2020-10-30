# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import requests
from odoo import models, fields, api, _
import logging
_logger = logging.getLogger("===Woo===")


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_woo_customer = fields.Boolean(string="Is Woo Customer?",
                                     help="Used for identified that the customer is imported from WooCommerce store.")

    def woo_import_all_customers(self, wcapi, instance, common_log_id, page):
        """ This method used to request for the customer page.
            @param : self, wcapi, instance, common_log_id, page
            @return: response
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 28 August 2020 .
            Task_id: 165956
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model = "woo.instance.ept"
        model_id = common_log_line_obj.get_model_id(model)
        if instance.woo_version in ['wc/v1', 'wc/v2', 'wc/v3']:
            res = wcapi.get('customers', params={"per_page": 100, 'page': page})
        if not isinstance(res, requests.models.Response):
            message = "Import all customers \nresponse is not in proper format :: %s" % (res)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_id, False)
            return []
        if res.status_code not in [200, 201]:
            message = "Error in Import All Customers %s" % (res.content)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_id, False)
            return []
        try:
            response = res.json()
        except Exception as e:
            message = "Json Error : While import customers from WooCommerce for instance %s. \n%s" % (instance.name, e)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_id, False)
            return []
        else:
            return response

    @api.model
    def woo_get_customers(self, common_log_id, instance=False):
        """ This method used to call the request of the customer and prepare a customer response.
            @param : self, instance=False
            @return: customers
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 28 August 2020 .
            Task_id: 165956
        """
        process_import_export = self.env["woo.process.import.export"]
        common_log_line_obj = self.env["common.log.lines.ept"]
        bus_bus_obj = self.env['bus.bus']
        model_id = common_log_line_obj.get_model_id(self._name)
        woo_process_import_export_obj = process_import_export.browse(self._context.get('import_export_record_id'))
        wcapi = instance.woo_connect()
        response = wcapi.get('customers', params={"per_page": 100})
        customer_queues = []
        if not isinstance(response, requests.models.Response):
            message = "Import Customers \nResponse is not in proper format :: %s" % (response)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_id, False)
            return []
        if response.status_code not in [200, 201]:
            message = "Error in Import Customers %s" % (response.content)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_id, False)
            return []
        try:
            customers = response.json()
        except Exception as e:
            message = "Json Error : While import Customers from WooCommerce for instance %s. \n%s" % (instance.name, e)
            common_log_line_obj.woo_create_log_line(message, model_id, common_log_id, False)
            return []
        total_pages = response.headers.get('X-WP-TotalPages')
        if int(total_pages) >= 2:
            queues = woo_process_import_export_obj.create_customer_queue(customers)
            customer_queues += queues.mapped('id')
            message = "Customer Queue created ", queues.mapped('name')
            _logger.info("Created customer queues -- %s." % (str(message)))
            bus_bus_obj.sendone((self._cr.dbname, 'res.partner', self.env.user.partner_id.id),{'type': 'simple_notification', 'title': 'Woocomerce Connector', 'message':message,'sticky':False, 'warning': True})
            self._cr.commit()
            for page in range(2, int(total_pages) + 1):
                customers = self.woo_import_all_customers(wcapi, instance,common_log_id, page)
                if customers:
                    queues = woo_process_import_export_obj.create_customer_queue(customers)
                    customer_queues += queues.mapped('id')
                    _logger.info("Created customer queues -- %s." % (str(message)))
                    message = "Customer Queue created ", queues.mapped('name')
                    bus_bus_obj.sendone((self._cr.dbname, 'res.partner', self.env.user.partner_id.id),{'type': 'simple_notification', 'title': 'Woocomerce Connector', 'message':message,'sticky':False, 'warning': True})
                    self._cr.commit()
        else:
            if customers:
                queues = woo_process_import_export_obj.create_customer_queue(customers)
                customer_queues += queues.mapped('id')
                message = "Customer Queue created ", queues.mapped('name')
                _logger.info("Created customer queues -- %s." % (str(message)))
                bus_bus_obj.sendone((self._cr.dbname, 'res.partner', self.env.user.partner_id.id),{'type': 'simple_notification', 'title': 'Woocomerce Connector', 'message':message,'sticky':False, 'warning': True})
                self._cr.commit()
        return customer_queues

    def woo_create_contact_customer(self, vals, instance=False):
        """ This method used to create a contact type customer.
            @param : self, vals, instance=False
            @return: partner
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 2 September 2020 .
            Task_id: 165956
        """
        woo_cust_id = vals.get('id') or False
        contact_first_name = vals.get('first_name','')
        contact_last_name = vals.get('last_name','')
        contact_email = vals.get('email','')
        contact_name = "%s %s" % (contact_first_name, contact_last_name)
        if not contact_first_name and not contact_last_name:
            return False
        woo_customer_id = "%s" % woo_cust_id if woo_cust_id else False
        woo_instance_id = instance.id
        woo_partner_obj = self.env['woo.res.partner.ept']
        partner = woo_partner_obj.search([("woo_customer_id", "=", woo_customer_id), ("woo_instance_id", "=", woo_instance_id)],limit=1) if woo_customer_id else False
        if partner:
            partner = partner.partner_id
            return partner
        woo_partner_values = {'woo_customer_id': woo_customer_id,
                              'woo_instance_id': woo_instance_id,
                              }
        if contact_email:
            partner = self.search_partner_by_email(contact_email)
            if partner:
                if not partner.is_woo_customer:
                    partner.write({'is_woo_customer': True})
                    woo_partner_values.update({'partner_id': partner.id})
                    self.create_woo_res_partner_ept(woo_partner_values)
                return partner
        contact_partner_vals = ({
            'customer_rank': 1,
            'is_woo_customer': True,
            'type':'contact',
            'name': contact_name,
            'email': contact_email or False,
        })
        partner = self.create(contact_partner_vals)
        woo_partner_values.update({'partner_id': partner.id})
        self.create_woo_res_partner_ept(woo_partner_values)
        return partner

    def create_woo_res_partner_ept(self,woo_partner_values):
        """ This method use to create a Woocommerce layer customer.
            @param : self,woo_partner_values
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 31 August 2020 .
            Task_id: 165956
        """
        woo_partner_obj = self.env['woo.res.partner.ept']
        woo_partner_obj.create({
            'partner_id': woo_partner_values.get('partner_id'),
            'woo_customer_id': woo_partner_values.get('woo_customer_id'),
            'woo_instance_id': woo_partner_values.get('woo_instance_id'),
            'woo_company_name_ept': woo_partner_values.get('woo_company_name_ept'),
        })

    def woo_create_or_update_customer(self,customer_val,instance,parent_id,type):
        """ This method used to create a billing and shipping address base on the customer val response.
            @param : self,customer_val,instance,parent_id,type
            @return: address_partner
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 2 September 2020 .
            Task_id: 165956
        """
        first_name = customer_val.get("first_name")
        last_name = customer_val.get("last_name")
        if not first_name and not last_name:
            return False
        company_name = customer_val.get("company",'')
        partner_vals = self.woo_prepare_partner_vals(customer_val,instance)
        address_key_list = ['street', 'street2', 'city', 'zip', 'phone','state_id', 'country_id']

        if type == 'delivery':
            address_key_list = ['street', 'street2', 'city', 'zip','state_id', 'country_id']
        if company_name:
            address_key_list.append('company_name')
            partner_vals.update({'company_name':company_name})

        address_partner = self._find_partner_ept(partner_vals,address_key_list,[('parent_id', '=', parent_id.id),('type', '=', type)])
        if not address_partner:
            address_partner = self._find_partner_ept(partner_vals,address_key_list,[('parent_id', '=', parent_id.id)])
        if address_partner:
            return address_partner

        if 'company_name' in partner_vals:
            partner_vals.pop('company_name')
        partner_vals.update({'type':type,'parent_id':parent_id.id})
        address_partner = self.create(partner_vals)
        company_name and address_partner.write({'company_name':company_name})
        return address_partner

    def woo_prepare_partner_vals(self, vals,instance):
        """ This method used to prepare a partner vals.
            @param : self,vals,instance
            @return: partner_vals
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 29 August 2020 .
            Task_id: 165956
        """
        email = vals.get("email",False)
        first_name = vals.get("first_name")
        last_name = vals.get("last_name")
        name = "%s %s" % (first_name, last_name)
        phone = vals.get("phone")
        address1 = vals.get("address_1")
        address2 = vals.get("address_2")
        city = vals.get("city")
        zip = vals.get("postcode")
        state_name = vals.get("state")
        country_name = vals.get("country")
        country = self.get_country(country_name)

        state = self.create_or_update_state_ept(country_name, state_name, False, country)

        partner_vals = {
            'email': email or False,
            'name': name,
            'phone': phone,
            'street': address1,
            'street2': address2,
            'city': city,
            'zip': zip,
            'state_id': state and state.id or False,
            'country_id': country and country.id or False,
            'is_company': False,
            'lang': instance.woo_lang_id.code,
        }
        return partner_vals