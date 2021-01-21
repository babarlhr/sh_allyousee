# Copyright 2018-2019 Odoo House
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
{
    'name': 'Danish Address Layout',
    'version': '14.0.1.0.0',
    'depends': [
        'base',
    ],
    'author': 'Odoo House',
    'license': "LGPL-3",
    'website': 'https://odoohouse.dk',
    'category': 'Localization',
    'description': """
This module provides Danish address input field layout.
    """,
    'data': [
        'views/assets.xml',
        'views/res_partner_views.xml',
        'data/res_country_data.xml',
    ],
    'installable': True,
}
