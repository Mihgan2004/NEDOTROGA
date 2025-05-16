 # -*- coding: utf-8 -*-
import json
import logging
from odoo import http, _
from odoo.http import request
from odoo.osv import expression

_logger = logging.getLogger(__name__)

class CDEKController(http.Controller):
    """HTTP Controller for CDEK integration endpoints"""

    def _get_cdek_client(self):
        """Retrieve CDEK API client configured in system settings."""
        return request.env['res.config.settings']._get_cdek_client()

    @http.route('/cdek/pvz/search', type='json', auth='user', methods=['POST'], csrf=False)
    def search_pvz(self, city_name=None, search_text=None, limit=50, **kwargs):
        """
        Search for CDEK PVZ points for map display.
        :param city_name: Name of the city to restrict search
        :param search_text: Text to filter PVZ name, code, or address
        :param limit: Max number of points to return
        """
        client = self._get_cdek_client()
        if not client:
            return {'error': _('CDEK client is not configured.')}

        domain = [('active', '=', True)]
        if city_name:
            domain.append(('city_name', 'ilike', city_name))
        if search_text:
            # Filter by name, code, or address
            term_filters = [
                [('name', 'ilike', search_text)],
                [('code', 'ilike', search_text)],
                [('address_full', 'ilike', search_text)],
            ]
            domain = expression.OR(term_filters, domain)

        try:
            limit = int(limit) if limit else 50
        except (TypeError, ValueError):
            limit = 50

        pvz_records = request.env['cdek.pvz'].search(domain, limit=limit)
        result = []
        for pvz in pvz_records:
            if not (pvz.latitude and pvz.longitude):
                continue
            result.append({
                'id': pvz.id,
                'name': pvz.name,
                'code': pvz.code,
                'address': pvz.address_full,
                'latitude': pvz.latitude,
                'longitude': pvz.longitude,
                'city_code': pvz.city_code,
                'work_schedule': pvz.work_schedule,
            })
        _logger.info("CDEK PVZ search returned %d records for city=%s, text=%s", len(result), city_name, search_text)
        return result

    @http.route('/cdek/geocode/city', type='json', auth='user', methods=['POST'], csrf=False)
    def geocode_city(self, city_name, country_code='RU', **kwargs):
        """
        Geocode a city name via CDEK API to retrieve city code and coordinates.
        :param city_name: City name to geocode
        :param country_code: ISO country code (default 'RU')
        """
        client = self._get_cdek_client()
        if not client:
            return {'error': _('CDEK client is not configured.'), 'city_data': None}

        try:
            params = {
                'country_codes': [country_code.upper()],
                'q': city_name,
                'size': 1,
            }
            cities = client.get_cities(params=params)
            if not cities or not isinstance(cities, list):
                _logger.warning("CDEK geocode: no data for city %s", city_name)
                return {'error': _('City "%s" not found.') % city_name, 'city_data': None}
            city = cities[0]
            return {
                'city_data': {
                    'code': city.get('code'),
                    'city_name': city.get('city'),
                    'region': city.get('region'),
                    'country_code': city.get('country_code'),
                    'latitude': city.get('latitude'),
                    'longitude': city.get('longitude'),
                }
            }
        except Exception as e:
            _logger.error("Error geocoding city %s: %s", city_name, e, exc_info=True)
            return {'error': str(e), 'city_data': None}
