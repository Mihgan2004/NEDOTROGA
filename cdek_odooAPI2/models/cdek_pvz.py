# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class CdekPVZ(models.Model):
    _name = 'cdek.pvz'
    _description = 'CDEK Pickup Point (PVZ)'
    _order = 'city_name, name'

    name = fields.Char(string='PVZ Name', required=True, index=True)
    code = fields.Char(string='PVZ Code (CDEK)', required=True, index=True, help="Unique CDEK code for this pickup point.")
    
    type = fields.Selection([
        ('PVZ', 'Пункт выдачи заказа'),
        ('POSTAMAT', 'Постамат'),
        ('ALL', 'Все типы'), # For filtering, not usually a PVZ type itself
        ('TERMINAL', 'Терминал'), # Check CDEK docs for current types
        ], string='Type', default='PVZ', index=True)
    
    work_time = fields.Char(string='Work Hours')
    address_full = fields.Text(string='Full Address', help="Formatted full address of the PVZ.")
    address_comment = fields.Text(string='Address Comment / How to find')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    note = fields.Text(string='Note / Description')

    city_name = fields.Char(string='City Name', index=True)
    city_code = fields.Char(string='City Code (CDEK)', index=True, help="Numeric CDEK code for the city.") # CDEK uses numeric city codes
    region_name = fields.Char(string='Region Name')
    country_code = fields.Char(string='Country Code', default='RU') # e.g., RU, KZ, BY

    longitude = fields.Float(string='Longitude', digits=(10, 7)) # CDEK provides this precision
    latitude = fields.Float(string='Latitude', digits=(10, 7))

    # Capabilities (from CDEK API)
    is_cash_on_delivery = fields.Boolean(string='Cash on Delivery (COD) Available')
    is_card_payment = fields.Boolean(string='Card Payment Available')
    is_dressing_room = fields.Boolean(string='Dressing Room Available')
    is_partial_delivery = fields.Boolean(string='Partial Delivery Available')

    max_weight_allowed_kg = fields.Float(string='Max Weight (kg)', help="Maximum weight allowed at this PVZ.")
    # Dimensions limits (L, W, H in cm)
    max_length_cm = fields.Integer(string='Max Length (cm)')
    max_width_cm = fields.Integer(string='Max Width (cm)')
    max_height_cm = fields.Integer(string='Max Height (cm)')

    owner_code = fields.Char(string='Owner Code', help="Franchise or CDEK's own.") # e.g. CDEK, INPOST
    
    active = fields.Boolean(default=True, index=True)
    last_updated_cdek = fields.Datetime(string="Last Updated from CDEK", readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)


    _sql_constraints = [
        ('code_uniq', 'unique (code, company_id)', 'CDEK PVZ Code must be unique per company!')
    ]

    def name_get(self):
        result = []
        for record in self:
            name = f"[{record.code}] {record.name} ({record.city_name or _('Unknown City')})"
            result.append((record.id, name))
        return result

    @api.model
    def _format_pvz_data_from_cdek(self, cdek_pvz_data):
        """
        Maps raw CDEK API data for a single PVZ to Odoo model fields.
        :param cdek_pvz_data: dict from CDEK API /deliverypoints response
        :return: dict of values for Odoo model
        """
        location = cdek_pvz_data.get('location', {})
        vals = {
            'code': cdek_pvz_data.get('code'),
            'name': cdek_pvz_data.get('name'),
            'type': cdek_pvz_data.get('type'), # Ensure this matches your selection field
            'work_time': cdek_pvz_data.get('work_time'),
            'address_full': location.get('address_full') or location.get('address'),
            'address_comment': location.get('address_comment'),
            'phone': cdek_pvz_data.get('phones', [{}])[0].get('number') if cdek_pvz_data.get('phones') else None,
            'email': cdek_pvz_data.get('email'),
            'note': cdek_pvz_data.get('note'),
            'city_name': location.get('city'),
            'city_code': str(location.get('city_code')) if location.get('city_code') else None, # CDEK city code
            'region_name': location.get('region'),
            'country_code': location.get('country_code'),
            'longitude': location.get('longitude'),
            'latitude': location.get('latitude'),
            'is_cash_on_delivery': cdek_pvz_data.get('is_cash_on_delivery', False) or any(p.get('type') == 'CASH' for p in cdek_pvz_data.get('payment_methods', [])),
            'is_card_payment': any(p.get('type') == 'CARD' for p in cdek_pvz_data.get('payment_methods', [])),
            'is_dressing_room': any(s.get('type') == 'FITTING_ROOM' for s in cdek_pvz_data.get('services', [])),
            'is_partial_delivery': any(s.get('type') == 'PART_DELIVERY' for s in cdek_pvz_data.get('services', [])),
            'owner_code': cdek_pvz_data.get('owner_code'),
            'active': True, # Assume active if returned by API, or check 'is_reception_available'
            'last_updated_cdek': fields.Datetime.now(),
        }
        # Dimensions/Weight Limits (these might be nested or named differently in API)
        # Example: cdek_pvz_data.get('dimensions', [{}])[0].get('weight_max')
        # For now, placeholders for where to map these:
        # vals['max_weight_allowed_kg'] = cdek_pvz_data.get('max_shipment_weight')
        # vals['max_length_cm'] = cdek_pvz_data.get('max_length')
        # ... etc. Check CDEK /deliverypoints response structure carefully for these.

        return vals

    @api.model
    def cron_update_cdek_pvz_list(self, country_codes=None, city_codes=None):
        """
        Scheduled action to update the list of CDEK PVZs.
        Can be filtered by country or specific city codes if needed.
        """
        _logger.info("CRON: Starting CDEK PVZ list update.")
        client = self.env['res.config.settings']._get_cdek_client()
        if not client:
            _logger.error("CRON: CDEK PVZ update failed. Client could not be initialized.")
            return

        params = {'type': 'ALL'} # Get all types by default: PVZ and POSTAMAT
        if country_codes: # e.g. ['RU', 'KZ']
            params['country_code'] = country_codes
        if city_codes: # e.g. [44, 270] CDEK numeric city codes
            params['city_code'] = city_codes # This might need to be called per city if API doesn't take list

        try:
            all_cdek_pvz_data = client.get_delivery_points(params=params)
            if not all_cdek_pvz_data:
                _logger.info("CRON: No PVZ data returned from CDEK API with params %s.", params)
                return

            updated_count = 0
            created_count = 0
            processed_codes = []

            for pvz_data in all_cdek_pvz_data:
                code = pvz_data.get('code')
                if not code:
                    _logger.warning("CRON: Skipping PVZ data with no code: %s", pvz_data.get('name'))
                    continue
                
                processed_codes.append(code)
                vals = self._format_pvz_data_from_cdek(pvz_data)
                existing_pvz = self.search([('code', '=', code)], limit=1)

                if existing_pvz:
                    existing_pvz.write(vals)
                    updated_count += 1
                else:
                    self.create(vals)
                    created_count += 1
            
            # Deactivate PVZs not present in the latest CDEK update (for the given filter)
            # This is only safe if cron job fetches ALL PVZs for a region/country it's responsible for.
            # If filtered (e.g. by city_codes), this deactivation logic is risky.
            if not city_codes: # Only deactivate if we fetched for all (or by country)
                pvz_to_deactivate = self.search([
                    ('code', 'not in', processed_codes),
                    ('active', '=', True),
                    # Add country filter if 'country_codes' param was used
                    ('country_code', 'in', country_codes if country_codes else ['RU']) # Example
                ])
                if pvz_to_deactivate:
                    pvz_to_deactivate.write({'active': False})
                    _logger.info("CRON: Deactivated %d CDEK PVZs not in the latest API response.", len(pvz_to_deactivate))


            _logger.info("CRON: CDEK PVZ list update finished. Created: %d, Updated: %d.", created_count, updated_count)

        except UserError as e:
            _logger.error("CRON: UserError during CDEK PVZ update: %s", e)
        except Exception as e:
            _logger.error("CRON: Exception during CDEK PVZ update: %s", e, exc_info=True)