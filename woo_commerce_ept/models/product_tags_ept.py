# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import requests
import logging

from odoo import models, fields, api

_logger = logging.getLogger("Woo")


class WooTagsEpt(models.Model):
    _name = "woo.tags.ept"
    _order = 'name'
    _description = "Woo Product Tag"

    name = fields.Char("Name", required=1, copy=False)
    description = fields.Text('Description')
    slug = fields.Char(string='Slug',
                       help="The slug is the URL-friendly version of the name. It is usually all "
                            "lowercase and contains only letters, numbers, and hyphens.", copy=False)
    woo_tag_id = fields.Char("Woo Tag Id",size=120, copy=False)
    exported_in_woo = fields.Boolean("Exported In Woo", default=False, copy=False)
    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance", required=1, copy=False)

    @api.model
    def woo_export_product_tags(self, instances, woo_product_tags, common_log_book_id, model_id=False):
        """
        This method is used for export the product tags from odoo to woo commerce
        :param instances:  It is the browsable object of the woo instance
        :param woo_product_tags: It contain the browsable object of woo product tags and its type is list
        :param common_log_book_id: It contain the browsable object of the common log book ept model
        :param model_id: It contain the id of the model class and its Type is Integer
        :return: It will return True if the process of export tags in woo is successful completed
        @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
        @change: For exporting tags from wizard and action by Maulik Barad on Date 13-Dec-2019.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        if not model_id:
            model_id = common_log_line_obj.get_model_id(self._name)
        for instance in instances:
            wcapi = instance.woo_connect()
            product_tags = []
            for woo_product_tag in woo_product_tags.filtered(lambda x: x.woo_instance_id == instance):
                row_data = {"name": woo_product_tag.name,
                            "description": str(woo_product_tag.description or ""),
                            "slug": str(woo_product_tag.slug or "")}
                product_tags.append(row_data)
            if not product_tags:
                continue
            data = {"create":product_tags}
            _logger.info("Exporting tags to Woo of instance {0}".format(instance.name))
            res = wcapi.post("products/tags/batch", data)
            if not isinstance(res, requests.models.Response):
                message = "Export Product Tags \nResponse is not in proper format :: %s" % (res)
                common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_book_id,False)
                return False
            if res.status_code not in [200, 201]:
                if res.status_code == 500:
                    try:
                        response = res.json()
                    except Exception as error:
                        message = "Json Error : While exporting tag to WooCommerce for instance %s. \n%s" % (instance.name, error)
                        common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                        common_log_book_id,
                                                                        False)
                    if isinstance(response, dict) and response.get("code") == "term_exists":
                        woo_product_tag.write({"woo_tag_id": response.get("data"), "exported_in_woo": True})
                    else:
                        message = res.content
                        common_log_line_obj.woo_product_export_log_line(message, model_id,common_log_book_id,False)
            try:
                response = res.json()
            except Exception as error:
                message = "Json Error : While exporting tag to WooCommerce for instance %s. \n%s" % (instance.name, error)
                common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_book_id,False)
                return False
            exported_product_tags = response.get("create")
            for tag in exported_product_tags:
                woo_product_tag = woo_product_tags.filtered(lambda x: x.name == tag.get("name") and x.woo_instance_id == instance)
                if tag.get("id", False) and woo_product_tag:
                    woo_product_tag.write(
                        {"woo_tag_id": tag.get("id", False),
                         "exported_in_woo": True,
                         "slug": tag.get("slug", "")})
            _logger.info("Exported {0} tags to Woo of instance {1}".format(len(exported_product_tags), instance.name))
        self._cr.commit()
        return True

    def woo_import_all_tags(self, wcapi, instance, page, woo_common_log_id, model_id):
        """
        This method is used for collecting the info of tags by page wise and return the response into dict format
        :param wcapi: It is the connection object of woo commerce to odoo
        :param instance: It is the browsable object of the woo instance
        :param page: It contain the page number of woo product tags and its type is Integer
        :param woo_common_log_id: It contain the browsable object of the common log book ept model
        :param model_id: It contain the id of the model class
        :return: It will return the response of collection details of tags from woo and its type is Dict
        @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        if instance.woo_version == 'v3':
            res = wcapi.get("products/tags?filter[limit]=1000&page=%s" % (page))
        else:
            res = wcapi.get("products/tags", params={"per_page": 100, 'page': page})
        if not isinstance(res, requests.models.Response):
            common_log_line_obj.create(
                {'message': "Get Product Tags \nResponse is not in proper format :: %s" % (res),
                 'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                 'model_id': model_id,
                 'res_id': self and self.id or False
                 })
            return []
        if res.status_code not in [200, 201]:
            common_log_line_obj.create(
                {'message': res.content,
                 'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                 'model_id': model_id,
                 'res_id': self and self.id or False
                 })
            return []
        try:
            response = res.json()
        except Exception as e:
            common_log_line_obj.create({
                'message': "Json Error : While import tags from WooCommerce for instance %s. \n%s" % (
                    instance.name, e),
                'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                'model_id': model_id,
                'res_id': self and self.id or False
            })
            return []
        if instance.woo_version == 'v3':
            errors = response.get('errors', '')
            if errors:
                message = errors[0].get('message')
                common_log_line_obj.create(
                    {'message': message,
                     'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                     'model_id': model_id,
                     'res_id': self and self.id or False
                     })
                return []
            return response.get('product_tags')
        # elif instance.woo_version == 'new':
        else:
            return response

    def woo_sync_product_tags(self, instance, woo_common_log_id):
        """
        This method is used for collecting the tags information and also sync the tags into woo commerce in odoo
        :param instance: It is the browsable object of the woo instance
        :param woo_common_log_id: It contain the browsable object of the common log book ept model
        :return: return True if the process of tags is successful complete
        @author: Dipak Gogiya @Emipro Technologies Pvt.Ltd
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id("woo.tags.ept")
        wcapi = instance.woo_connect()
        res = wcapi.get("products/tags", params={"per_page": 100})
        if not isinstance(res, requests.models.Response):
            common_log_line_obj.create(
                {'message': "Get Product Tags \nResponse is not in proper format :: %s" % (res),
                 'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                 'model_id': model_id,
                 'res_id': self and self.id or False
                 })
            return True
        if res.status_code not in [200, 201]:
            common_log_line_obj.create({
                'message': "Get Product Tags \nResponse is not in proper format :: %s" % (
                    res.content),
                'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                'model_id': model_id,
                'res_id': self and self.id or False
            })
            return True
        results = []
        total_pages = res and res.headers.get('x-wp-totalpages', 0) or 1
        try:
            res = res.json()
        except Exception as e:
            common_log_line_obj.create({
                'message': "Json Error : While import tags from WooCommerce for instance %s. \n%s" % (
                    instance.name, e),
                'log_book_id': woo_common_log_id and woo_common_log_id.id or False,
                'model_id': model_id,
                'res_id': self and self.id or False
            })
            return False
        results = res
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                results = results + self.woo_import_all_tags(wcapi, instance, page,
                                                             woo_common_log_id,
                                                             model_id)

        for res in results:
            if not isinstance(res, dict):
                continue
            tag_id = res.get('id')
            name = res.get('name')
            description = res.get('description')
            slug = res.get('slug')
            woo_tag = self.search(
                [('woo_tag_id', '=', tag_id), ('woo_instance_id', '=', instance.id)], limit=1)
            if not woo_tag:
                woo_tag = self.search(
                    [('slug', '=', slug), ('woo_instance_id', '=', instance.id)], limit=1)
            if woo_tag:
                woo_tag.write({'woo_tag_id': tag_id, 'name': name, 'description': description,
                               'slug': slug, 'exported_in_woo': True})
            else:
                self.create({'woo_tag_id': tag_id, 'name': name, 'description': description,
                             'slug': slug, 'woo_instance_id': instance.id,
                             'exported_in_woo': True})
        return True

    @api.model
    def woo_update_product_tags(self, instances, woo_product_tags, common_log_book_id, model_id=False):
        """
        This method will update the tags in WooCommerce.
        @author: Maulik Barad on Date 14-Dec-2019.
        @param instances: Recordset of Woo Instance.
        @param woo_product_tags: Recordset of Tag in Woo layer to update.
        @param common_log_book_id: Record of Common Log Book to add log lines in it.
        @param model_id: Id of the model from which we are updating the tags.
        """
        common_log_line_obj = self.env["common.log.lines.ept"]
        if not model_id:
            model_id = common_log_line_obj.get_model_id(self._name)
        for instance in instances:
            wcapi = instance.woo_connect()
            product_tags = []
            for woo_product_tag in woo_product_tags.filtered(lambda x: x.woo_instance_id == instance):
                row_data = {"id":woo_product_tag.woo_tag_id,
                            "name": woo_product_tag.name,
                            "description": str(woo_product_tag.description or ""),
                            "slug": str(woo_product_tag.slug or "")}
                product_tags.append(row_data)

            data = {"update":product_tags}
            _logger.info("Updating tags in Woo of instance {0}".format(instance.name))
            res = wcapi.post("products/tags/batch", data)
            if not isinstance(res, requests.models.Response):
                message = "Update Product Tags \nResponse is not in proper format :: %s" % (
                    res)
                common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_book_id,
                                                                False)
                return False
            if res.status_code not in [200, 201]:
                if res.status_code == 500:
                    try:
                        response = res.json()
                    except Exception as e:
                        message = "Json Error : While updating tag to WooCommerce for instance " \
                                  "%s. \n%s" % (instance.name, e)
                        common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                        common_log_book_id,
                                                                        False)
                    if isinstance(response, dict) and response.get("code") == "term_exists":
                        woo_product_tag.write(
                            {"woo_tag_id": response.get("data"), "exported_in_woo": True})
                    else:
                        message = res.content
                        common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                        common_log_book_id,
                                                                        False)
            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While updating tag to WooCommerce for instance %s. \n%s" \
                          % (instance.name, e)
                common_log_line_obj.woo_product_export_log_line(message, model_id, common_log_book_id,
                                                                False)
                return False
            updated_product_tags = response.get("update")
            for tag in updated_product_tags:
                woo_product_tag = woo_product_tags.filtered(lambda x: x.woo_tag_id == tag.get("id") and x.woo_instance_id == instance)
                if woo_product_tag:
                    woo_product_tag.write({"slug": tag.get("slug", "")})
            _logger.info("Updated {0} tags to Woo of instance {1}".format(len(updated_product_tags), instance.name))
        return True
