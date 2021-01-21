# -*- coding: utf-8 -*-
# Copyright 2019 Odoo House
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Danish address layout on reports',
    'version': '14.0.1.0.0',
    'category': 'Localization',
    'summary': 'Danmarkspakken',
    'sequence': 110,
    'description': "",
    'depends': [
        'base',
        'web',
    ],
    'data': [
        'views/address_layout.xml',
    ],
    'test': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
