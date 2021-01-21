
{
    'name': 'Report purchase order basis',
    'version': '13.0.1.0.0',
    'category': 'Localization',
    'description': "Remove tax on lines",
    'summary': 'Danmarkspakken',
    'sequence': 140,
    'depends': ['purchase'
    ],
    'data': [
        'views/report_purchase_basis.xml',
    ],
    'test': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
