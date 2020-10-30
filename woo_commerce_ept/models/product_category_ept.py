# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import requests, base64
import logging
from odoo import models, fields, api, _
from ..img_upload import img_file_upload

_logger = logging.getLogger("Woo")
from odoo.tools.mimetypes import guess_mimetype

class WooProductCategoryEpt(models.Model):
    _name = 'woo.product.categ.ept'
    _order = 'name'
    _description = "Woo Product Category"
    _rec_name = 'complete_name'

    name = fields.Char('Name', required="1", translate=True)
    parent_id = fields.Many2one('woo.product.categ.ept', string='Parent', index=True,
                                ondelete='cascade')
    description = fields.Char('Description', translate=True)
    slug = fields.Char(string='Slug',
                       help="The slug is the URL-friendly version of the name. It is usually all "
                            "lowercase and contains only letters, numbers, and hyphens.")
    display = fields.Selection([('default', 'Default'),
                                ('products', 'Products'),
                                ('subcategories', 'Sub Categories'),
                                ('both', 'Both')
                                ], default='default')
    woo_instance_id = fields.Many2one("woo.instance.ept", "Instance", required=1)
    exported_in_woo = fields.Boolean('Exported In Woo', default=False, readonly=True)
    woo_categ_id = fields.Char('Woo Category Id', size=120, readonly=True)
    woo_is_image_url = fields.Boolean("Is Image Url ?", related="woo_instance_id.woo_is_image_url")
    image = fields.Binary('Image')
    url = fields.Char(size=600, string='Image URL')
    response_url = fields.Char(size=600, string='Response URL', help="URL from WooCommerce")
    complete_name = fields.Char('Complete Name', compute='_compute_complete_name')

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = '%s / %s' % (
                    category.parent_id.complete_name, category.name)
            else:
                category.complete_name = category.name

    @api.model
    def name_create(self, name):
        return self.create({'name':name}).name_get()[0]

    def create_or_update_woo_categ(self, instance, woo_common_log_id, model_id,
                                   woo_product_categ_name, sync_images_with_product=True):
        common_log_line_obj = self.env["common.log.lines.ept"]
        woo_categ = False
        categ_name_list = []
        product_categ_ids = []
        wcapi = instance.woo_connect()
        categ_res = wcapi.get("products/categories?fields=id,name,parent")
        if not isinstance(categ_res, requests.models.Response):
            message = "Get Product Category \nResponse is not in proper format :: %s" % (
                categ_res)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id, False)
            return False
        if categ_res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(categ_res.content, model_id,
                                                            woo_common_log_id, False)
            return False
        try:
            categ_response = categ_res.json()
        except Exception as e:
            message = "Json Error : While import product category %s from WooCommerce for " \
                      "instance %s. \n%s" % (woo_product_categ_name, instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id, False)
            return False
        if instance.woo_version == 'v3':
            product_categories = categ_response.get('product_categories')
        else:
            product_categories = categ_response
        categ = list(filter(lambda categ:categ['name'].lower() == woo_product_categ_name.lower(),
                            product_categories))
        if categ:
            categ = categ[0]
            product_categ_ids.append(categ.get('id'))
            categ_name_list.append(woo_product_categ_name.lower())
        for product_categ_id in product_categ_ids:
            tmp_categ = list(
                    filter(lambda categ1:categ1['id'] == product_categ_id, product_categories))
            if tmp_categ:
                tmp_categ = tmp_categ[0]
                if tmp_categ.get('parent') and tmp_categ.get('parent') not in product_categ_ids:
                    product_categ_ids.append(tmp_categ.get('parent'))
                    tmp_parent_categ = list(
                            filter(lambda categ2:categ2['id'] == tmp_categ.get('parent'),
                                   product_categories))
                    tmp_parent_categ and categ_name_list.append(
                            tmp_parent_categ[0].get('name').lower())

        product_categ_ids.reverse()
        for product_categ_id in product_categ_ids:
            response = wcapi.get("products/categories/%s" % (product_categ_id))
            if not isinstance(response, requests.models.Response):
                message = "Get Product Category \nResponse is not in proper format :: %s" % (
                    response)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                continue
            if response.status_code not in [200, 201]:
                common_log_line_obj.woo_product_export_log_line(response.content, model_id,
                                                                woo_common_log_id, False)
                continue
            try:
                response = response.json()
            except Exception as e:
                message = "Json Error : While import product category with id %s from " \
                          "WooCommerce for instance %s. \n%s" % (
                              product_categ_id, instance.name, e)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                continue
            if instance.woo_version == 'v3':
                categ = response.get('product_category')
            else:
                categ = response
            product_category = {'id':categ.get('id'), 'name':categ.get('name')}
            categ_name = product_category.get('name')
            if categ_name.lower() in categ_name_list:
                single_catg_res = wcapi.get("products/categories/%s" % (product_category.get('id')))
                if not isinstance(single_catg_res, requests.models.Response):
                    message = "Get Product Category \nResponse is not in proper format :: %s" % (
                        single_catg_res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                    continue
                try:
                    single_catg_response = single_catg_res.json()
                except Exception as e:
                    message = "Json Error : While import product category with id %s from" \
                              " WooCommerce for instance %s. \n%s" % (
                                  product_category.get('id'), instance.name, e)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                    continue
                if instance.woo_version == 'v3':
                    single_catg = single_catg_response.get('product_category')
                else:
                    single_catg = single_catg_response
                parent_woo_id = single_catg.get('parent')
                parent_id = False
                binary_img_data = False
                if parent_woo_id:
                    parent_id = self.search([('woo_categ_id', '=', parent_woo_id),
                                             ('woo_instance_id', '=', instance.id)], limit=1).id
                vals = {'name':categ_name, 'woo_instance_id':instance.id, 'parent_id':parent_id,
                        'woo_categ_id':product_category.get('id'),
                        'display':single_catg.get('display'), 'slug':single_catg.get('slug'),
                        'exported_in_woo':True, 'description':single_catg.get('description', '')}
                if sync_images_with_product:
                    res_image = False
                    if instance.woo_version == 'v3':
                        res_image = single_catg.get('image')
                    else:
                        res_image = single_catg.get('image') and single_catg.get('image').get('src',
                                                                                              '')
                    if instance.woo_is_image_url:
                        res_image and vals.update({'response_url':res_image})
                    else:
                        if res_image:
                            try:
                                res_img = requests.get(res_image, stream=True, verify=False,
                                                       timeout=10)
                                if res_img.status_code == 200:
                                    binary_img_data = base64.b64encode(res_img.content)
                            except Exception:
                                pass
                        binary_img_data and vals.update({'image':binary_img_data})
                woo_categ = self.search([('woo_categ_id', '=', product_category.get('id')),
                                         ('woo_instance_id', '=', instance.id)], limit=1)
                if not woo_categ:
                    woo_categ = self.search([('slug', '=', product_category.get('slug')),
                                             ('woo_instance_id', '=', instance.id)], limit=1)
                if woo_categ:
                    woo_categ.write(vals)
                else:
                    woo_categ = self.create(vals)
        return woo_categ

    def import_all_woo_categories(self, wcapi, instance, page, woo_common_log_id, model_id):
        common_log_line_obj = self.env["common.log.lines.ept"]
        if instance.woo_version == 'v3':
            res = wcapi.get("products/categories?filter[limit]=1000&page=%s" % (page))
        else:
            res = wcapi.get("products/categories", params={'per_page':100, 'page':page})
        if not isinstance(res, requests.models.Response):
            message = "Get All Product Category \nResponse is not in proper format :: %s" % (
                res)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id, False)
            return []
        if res.status_code not in [200, 201]:
            common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                            woo_common_log_id, False)
            return []
        try:
            response = res.json()
        except Exception as e:
            message = "Json Error : While import product categories from WooCommerce for " \
                      "instance %s. \n%s" % (instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id, False)
            return []
        if instance.woo_version == 'v3':
            errors = response.get('errors', '')
            if errors:
                message = errors[0].get('message')
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return []
            return response.get('product_categories')
        else:
            return response

    def sync_woo_product_category(self, instance, woo_common_log_id, woo_product_categ=False,
                                  woo_product_categ_name=False, sync_images_with_product=True):
        common_log_line_obj = self.env["common.log.lines.ept"]
        model_id = common_log_line_obj.get_model_id("woo.product.categ.ept")
        wcapi = instance.woo_connect()
        if woo_product_categ and woo_product_categ.exported_in_woo:
            response = wcapi.get("products/categories/%s" % (woo_product_categ.woo_categ_id))
            if not isinstance(response, requests.models.Response):
                if not isinstance(response, requests.models.Response):
                    message = "Get Product Category \nResponse is not in proper format :: %s" % (
                        response)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                return True
            if response.status_code == 404:
                self.export_product_categs(instance, [woo_product_categ], woo_common_log_id,
                                           model_id)
                return True
        elif woo_product_categ and not woo_product_categ.exported_in_woo:
            woo_categ = self.create_or_update_woo_categ(instance, woo_common_log_id,
                                                        model_id, woo_product_categ.name,
                                                        sync_images_with_product)
            if woo_categ:
                return woo_categ
            else:
                self.export_product_categs(instance, [woo_product_categ], woo_common_log_id,
                                           model_id)
                return True
        elif not woo_product_categ and woo_product_categ_name:
            woo_categ = self.create_or_update_woo_categ(instance, woo_common_log_id,
                                                        model_id, woo_product_categ_name,
                                                        sync_images_with_product)
            return woo_categ
        else:
            if instance.woo_version == 'v3':
                response = wcapi.get("products/categories?filter[limit]=1000")
            else:
                response = wcapi.get("products/categories", params={'per_page':100})
            if not isinstance(response, requests.models.Response):
                message = "Get Product Category \nResponse is not in proper format :: %s" % (
                    response)
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return True
            if response.status_code not in [200, 201]:
                message = response.content
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return True

        total_pages = 1
        if instance.woo_version == 'v3':
            total_pages = response and response.headers.get('X-WC-TotalPages') or 1
        else:
            total_pages = response and response.headers.get('x-wp-totalpages') or 1
        try:
            res = response.json()
        except Exception as e:
            message = "Json Error : While import product categories from WooCommerce for " \
                      "instance %s. \n%s" % (instance.name, e)
            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                            woo_common_log_id, False)
            return False
        if instance.woo_version == 'v3':
            errors = res.get('errors', '')
            if errors:
                message = errors[0].get('message')
                common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                woo_common_log_id, False)
                return True
            if woo_product_categ:
                response = res.get('product_category')
                results = [response]
            else:
                results = res.get('product_categories')
        else:
            if woo_product_categ:
                results = [res]
            else:
                results = res
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                results = results + self.import_all_woo_categories(wcapi, instance, page,
                                                                   woo_common_log_id, model_id)

        processed_categs = []
        for res in results:
            if not isinstance(res, dict):
                continue
            if res.get('id', False) in processed_categs:
                continue

            categ_results = []
            categ_results.append(res)
            for categ_result in categ_results:
                if not isinstance(categ_result, dict):
                    continue
                if categ_result.get('parent'):
                    parent_categ = list(
                            filter(lambda categ:categ['id'] == categ_result.get('parent'), results))
                    if parent_categ:
                        parent_categ = parent_categ[0]
                    else:
                        response = wcapi.get(
                                "products/categories/%s" % (categ_result.get('parent')))
                        if not isinstance(response, requests.models.Response):
                            message = "Get Product Category \nResponse is not in proper format " \
                                      ":: %s" % (response)
                            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                            woo_common_log_id,
                                                                            False)
                            continue
                        try:
                            response = response.json()
                        except Exception as e:
                            message = "Json Error : While import parent category for category" \
                                      " %s from WooCommerce for instance %s. \n%s" % (
                                          categ_result.get('name'), instance.name, e)
                            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                            woo_common_log_id,
                                                                            False)
                            continue
                        if instance.woo_version == 'v3':
                            parent_categ = response.get('product_category')
                        else:
                            parent_categ = response
                    if parent_categ not in categ_results:
                        categ_results.append(parent_categ)

            categ_results.reverse()
            for result in categ_results:
                if not isinstance(result, dict):
                    continue
                if result.get('id') in processed_categs:
                    continue

                woo_categ_id = result.get('id')
                woo_categ_name = result.get('name')
                display = result.get('display')
                slug = result.get('slug')
                parent_woo_id = result.get('parent')
                parent_id = False
                binary_img_data = False
                if parent_woo_id:
                    parent_id = self.search([('woo_categ_id', '=', parent_woo_id),
                                             ('woo_instance_id', '=', instance.id)], limit=1).id
                vals = {'name':woo_categ_name, 'woo_instance_id':instance.id, 'display':display,
                        'slug':slug, 'exported_in_woo':True, 'parent_id':parent_id,
                        'description':result.get('description', '')}
                if sync_images_with_product:
                    res_image = False
                    if instance.woo_version == 'v3':
                        res_image = result.get('image')
                    else:
                        res_image = result.get('image') and result.get('image').get('src', '')

                    if instance.woo_is_image_url:
                        res_image and vals.update({'response_url':res_image})
                    else:
                        if res_image:
                            try:
                                res_img = requests.get(res_image, stream=True, verify=False,
                                                       timeout=10)
                                if res_img.status_code == 200:
                                    binary_img_data = base64.b64encode(res_img.content)
                            except Exception:
                                pass
                        binary_img_data and vals.update({'image':binary_img_data})
                vals.update({'woo_categ_id':woo_categ_id, 'slug':slug})
                woo_product_categ = self.search(
                        [('woo_categ_id', '=', woo_categ_id),
                         ('woo_instance_id', '=', instance.id)])
                if not woo_product_categ:
                    woo_product_categ = self.search(
                            [('slug', '=', slug), ('woo_instance_id', '=', instance.id)], limit=1)
                if woo_product_categ:
                    woo_product_categ.write(vals)
                else:
                    self.create(vals)

                processed_categs.append(result.get('id', False))
        return True

    def export_product_categs(self, instance, woo_product_categs, woo_common_log_id, model_id):
        common_log_line_obj = self.env['common.log.lines.ept']
        wcapi = instance.woo_connect()
        for woo_product_categ in woo_product_categs:
            if woo_product_categ.woo_categ_id:
                res = wcapi.get("products/categories/%s" % (woo_product_categ.woo_categ_id))
                if not isinstance(res, requests.models.Response):
                    message = "Get Product Category \nResponse is not in proper format :: %s" % (
                        res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                    continue
                if res.status_code != 404:
                    continue
                if res.status_code not in [200, 201]:
                    common_log_line_obj.woo_product_export_log_line(res.content, model_id,
                                                                    woo_common_log_id, False)
                    continue
            product_categs = []
            product_categs.append(woo_product_categ)
            for categ in product_categs:
                if categ.parent_id and categ.parent_id not in product_categs and not categ.parent_id.woo_categ_id:
                    product_categs.append(categ.parent_id)

            product_categs.reverse()
            for woo_product_categ in product_categs:
                img_url = ''
                if instance.woo_is_image_url:
                    if woo_product_categ.response_url:
                        try:
                            img = requests.get(woo_product_categ.response_url, stream=True,
                                               verify=False, timeout=10)
                            if img.status_code == 200:
                                img_url = woo_product_categ.response_url
                            elif woo_product_categ.url:
                                img_url = woo_product_categ.url
                        except Exception:
                            img_url = woo_product_categ.url or ''
                    elif woo_product_categ.url:
                        img_url = woo_product_categ.url
                else:
                    res = {}
                    if woo_product_categ.image:
                        mime_type = guess_mimetype(base64.b64decode(woo_product_categ.image))
                        res = img_file_upload.upload_image(instance, woo_product_categ.image,
                                                           "%s_%s" % (woo_product_categ.name,
                                                                      woo_product_categ.id),
                                                           mime_type)
                    img_url = res and res.get('url', False) or ''
                row_data = {'name':str(woo_product_categ.name),
                            'description':str(woo_product_categ.description or ''),
                            'display':str(woo_product_categ.display),
                            }
                if woo_product_categ.slug:
                    row_data.update({'slug':str(woo_product_categ.slug)})
                img_url and row_data.update({'image':img_url})
                if instance.woo_version != 'v3' and img_url:
                    row_data.update({'image':{'src':img_url}})
                woo_product_categ.parent_id.woo_categ_id and row_data.update(
                        {'parent':woo_product_categ.parent_id.woo_categ_id})
                if instance.woo_version == 'v3':
                    data = {'product_category':row_data}
                elif instance.woo_version != 'v3':
                    data = row_data
                res = wcapi.post("products/categories", data)
                if not isinstance(res, requests.models.Response):
                    message = "Export Product Category \nResponse is not in proper format :: %s" % (
                        res)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                    continue
                if res.status_code not in [200, 201]:
                    if res.status_code == 500:
                        try:
                            response = res.json()
                        except Exception as e:
                            message = "Json Error : While export product category %s to " \
                                      "WooCommerce for instance %s. \n%s" % (
                                          woo_product_categ.name, instance.name, e)
                            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                            woo_common_log_id,
                                                                            False)
                            continue
                        if isinstance(response, dict) and response.get('code') == 'term_exists':
                            woo_product_categ.write(
                                    {'woo_categ_id':response.get('data'), 'exported_in_woo':True})
                            continue
                        else:
                            message = res.content
                            common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                            woo_common_log_id,
                                                                            False)
                            continue
                try:
                    response = res.json()
                except Exception as e:
                    message = "Json Error : While export product category %s to WooCommerce for" \
                              " instance %s. \n%s" % (woo_product_categ.name, instance.name, e)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                    continue
                if not isinstance(response, dict):
                    message = "Export Product Category \nResponse is not in proper format :: %s" % (
                        response)
                    common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                    woo_common_log_id, False)
                    continue
                if instance.woo_version == 'v3':
                    errors = response.get('errors', '')
                    if errors:
                        message = errors[0].get('message')
                        message = "%s :: %s" % (message, woo_product_categ.name)
                        common_log_line_obj.woo_product_export_log_line(message, model_id,
                                                                        woo_common_log_id, False)
                        continue
                    product_categ = response.get('product_category', False)
                else:
                    product_categ = response
                product_categ_id = product_categ and product_categ.get('id', False)
                slug = product_categ and product_categ.get('slug', '')
                response_data = {}
                if instance.woo_is_image_url:
                    response_url = ''
                    if instance.woo_version == 'v3':
                        response_url = product_categ and product_categ.get('image', '')
                    else:
                        response_url = product_categ and product_categ.get(
                                'image') and product_categ.get('image', {}).get('src', '') or ''
                    response_data.update({'response_url':response_url})
                if product_categ_id:
                    response_data.update(
                            {'woo_categ_id':product_categ_id, 'slug':slug, 'exported_in_woo':True})
                    woo_product_categ.write(response_data)
        self._cr.commit()
        return True

    def update_product_categs_in_woo(self, instance, woo_product_categs):
        """- This method used to update product category from Odoo to Woocommerce.
           - It will only update category which is already synced.
            @param : self
            @author: Haresh Mori @Emipro Technologies Pvt. Ltd on date 13/12/2019.
        """
        wcapi = instance.woo_connect()
        common_log_line_obj = self.env['common.log.lines.ept']
        common_log_book_obj = self.env["common.log.book.ept"]
        model_id = common_log_line_obj.get_model_id("woo.product.categ.ept")
        common_log_book_id = common_log_book_obj.create({"type":"export",
                                                                     "module":"woocommerce_ept",
                                                                     "woo_instance_id":instance.id,
                                                                     "active":True})
        updated_categs = []
        for woo_categ in woo_product_categs:
            if woo_categ in updated_categs:
                continue
            product_categs = []
            product_categs.append(woo_categ)
            for categ in product_categs:
                if categ.parent_id and categ.parent_id not in product_categs and categ.parent_id not in updated_categs:
                    self.sync_woo_product_category(instance, common_log_book_id,
                                                   woo_product_categ=categ.parent_id)
                    product_categs.append(categ.parent_id)

            product_categs.reverse()
            for woo_categ in product_categs:
                img_url = ''
                if instance.woo_is_image_url:
                    if woo_categ.response_url:
                        try:
                            img = requests.get(woo_categ.response_url, stream=True,
                                               verify=False, timeout=10)
                            if img.status_code == 200:
                                img_url = woo_categ.response_url
                            elif woo_categ.url:
                                img_url = woo_categ.url
                        except Exception:
                            img_url = woo_categ.url or ''
                    elif woo_categ.url:
                        img_url = woo_categ.url
                else:
                    res = {}
                    if woo_categ.image:
                        mime_type = guess_mimetype(base64.b64decode(woo_categ.image))
                        res = img_file_upload.upload_image(instance, woo_categ.image,
                                                           "%s_%s" % (woo_categ.name, woo_categ.id),
                                                           mime_type)
                    img_url = res and res.get('url', False) or ''

                row_data = {'name':str(woo_categ.name),
                            'display':str(woo_categ.display),
                            'description':str(woo_categ.description or '')}
                if woo_categ.slug:
                    row_data.update({'slug':str(woo_categ.slug)})
                if instance.woo_version == 'wc/v3' and img_url:
                    row_data.update({'image':{'src':img_url}})
                woo_categ.parent_id.woo_categ_id and row_data.update(
                        {'parent':woo_categ.parent_id.woo_categ_id})
                row_data.update({'id':woo_categ.woo_categ_id})
            _logger.info("Start request for category name: '%s'" % (woo_categ.name))
            res = wcapi.post('products/categories/batch', {'update':[row_data]})
            if not isinstance(res, requests.models.Response):
                message = "Update Product Category \nResponse is not in proper format :: %s" % (res)
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id,
                                                        False)
                continue
            if res.status_code not in [200, 201]:
                common_log_line_obj.woo_create_log_line(res.content, model_id, common_log_book_id,
                                                        False)
                continue
            try:
                response = res.json()
            except Exception as e:
                message = "Json Error : While update product category with id %s to WooCommerce for instance %s. \n%s " % (
                woo_categ.woo_categ_id, instance.name, e)
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id,
                                                        False)
                continue
            if not isinstance(response, dict):
                message = "Update Product Category \nResponse is not in proper format :: %s" % (
                    response)
                common_log_line_obj.woo_create_log_line(message, model_id, common_log_book_id,
                                                        False)
                continue
            updated_categs.append(woo_categ)
            _logger.info("Done request for category name :'%s'" % (woo_categ.name))
        if not common_log_book_id.log_lines:
            common_log_book_id.unlink()
        return True
