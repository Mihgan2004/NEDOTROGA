# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cdek_order_uuid = fields.Char(
        string='CDEK Order UUID',
        copy=False,
        readonly=True,
        help="CDEK Order Identifier, typically populated after shipment registration."
    )
    # CDEK PVZ (Pickup Point) Selection
    # Storing PVZ code is key. Address/name are for display and convenience.
    cdek_pvz_code = fields.Char(
        string='CDEK PVZ Code',
        copy=False,
        help="Code of the selected CDEK Pickup Point (PVZ)."
    )
    cdek_pvz_name = fields.Char(
        string='CDEK PVZ Name',
        compute='_compute_cdek_pvz_details', store=True, readonly=True,
        help="Name of the selected CDEK PVZ."
    )
    cdek_pvz_address_full = fields.Text(
        string='CDEK PVZ Address',
        compute='_compute_cdek_pvz_details', store=True, readonly=True,
        help="Full address of the selected CDEK PVZ."
    )
    # Field to link to your cdek.pvz model, if you populate it
    cdek_pvz_id = fields.Many2one(
        'cdek.pvz', string='Selected CDEK PVZ Record',
        domain="[('active', '=', True)]", # Add more domain based on city if possible
        copy=False,
        help="Link to the locally stored CDEK PVZ record."
    )

    partner_shipping_id_city = fields.Char(
        related='partner_shipping_id.city',
        string='Shipping City',
        readonly=True,
        store=False,
    )
    partner_shipping_id_country_code = fields.Char(
        related='partner_shipping_id.country_id.code',
        string='Shipping Country Code',
        readonly=True,
        store=False,
    )



    @api.depends('cdek_pvz_id')
    def _compute_cdek_pvz_details(self):
        for order in self:
            if order.cdek_pvz_id:
                order.cdek_pvz_name = order.cdek_pvz_id.name
                order.cdek_pvz_address_full = order.cdek_pvz_id.address_full
                if not order.cdek_pvz_code: # Populate code if only m2o was set
                    order.cdek_pvz_code = order.cdek_pvz_id.code
            else:
                order.cdek_pvz_name = False
                order.cdek_pvz_address_full = False
                # Don't clear cdek_pvz_code if it was set manually without a cdek.pvz record

    @api.onchange('cdek_pvz_id')
    def _onchange_cdek_pvz_id(self):
        if self.cdek_pvz_id:
            self.cdek_pvz_code = self.cdek_pvz_id.code
            # Trigger recompute of delivery cost if PVZ selection affects it
            if self.carrier_id and self.carrier_id.delivery_type == 'cdek':
                self.delivery_set = False # Force re-calculation of delivery price
                self.get_delivery_price()
        # If cdek_pvz_id is cleared, cdek_pvz_code might persist if entered manually.
        # Consider if clearing cdek_pvz_id should also clear cdek_pvz_code.

    @api.onchange('partner_shipping_id', 'company_id')
    def onchange_partner_shipping_id_cdek(self):
        # Reset PVZ if shipping address changes, as PVZs are location-specific
        if self.carrier_id and self.carrier_id.delivery_type == 'cdek':
            self.cdek_pvz_id = False
            self.cdek_pvz_code = False
            # Potentially trigger re-computation of delivery methods/costs

    @api.onchange('carrier_id')
    def _onchange_carrier_id_cdek(self):
        # If carrier changes away from CDEK or to a CDEK that doesn't support PVZ, clear PVZ
        if self.carrier_id and self.carrier_id.delivery_type != 'cdek':
            self.cdek_pvz_id = False
            self.cdek_pvz_code = False
        elif not self.carrier_id:
            self.cdek_pvz_id = False
            self.cdek_pvz_code = False


    # Override to create CDEK shipment if configured, or rely on button from stock.picking
    # The original code had direct sending on SO confirm. This can be problematic if picking details change.
    # It's often better to register with CDEK when the picking is validated or via a button.
    # However, if immediate registration is desired:
    # def action_confirm(self):
    #     res = super(SaleOrder, self).action_confirm()
    #     for order in self:
    #         if order.carrier_id and order.carrier_id.delivery_type == 'cdek':
    #             # Ensure pickings are created and in a state to be sent
    #             # This logic might be complex if pickings are not immediately ready
    #             pickings_to_send = order.picking_ids.filtered(
    #                 lambda p: p.state not in ('done', 'cancel') and not p.carrier_tracking_ref
    #             )
    #             if pickings_to_send:
    #                 try:
    #                     order.carrier_id.cdek_send_shipping(pickings_to_send)
    #                     # Propagate UUID back to SO if needed, though it's mainly on picking
    #                     if pickings_to_send[0].cdek_order_uuid:
    #                         order.cdek_order_uuid = pickings_to_send[0].cdek_order_uuid
    #                 except UserError as e:
    #                     order.message_post(body=_("CDEK Shipment Registration Error: %s") % str(e))
    #                 except Exception as e:
    #                     _logger.error("Failed to send CDEK shipment for SO %s on confirm: %s", order.name, e, exc_info=True)
    #                     order.message_post(body=_("Unexpected error during CDEK shipment registration: %s") % str(e))
    #     return res

    def action_view_cdek_tracking(self):
        """Action to open CDEK tracking link for the related shipment."""
        self.ensure_one()
        # Find the relevant picking
        # This assumes one main picking or the first one found. Adjust if multiple CDEK pickings per SO.
        cdek_pickings = self.picking_ids.filtered(lambda p: p.carrier_id.delivery_type == 'cdek' and (p.carrier_tracking_ref or p.cdek_order_uuid))
        if not cdek_pickings:
            raise UserError(_("No CDEK shipment found for this order, or it has no tracking number yet."))

        tracking_link = cdek_pickings[0].carrier_id.cdek_get_tracking_link(cdek_pickings[0])
        if not tracking_link:
            raise UserError(_("Could not generate CDEK tracking link."))

        return {
            'type': 'ir.actions.act_url',
            'url': tracking_link,
            'target': 'new',
        }