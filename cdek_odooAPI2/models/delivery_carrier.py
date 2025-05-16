# -*- coding: utf-8 -*-
"""
CDEK delivery carrier for Odoo 18 – full production version.

Key design points
-----------------
* One single entry‑point for the CDEK REST client:  self._get_cdek_client()
  (see res_config_settings.py where the credentials & test mode are stored).
* All user editable parameters live either on the carrier
  (tariff, COD flag, extra days, free‑shipping threshold,
   default length/width/height/weight, shipment PVZ code) or in the
  “Global CDEK settings”.
* Every outward call to CDEK API v2 is wrapped in try/except and always
  returns a dict that **contains the key “price”** – even on failure – so
  Odoo’s website_sale controller never throws KeyError again.

Author: ChatGPT (o3 model)
License: LGPL‑3.0 (same as Odoo “delivery” base module)
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Tuple

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTS (shared with the rest of the module – keep in sync if you move)
# ---------------------------------------------------------------------------
CDEK_IM_TYPE = 1  # “интернет‑магазин”
CDEK_DELIVERY_TYPE = 2  # “доставка”
DEFAULT_TARIFF = 136  # “Посылка склад‑дверь”
DEFAULT_LEN = 10
DEFAULT_WID = 10
DEFAULT_HEI = 10
DEFAULT_WGT_KG = 0.1
CDEK_LABEL_FORMATS = [
    ('pdf',  'PDF (А4)'),
    ('zpl',  'ZPL (термопринтер)'),
]


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    # ---------------------------------------------------------------------
    # FIELDS – minimal but sufficient for Russian on‑line T‑shirt shop
    # ---------------------------------------------------------------------
    delivery_type = fields.Selection(
        selection_add=[("cdek", "CDEK")],
        ondelete={"cdek": "set default"},
    )

    # --- CDEK specific ----------------------------------------------------
    cdek_tariff_code = fields.Integer(
        string="CDEK tariff code",
        default=DEFAULT_TARIFF,
        help="Любой тариф из справочника CDEK API v2. Например 136 – «Посылка склад‑дверь».",
    )
    cdek_order_type = fields.Selection(
        [("1", "Интернет‑магазин"), ("2", "Доставка")],
        string="CDEK order type",
        default=str(CDEK_IM_TYPE),
        required=True,
    )
    cdek_shipment_point_code = fields.Char(
        string="CDEK PVZ code (отправление)",
        help="Если вы лично сдаёте заказы в ПВЗ (тарифы «от склада»).",
    )
    cdek_allow_cod = fields.Boolean(
        string="Enable COD (наложенный платёж)",
        default=False,
    )
    cdek_extra_days = fields.Integer(
        string="Доп. дни обработки",
        default=0,
        help="Сколько дней добавить к сроку доставки, показываемому покупателю.",
    )
    cdek_free_threshold = fields.Monetary(
        string="Бесплатно от (сумма заказа)",
        help="Если сумма заказа (без доставки) >= этого значения, доставка бесплатна.",
        currency_field="company_currency_id",
    )

    cdek_label_format_override = fields.Selection(
        CDEK_LABEL_FORMATS,
        string=_("Label format override"),
        help=_(
            "If set, this format will be used instead of the global default "
            "when you print CDEK labels for this carrier."
        ),
    )

    cdek_add_days = fields.Integer(
        string=_("Additional Delivery Days"),
        default=0,
        help=_("Add this many days to the delivery time returned by CDEK API."),
    )

    cdek_allow_cod = fields.Boolean(
        string="Allow Cash on Delivery (COD)",
        default=False,
        help="Enable Cash on Delivery for this carrier."
    )
    cdek_free_shipping_threshold = fields.Monetary(
        string="Free Shipping Threshold",
        currency_field="currency_id",
        help="If order total (untaxed) ≥ this amount, shipping is free."
    )


    # Defaults for parcels (cms / kg)
    default_length_cm = fields.Integer(default=DEFAULT_LEN)
    default_width_cm = fields.Integer(default=DEFAULT_WID)
    default_height_cm = fields.Integer(default=DEFAULT_HEI)
    default_weight_kg = fields.Float(default=DEFAULT_WGT_KG)

    # Helper – company currency on carrier form
    company_currency_id = fields.Many2one(
        related="company_id.currency_id", readonly=True
    )

    # ---------------------------------------------------------------------
    # CONSTRAINTS
    # ---------------------------------------------------------------------
    @api.constrains("delivery_type", "cdek_tariff_code")
    def _check_mandatory_cdek(self) -> None:
        for record in self:
            if record.delivery_type == "cdek" and not record.cdek_tariff_code:
                raise ValidationError(_("Tariff code is required for CDEK carriers."))

    # ---------------------------------------------------------------------
    # INTERNAL HELPERS
    # ---------------------------------------------------------------------
    def _get_cdek_client(self):
        """Return a configured instance of `CdekRequest` (wrapper)."""
        self.ensure_one()
        client = self.env["res.config.settings"].sudo()._get_cdek_client()
        if not client:
            raise UserError(_("CDEK API credentials are not configured."))
        return client

    # ---------------------------------------------------------------------
    # PUBLIC API expected by Odoo “delivery” base module
    # ---------------------------------------------------------------------
    # 1. Rate shipment -----------------------------------------------------
    def cdek_rate_shipment(self, order):
        """Website & backend price quote."""
        self.ensure_one()
        _logger.info("CDEK rating for SaleOrder %s via carrier %s", order.name, self.name)

        # Free shipping rule
        if self.cdek_free_threshold and order.amount_untaxed >= self.cdek_free_threshold:
            return dict(success=True, price=0.0, error_message=False, warning_message=False)

        # Build calculator payload
        try:
            payload = self._build_calc_payload(order)
        except UserError as err:
            return self._rate_error(str(err))

        client = self._get_cdek_client()
        try:
            resp = client.calculate_tariff(payload)
            _logger.debug("CDEK calculator OK: %s", resp)
        except UserError as err:
            return self._rate_error(str(err))

        # Parse
        price = float(resp.get("total_sum", 0.0))
        dmin = resp.get("period_min") or 0
        dmax = resp.get("period_max") or 0
        delivery_time = _("%s‑%s дн.") % (dmin, dmax) if dmin and dmax else ""
        if self.cdek_extra_days:
            delivery_time += _(" +%d дн. обработка") % self.cdek_extra_days

        return dict(
            success=True,
            price=price,
            error_message=False,
            warning_message=False,
            delivery_time=delivery_time,
        )

    # 2. Send shipping -----------------------------------------------------
    def cdek_send_shipping(self, pickings):
        """Register orders in CDEK."""
        self.ensure_one()
        client = self._get_cdek_client()
        results = []
        for picking in pickings:
            try:
                payload = self._build_order_payload(picking)
                resp = client.create_order(payload)
                uuid_val = resp["uuid"]
                picking.write(
                    {
                        "carrier_tracking_ref": uuid_val,
                        "cdek_order_uuid": uuid_val,
                    }
                )
                results.append(
                    dict(
                        exact_price=picking.carrier_price or 0.0,
                        tracking_number=uuid_val,
                    )
                )
            except Exception as e:
                _logger.exception("CDEK send failed for %s", picking.name)
                picking.message_post(body=str(e))
                results.append(dict(error_message=str(e), exact_price=0.0))
        return results

    # 3. Tracking link -----------------------------------------------------
    def cdek_get_tracking_link(self, picking):
        return f"https://cdek.ru/tracking?order_id={picking.carrier_tracking_ref}"

    # ---------------------------------------------------------------------
    # BUILD PAYLOADS
    # ---------------------------------------------------------------------
    # -- calculator --------------------------------------------------------
    def _build_calc_payload(self, order) -> Dict[str, Any]:
        """Return dict for /calculator/tariff request."""
        sender = order.warehouse_id.partner_id or self.env.company.partner_id
        recipient = order.partner_shipping_id

        from_loc = self._partner_to_location(sender, allow_code_or_zip=True)
        to_loc = self._partner_to_location(recipient)

        pkg_list, _ = self._packages_from_so(order)

        return {
            "type": int(self.cdek_order_type),
            "tariff_code": self.cdek_tariff_code,
            "from_location": from_loc,
            "to_location": to_loc,
            "packages": pkg_list,
        }

    # -- order creation ----------------------------------------------------
    def _build_order_payload(self, picking) -> Dict[str, Any]:
        """Return dict for /orders."""
        sale = picking.sale_id
        if not sale:
            raise UserError(_("Picking %s is not linked to a sale order.") % picking.name)

        recipient = self._contact_block(sale.partner_shipping_id, for_order=True)
        sender_partner = picking.picking_type_id.warehouse_id.partner_id or self.env.company.partner_id
        sender_block = self._contact_block(sender_partner, is_sender=True, for_order=True)

        location_from = (
            {"code": int(self.cdek_shipment_point_code)}
            if self.cdek_shipment_point_code
            else self._partner_to_location(sender_partner, allow_code_or_zip=True)
        )
        location_to = (
            {"code": int(sale.cdek_pvz_id.code)}
            if sale.cdek_pvz_id
            else self._partner_to_location(sale.partner_shipping_id)
        )

        packages, total_cod = self._packages_from_picking(picking)

        payload = {
            "uuid": str(uuid.uuid4()),
            "type": int(self.cdek_order_type),
            "number": picking.name,
            "tariff_code": self.cdek_tariff_code,
            "recipient": recipient,
            "sender": sender_block,
            "from_location": location_from,
            "to_location": location_to,
            "comment": (sale.note or "")[:255],
            "packages": packages,
            "shipment_date": date.today().isoformat(),
        }

        if self.cdek_allow_cod and total_cod:
            payload["delivery_recipient_cost"] = {"value": float(round(total_cod, 2))}

        return payload

    # ---------------------------------------------------------------------
    # LOW‑LEVEL helpers
    # ---------------------------------------------------------------------
    def _partner_to_location(self, partner, allow_code_or_zip: bool = False) -> Dict[str, Any]:
        """Convert res.partner to CDEK location dto."""
        if partner.country_id.code != "RU":
            raise UserError(_("Only Russian addresses are supported in this demo."))

        loc = {
            "country_code": partner.country_id.code,
            "city": partner.city,
            "address": ", ".join(filter(None, [partner.street, partner.street2])),
        }
        if partner.zip:
            loc["postal_code"] = partner.zip

        # try integer CDEK city code on partner
        if hasattr(partner, "cdek_city_code") and partner.cdek_city_code:
            try:
                loc["code"] = int(partner.cdek_city_code)
            except ValueError:
                _logger.debug("Invalid cdek_city_code %s", partner.cdek_city_code)

        if allow_code_or_zip and not loc.get("code") and not loc.get("postal_code"):
            raise UserError(_("Sender location needs either CDEK city code or postal code."))

        return loc

    def _contact_block(self, partner, is_sender=False, for_order=False) -> Dict[str, Any]:
        """Return dict for ContactDto."""
        name = partner.name or (partner.parent_id.name if partner.parent_id else "")
        phone = re.sub(r"\D", "", partner.mobile or partner.phone or "")
        if for_order and not phone:
            raise UserError(_("Phone is required for %s") % name)
        res = {"name": name[:100]}
        if phone:
            res["phones"] = [{"number": phone}]
        if partner.email:
            res["email"] = partner.email
        if is_sender and partner.is_company:
            res["company"] = name[:100]
        return res

    # -- packages ----------------------------------------------------------
    def _packages_from_so(self, order) -> Tuple[List[Dict[str, Any]], float]:
        total_w = 0
        items = []
        for line in order.order_line.filtered(
            lambda l: not l.display_type and l.product_id.type in ("product", "consu")
        ):
            w_kg = line.product_id.weight or self.default_weight_kg
            w_g = max(int(round(w_kg * 1000)), 10)
            total_w += w_g * int(line.product_uom_qty)
            item = {
                "name": line.product_id.name[:255],
                "ware_key": line.product_id.default_code or str(line.product_id.id),
                "cost": round(line.price_unit * (1 - line.discount / 100), 2),
                "weight": w_g,
                "amount": int(line.product_uom_qty),
            }
            if self.cdek_allow_cod:
                item["payment"] = {"value": item["cost"]}
            items.append(item)

        if not items:
            # at least 1 default item
            items.append(
                {
                    "name": _("T‑shirt"),
                    "ware_key": "DEFAULT",
                    "cost": 0.0,
                    "weight": int(self.default_weight_kg * 1000),
                    "amount": 1,
                }
            )
            total_w = int(self.default_weight_kg * 1000)

        pkg = {
            "number": "1",
            "weight": total_w,
            "length": self.default_length_cm,
            "width": self.default_width_cm,
            "height": self.default_height_cm,
            "items": items,
        }
        total_cod = sum(i.get("cost", 0.0) * i.get("amount", 0) for i in items) if self.cdek_allow_cod else 0
        return [pkg], total_cod

    def _packages_from_picking(self, picking) -> Tuple[List[Dict[str, Any]], float]:
        # reuse sale‑order logic for simplicity (weights already transferred)
        return self._packages_from_so(picking.sale_id)

    # ---------------------------------------------------------------------
    # ERROR HELPER
    # ---------------------------------------------------------------------
    @staticmethod
    def _rate_error(msg: str) -> Dict[str, Any]:
        """Return structure compatible with delivery._get_rate() expectations."""
        return dict(success=False, price=0.0, error_message=msg, warning_message=False)
