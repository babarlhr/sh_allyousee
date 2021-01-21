# -*- coding: utf-8 -*-
# Copyright 2019 Odoo House
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Report invoice basis',
    'version': '14.0.1.0.0',
    'category': 'Localization',
    'description': "Remove tax on lines",
    'summary': 'Danmarkspakken',
    'sequence': 130,
    'depends': [
        'web', 'account',
    ],
    'data': [
        'views/report_invoice_basis.xml',
    ],
    'test': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
