# -*- coding: utf-8 -*-
# Copyright 2019 Odoo House
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Report sale order basis',
    'version': '14.0.1.0.0',
    'category': 'Localization',
    'description': "Remove tax on lines",
    'summary': 'Danmarkspakken',
    'sequence': 140,
    'depends': [
        'web', 'sale',
    ],
    'data': [
        'views/report_sale_basis.xml',
    ],
    'test': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
