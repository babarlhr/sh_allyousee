# -*- coding: utf-8 -*-
# Copyright 2019 Odoo House
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Report external layout basis',
    'version': '14.0.1.0.0',
    'category': 'Localization',
    'description': "Move logo to right",
    'summary': 'Danmarkspakken',
    'sequence': 120,
    'depends': [
        'base',
        'web',
    ],
    'data': [
        'views/external_layouts.xml',
    ],
    'test': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
