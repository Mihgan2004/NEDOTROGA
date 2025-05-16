# -*- coding: utf-8 -*-

# CDEK API URLs
CDEK_API_PROD_URL = "https://api.cdek.ru/v2/"
CDEK_API_TEST_URL = "https://api.edu.cdek.ru/v2/"

# CDEK API Endpoints (relative to base URL)
CDEK_URLS = {
    "token": "oauth/token",
    "orders": "orders",
    "order_by_uuid": "orders/{uuid}",
    "calculator_tariff": "calculator/tariff",
    "delivery_points": "deliverypoints",
    "location_cities": "location/cities",
    "location_regions": "location/regions",
    "print_barcodes": "print/orders/{uuid}/barcodes.{format}",
    "print_receipt": "print/orders/{uuid}/receipt.{format}",
}

# Label Formats supported by CDEK and this module
CDEK_LABEL_FORMATS = [
    ('pdf', 'PDF'),
    ('zpl', 'ZPL'),
    # ('epl', 'EPL'), # Add if CDEK supports and you need it
]

# Default package dimensions and weight (used if product has no dimensions/weight)
# Values should be set in res.config.settings, these are just illustrative defaults
DEFAULT_LENGTH_CM = 10.0
DEFAULT_WIDTH_CM = 10.0
DEFAULT_HEIGHT_CM = 10.0
DEFAULT_WEIGHT_KG = 1.0

# CDEK Order Type (1 for "интернет-магазин")
CDEK_ORDER_TYPE_IM = 1

# Timeouts for requests
REQUEST_TIMEOUT_SECONDS = 30