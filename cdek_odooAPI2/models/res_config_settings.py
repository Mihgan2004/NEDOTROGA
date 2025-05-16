from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.cdek_odooAPI2.services.cdek_request import CdekRequest

from ..const import CDEK_LABEL_FORMATS, DEFAULT_LENGTH_CM, DEFAULT_WIDTH_CM, DEFAULT_HEIGHT_CM, DEFAULT_WEIGHT_KG

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # CDEK API Credentials and Mode
    cdek_client_id = fields.Char(
        string="CDEK Client ID",
        config_parameter='cdek.client_id'
    )
    cdek_client_secret = fields.Char(
        string="CDEK Client Secret",
        config_parameter='cdek.client_secret',
        help="Ensure this is stored securely."
    )
    cdek_test_mode = fields.Boolean(
        string="CDEK Test Mode",
        config_parameter='cdek.test_mode',
        default=True,
        help="Use CDEK test (sandbox) environment."
    )
    # Optional CDEK Account Identifiers (if needed in payloads)
    cdek_account = fields.Char(
        string="CDEK Account (Number)",
        config_parameter='cdek.account',
        help="Your CDEK account number, if required for specific API calls or payload fields."
    )
    cdek_secure_password = fields.Char(
        string="CDEK Secure Password (for account)",
        config_parameter='cdek.secure_password',
        help="Secure password associated with your CDEK account, if required."
    )


    # Default Settings for Shipments
    cdek_default_label_format = fields.Selection(
        CDEK_LABEL_FORMATS,
        string='Default Label Format',
        config_parameter='cdek.default_label_format',
        default='pdf',
        required=True
    )
    cdek_default_sender_city_code = fields.Char(
        string="Default Sender City Code (CDEK)",
        config_parameter='cdek.default_sender_city_code',
        help="Numeric CDEK code for the default sender city (e.g., Moscow is 44)."
    )
    cdek_default_sender_postcode = fields.Char(
        string="Default Sender Postal Code",
        config_parameter='cdek.default_sender_postcode'
    )
    # Default package dimensions - ensure units are clear (CM for CDEK API)
    cdek_default_length_cm = fields.Float(
        string='Default Package Length (cm)',
        config_parameter='cdek.default_length_cm',
        default=DEFAULT_LENGTH_CM,
        digits='Stock Weight' # Using a common precision
    )
    cdek_default_width_cm = fields.Float(
        string='Default Package Width (cm)',
        config_parameter='cdek.default_width_cm',
        default=DEFAULT_WIDTH_CM,
        digits='Stock Weight'
    )
    cdek_default_height_cm = fields.Float(
        string='Default Package Height (cm)',
        config_parameter='cdek.default_height_cm',
        default=DEFAULT_HEIGHT_CM,
        digits='Stock Weight'
    )
    cdek_default_weight_kg = fields.Float( # Store in KG, convert to Grams for API
        string='Default Package Weight (kg)',
        config_parameter='cdek.default_weight_kg',
        default=DEFAULT_WEIGHT_KG,
        digits='Stock Weight'
    )

    # Tracking Settings
    cdek_tracking_update_interval_minutes = fields.Integer(
        string='Tracking Update Interval (minutes)',
        config_parameter='cdek.tracking_update_interval_minutes',
        default=60,
        help="How often to automatically check CDEK shipment statuses. 0 to disable."
    )

    # Utility method to get an initialized CdekRequest client
    @api.model
    def _get_cdek_client(self, carrier=None):
        """
        Helper to get an instance of CdekRequest with current global settings.
        :param carrier: Optional delivery.carrier record. If provided, its log_xml method can be used for debugging.
        :return: CdekRequest instance
        """
        params = self.env['ir.config_parameter'].sudo()
        client_id = params.get_param('cdek.client_id')
        client_secret = params.get_param('cdek.client_secret')
        test_mode = params.get_param('cdek.test_mode', 'False').lower() in ('true', '1') # Ensure boolean

        from ..const import CDEK_API_PROD_URL, CDEK_API_TEST_URL # Avoid circular import at top level
        base_url = CDEK_API_TEST_URL if test_mode else CDEK_API_PROD_URL

        if not client_id or not client_secret:
            # Check if being called from a context where settings might not be saved yet (e.g. during config save)
            # In such cases, it might be okay to return None or raise a less severe warning
            # For general use, this is an error.
            if self.env.context.get('saving_config'):
                 _logger.warning("CDEK client cannot be initialized: API credentials not yet saved or missing.")
                 return None # Or handle as appropriate for the caller
            raise UserError(_("CDEK API Client ID or Secret is not configured in settings."))

        debug_logger = None
        if carrier and hasattr(carrier, 'log_xml') and carrier.debug_logging:
            debug_logger = lambda message, name: carrier.log_xml(message, name)

        return CdekRequest(client_id, client_secret, base_url, debug_logger=debug_logger)