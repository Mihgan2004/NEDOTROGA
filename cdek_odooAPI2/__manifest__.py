# -*- coding: utf-8 -*-
{
    'name': 'CDEK Integration',
    'version': '18.0.1.0.0',
    'summary': 'Интеграция с транспортной компанией СДЭК (API v2)',
    'description': """
        Модуль интеграции Odoo 18 с CDEK API v2.
        Реализует расчёт стоимости и сроков доставки, выбор ПВЗ,
        отправку заказов, получение квитанций, синхронизацию статусов
        и всё необходимое для надёжной работы в тестовом и боевом режимах.
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
        # права доступа
        'security/ir.model.access.csv',
        # запланированные задачи
        'data/cdek_scheduled_actions.xml',
        # настройки модуля
        'views/res_config_settings_views.xml',
        # расширения delivery.carrier
        'views/delivery_carrier_views.xml',
        # отображение полей в отгрузках
        'views/stock_picking_views.xml',
        # отображение полей и кнопок в заказах
        'views/sale_order_views.xml',
    ],

    "assets": {
        "web.assets_backend": [
            "cdek_odooAPI2/static/src/js/cdek_pvz_selector_map.js",
            "cdek_odooAPI2/static/src/xml/cdek_pvz_selector_map.xml",
        ],
        "web.assets_frontend": [
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
