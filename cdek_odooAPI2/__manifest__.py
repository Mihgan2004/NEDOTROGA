# -*- coding: utf-8 -*-
{
    'name': 'CDEK Integration',
    'version': '18.0.1.0.0',
    'summary': 'Интеграция с транспортной компанией СДЭК (API v2) + JS Widget',
    'description': """
        Модуль интеграции Odoo 18 с CDEK API v2.
        Реализует расчёт стоимости и сроков доставки, выбор ПВЗ,
        отправку заказов, получение квитанций, синхронизацию статусов,
        а также интеграцию с официальным JS-виджетом СДЭК.
    """,
    'category': 'Warehouse/Delivery',
    'author': 'ВашеНазваниеКомпании',
    'website': 'https://your.company.website',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'sale',
        'stock',
        'delivery',
        'website_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cdek_scheduled_actions.xml',
        'views/res_config_settings_views.xml',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/sale_order_views.xml',
        'views/cdek_widget_template.xml',  # добавляем шаблон виджета
    ],

    "assets": {
        "web.assets_backend": [
            "cdek_odooAPI2/static/src/js/cdek_pvz_selector_map.js",
            "cdek_odooAPI2/static/src/xml/cdek_pvz_selector_map.xml",
        ],
        "web.assets_frontend": [
            'cdek_odooAPI2/static/lib/cdek_widget.js',  # CDN виджета
            "cdek_odooAPI2/static/src/js/cdek_widget_loader.js",  # твой загрузчик
            "cdek_odooAPI2/static/src/js/cdek_pvz_selector_map.js",
            "cdek_odooAPI2/static/src/xml/cdek_pvz_selector_map.xml",
        ],
        "web.assets_qweb": [
            "cdek_odooAPI2/static/src/xml/cdek_pvz_selector_map.xml",
        ],
    },

    'installable': True,
    'application': True,
    'auto_install': False,
}