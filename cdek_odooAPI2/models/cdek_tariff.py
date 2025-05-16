# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class CdekTariff(models.Model):
    _name = 'cdek.tariff'
    _description = 'CDEK Tariff Information'
    _order = 'code'

    code = fields.Integer(string='Tariff Code (CDEK)', required=True, index=True, help="Unique numeric CDEK code for this tariff.")
    name = fields.Char(string='Tariff Name', required=True, index=True)
    description = fields.Text(string='Description')
    
    # Tariff type based on CDEK's classification (e.g., door-door, warehouse-door)
    # CDEK API /calculator/tariff list does not directly provide these types.
    # This might need manual categorization or parsing from description.
    # type = fields.Selection([
    #     ('DD', 'Door-Door'), ('DW', 'Door-Warehouse'),
    #     ('WD', 'Warehouse-Door'), ('WW', 'Warehouse-Warehouse')
    # ], string="Tariff Type")

    delivery_mode_code = fields.Integer(string="Delivery Mode Code", help="CDEK's internal delivery_mode (e.g., 1 for door-door, 2 for door-PVZ, etc.)")
    delivery_mode_name = fields.Char(compute='_compute_delivery_mode_name')


    active = fields.Boolean(default=True, index=True)
    last_updated_cdek = fields.Datetime(string="Last Updated from CDEK", readonly=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('code_uniq', 'unique (code, company_id)', 'CDEK Tariff Code must be unique per company!')
    ]

    @api.depends('delivery_mode_code')
    def _compute_delivery_mode_name(self):
        # CDEK Delivery Modes (from API docs for Orders endpoint)
        # 1 - склад-склад; 2 - склад-дверь; 3 - дверь-склад; 4 - дверь-дверь;
        # 6 - дверь-постамат; 7 - склад-постамат;
        mode_map = {
            1: _("Warehouse-Warehouse"), 2: _("Warehouse-Door"),
            3: _("Door-Warehouse"), 4: _("Door-Door"),
            6: _("Door-Postamat"), 7: _("Warehouse-Postamat"),
        }
        for record in self:
            record.delivery_mode_name = mode_map.get(record.delivery_mode_code, _("Unknown"))


    @api.model
    def _format_tariff_data_from_cdek(self, cdek_tariff_data):
        """
        Maps raw CDEK API data for a single tariff to Odoo model fields.
        :param cdek_tariff_data: dict from CDEK API (e.g. from a future /tariffs endpoint or manual entry)
        :return: dict of values for Odoo model
        """
        # CDEK API for listing tariffs isn't as straightforward as PVZs.
        # Tariffs are usually known by their codes.
        # This method is a placeholder if such an API endpoint becomes available.
        # For now, tariffs might be manually created or based on a fixed list.
        vals = {
            'code': cdek_tariff_data.get('tariff_code'), # Ensure key matches API
            'name': cdek_tariff_data.get('tariff_name'),
            'description': cdek_tariff_data.get('tariff_description'),
            'delivery_mode_code': cdek_tariff_data.get('delivery_mode'), # delivery_mode is on order, not tariff list
            'active': True,
            'last_updated_cdek': fields.Datetime.now(),
        }
        return vals

    @api.model
    def cron_update_cdek_tariffs(self):
        """
        Scheduled action to update the list of CDEK Tariffs.
        NOTE: CDEK API v2 does not have a simple public endpoint to list all available tariffs like /deliverypoints.
        Tariff codes are generally documented or known. This method is a placeholder
        or could be adapted if a partner-specific tariff listing API is available.
        """
        _logger.info("CRON: Starting CDEK Tariff list update (Placeholder - No direct CDEK API for this).")
        # client = self.env['res.config.settings']._get_cdek_client()
        # if not client:
        #     _logger.error("CRON: CDEK Tariff update failed. Client could not be initialized.")
        #     return
        #
        # try:
        #     # Hypothetical call: cdek_tariffs_data = client.get_available_tariffs()
        #     # For now, this would likely involve updating from a predefined list or manual entries.
        #     # Example:
        #     # predefined_tariffs = [
        #     #    {'tariff_code': 136, 'tariff_name': 'Посылка склад-дверь', ...},
        #     #    {'tariff_code': 233, 'tariff_name': 'Экономичная посылка склад-склад', ...}
        #     # ]
        #     # for tariff_data in predefined_tariffs:
        #     #     vals = self._format_tariff_data_from_cdek(tariff_data)
        #     #     # ... create or update logic ...
        #
        #     _logger.info("CRON: CDEK Tariff list update finished (Manual/Placeholder).")
        #
        # except UserError as e:
        #     _logger.error("CRON: UserError during CDEK Tariff update: %s", e)
        # except Exception as e:
        #     _logger.error("CRON: Exception during CDEK Tariff update: %s", e, exc_info=True)
        pass