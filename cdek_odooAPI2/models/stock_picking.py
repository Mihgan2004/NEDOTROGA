# -*- coding: utf-8 -*-
import base64
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Renamed for clarity to avoid conflict with standard carrier_tracking_ref if it's used differently
    cdek_order_uuid = fields.Char(
        string='CDEK Order UUID',
        copy=False,
        readonly=True,
        help="Unique identifier for the order registered with CDEK."
    )
    cdek_tracking_state_code = fields.Char(
        string='CDEK Status Code',
        copy=False,
        readonly=True,
        help="Latest CDEK status code for this shipment."
    )
    cdek_tracking_state_name = fields.Char(
        string='CDEK Status Name',
        copy=False,
        readonly=True,
        help="Latest CDEK status name for this shipment."
    )
    cdek_tracking_state_datetime = fields.Datetime(
        string='CDEK Status Date',
        copy=False,
        readonly=True,
        help="Timestamp of the latest CDEK status."
    )
    cdek_tracking_history_log = fields.Text(
        string='CDEK Tracking History',
        copy=False,
        readonly=True,
        help="Full log of CDEK tracking status updates."
    )

    def _get_cdek_client_for_picking(self):
        """Helper to get CDEK client, ensuring carrier is CDEK."""
        self.ensure_one()
        if not self.carrier_id or self.carrier_id.delivery_type != 'cdek':
            # This method should only be called if it's a CDEK picking.
            # If called otherwise, it's a logic error in the calling code.
            _logger.warning("Attempted to get CDEK client for non-CDEK picking %s", self.name)
            return None # Or raise error

        # Use the carrier's helper to get a client instance with its logging capabilities
        return self.carrier_id._get_cdek_client()


    def cdek_update_tracking_state(self):
        """Updates CDEK tracking status for selected pickings."""
        updated_pickings = self.env['stock.picking']
        for picking in self.filtered(lambda p: p.carrier_id.delivery_type == 'cdek' and (p.carrier_tracking_ref or p.cdek_order_uuid) and p.state not in ('done', 'cancel')):
            client = picking._get_cdek_client_for_picking()
            if not client:
                picking.message_post(body=_("CDEK tracking update failed: Client could not be initialized. Check CDEK configuration."))
                continue

            tracking_uuid = picking.carrier_tracking_ref or picking.cdek_order_uuid
            try:
                _logger.info("CDEK Tracking Update: Fetching status for picking %s (UUID: %s)", picking.name, tracking_uuid)
                order_info = client.get_order_info(tracking_uuid)
                _logger.info("CDEK Tracking Update for %s: Response %s", picking.name, order_info)

                if not order_info or 'statuses' not in order_info or not order_info['statuses']:
                    picking.message_post(body=_("CDEK Tracking: No status information found for UUID %s.") % tracking_uuid)
                    continue

                statuses = sorted(order_info['statuses'], key=lambda s: s['date_time'], reverse=True)
                latest_status = statuses[0] # Most recent status

                history_lines = []
                for status in sorted(order_info['statuses'], key=lambda s: s['date_time']): # Chronological for log
                    history_lines.append(
                        f"{status.get('date_time')} - [{status.get('code')}] {status.get('name')}"
                        f"{(' (' + status.get('city') + ')') if status.get('city') else ''}"
                    )

                picking.write({
                    'cdek_tracking_state_code': latest_status.get('code'),
                    'cdek_tracking_state_name': latest_status.get('name'),
                    'cdek_tracking_state_datetime': fields.Datetime.from_string(latest_status.get('date_time')),
                    'cdek_tracking_history_log': "\n".join(history_lines),
                    # Potentially update Odoo's standard delivery state if mapping is defined
                    # 'delivery_state': self._map_cdek_status_to_odoo_state(latest_status.get('code')),
                })
                picking.message_post(body=_("CDEK tracking status updated: [%s] %s at %s") % (
                    latest_status.get('code'), latest_status.get('name'), latest_status.get('date_time')
                ))
                updated_pickings |= picking

            except UserError as e:
                _logger.error("CDEK Tracking Update UserError for %s: %s", picking.name, e)
                picking.message_post(body=_("CDEK Tracking Error: %s") % str(e))
            except Exception as e:
                _logger.error("CDEK Tracking Update Exception for %s: %s", picking.name, e, exc_info=True)
                picking.message_post(body=_("Unexpected error during CDEK tracking update for %s: %s") % (picking.name, str(e)))
        return updated_pickings


    def cdek_action_get_label(self):
        """Action to download and attach CDEK shipping label."""
        self.ensure_one()
        if not self.carrier_id or self.carrier_id.delivery_type != 'cdek':
            raise UserError(_("This picking is not configured for CDEK delivery."))

        tracking_uuid = self.carrier_tracking_ref or self.cdek_order_uuid
        if not tracking_uuid:
            raise UserError(_("CDEK Order UUID or Tracking Reference is missing for this picking."))

        client = self._get_cdek_client_for_picking()
        if not client:
            raise UserError(_("CDEK label download failed: Client could not be initialized. Check CDEK configuration."))

        label_format = self.carrier_id._cdek_get_label_format() # Get format from carrier or global config

        try:
            _logger.info("CDEK Get Label: Requesting %s label for picking %s (UUID: %s)", label_format.upper(), self.name, tracking_uuid)
            label_data = client.get_label_data(tracking_uuid, label_format=label_format)

            if not label_data:
                raise UserError(_("CDEK did not return any label data for UUID %s.") % tracking_uuid)

            filename = f"cdek_label_{tracking_uuid}_{self.name.replace('/', '_')}.{label_format}"
            attachment_vals = {
                'name': filename,
                'datas': base64.b64encode(label_data),
                'res_model': 'stock.picking',
                'res_id': self.id,
                'mimetype': 'application/pdf' if label_format == 'pdf' else 'text/plain', # Adjust mimetype for ZPL if needed
            }
            self.env['ir.attachment'].create(attachment_vals)
            self.message_post(body=_("CDEK shipping label (%s) downloaded.") % label_format.upper(), attachments=[(filename, label_data)])
            _logger.info("CDEK Get Label: Successfully attached %s label for picking %s.", label_format.upper(), self.name)

            # Optional: Return an action to download the label directly
            # return {
            #     'type': 'ir.actions.act_url',
            #     'url': f'/web/content/{attachment.id}?download=true', # If attachment is created and ID known
            #     'target': 'self',
            # }

        except UserError as e:
            _logger.error("CDEK Get Label UserError for %s: %s", self.name, e)
            raise # Re-raise UserError to display to user
        except Exception as e:
            _logger.error("CDEK Get Label Exception for %s: %s", self.name, e, exc_info=True)
            raise UserError(_("An unexpected error occurred while getting CDEK label for %s: %s") % (self.name, str(e)))


    def action_cdek_send_shipping(self):
        """Button action to send selected pickings to CDEK."""
        pickings_to_send = self.filtered(lambda p: p.carrier_id.delivery_type == 'cdek' and \
                                                  not p.carrier_tracking_ref and \
                                                  p.state not in ('done', 'cancel', 'draft'))
        if not pickings_to_send:
            raise UserError(_("No CDEK pickings found that are ready to be sent (or they might already have a tracking number)."))

        # Group pickings by carrier if multiple CDEK carriers are configured differently (though settings are global)
        # For simplicity, assuming one 'cdek_send_shipping' call can handle pickings for the same carrier config
        # If carrier_id can vary with different CDEK tariff codes, group by carrier_id
        for carrier in pickings_to_send.mapped('carrier_id'):
            carrier_pickings = pickings_to_send.filtered(lambda p: p.carrier_id == carrier)
            if carrier_pickings:
                carrier.cdek_send_shipping(carrier_pickings)
        return True