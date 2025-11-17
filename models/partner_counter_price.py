# -*- coding: utf-8 -*-
"""
Precios de Contadores por Cliente
Permite configurar precios personalizados para cada tipo de contador por cliente
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PartnerCounterPrice(models.Model):
    _name = 'partner.counter.price'
    _description = 'Precio de Contador por Cliente'
    _rec_name = 'display_name'
    _order = 'partner_id, counter_type_id'

    # Relaciones
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        ondelete='cascade',
        index=True
    )
    counter_type_id = fields.Many2one(
        'counter.type',
        string='Tipo de Contador',
        required=True,
        index=True
    )

    # Precio
    unit_price = fields.Float(
        string='Precio Unitario',
        required=True,
        default=0.0,
        help='Precio por página para este tipo de contador'
    )

    # Campos relacionados para búsqueda/display
    counter_name = fields.Char(
        string='Nombre del Contador',
        related='counter_type_id.name',
        readonly=True
    )
    counter_code = fields.Char(
        string='Código',
        related='counter_type_id.code',
        readonly=True
    )
    counter_oid = fields.Char(
        string='OID',
        related='counter_type_id.oid',
        readonly=True
    )
    partner_name = fields.Char(
        string='Cliente',
        related='partner_id.name',
        readonly=True
    )

    # Display name computado
    display_name = fields.Char(
        compute='_compute_display_name',
        string='Descripción',
        store=True
    )

    # Notas
    notes = fields.Text(
        string='Notas',
        help='Notas adicionales sobre este precio'
    )

    # Constraint SQL para evitar duplicados
    _sql_constraints = [
        ('partner_counter_unique',
         'UNIQUE(partner_id, counter_type_id)',
         'Ya existe un precio configurado para este cliente y tipo de contador')
    ]

    @api.depends('partner_id', 'partner_name', 'counter_type_id', 'counter_name', 'unit_price')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            if record.partner_name and record.counter_name:
                record.display_name = f"{record.partner_name} - {record.counter_name}: ${record.unit_price:.4f}"
            else:
                record.display_name = f"Precio #{record.id or 'Nuevo'}"

    @api.constrains('unit_price')
    def _check_unit_price(self):
        """Valida que el precio sea no negativo"""
        for record in self:
            if record.unit_price < 0:
                raise ValidationError(
                    f"El precio unitario no puede ser negativo: ${record.unit_price:.4f}"
                )

    @api.model
    def get_price_for_partner_counter(self, partner_id, counter_type_id):
        """
        Obtiene el precio configurado para un cliente y tipo de contador

        Args:
            partner_id: ID del cliente
            counter_type_id: ID del tipo de contador

        Returns:
            float: Precio configurado o 0.0 si no existe
        """
        price_record = self.search([
            ('partner_id', '=', partner_id),
            ('counter_type_id', '=', counter_type_id)
        ], limit=1)

        if price_record:
            _logger.debug(
                f"Precio encontrado para partner {partner_id}, counter {counter_type_id}: "
                f"${price_record.unit_price:.4f}"
            )
            return price_record.unit_price
        else:
            _logger.debug(
                f"No se encontró precio para partner {partner_id}, counter {counter_type_id}. "
                f"Usando 0.0"
            )
            return 0.0

    @api.model
    def get_all_prices_for_partner(self, partner_id):
        """
        Obtiene todos los precios configurados para un cliente

        Args:
            partner_id: ID del cliente

        Returns:
            dict: Diccionario {counter_type_id: unit_price}
        """
        prices = self.search([('partner_id', '=', partner_id)])
        return {price.counter_type_id.id: price.unit_price for price in prices}

    def name_get(self):
        """Muestra información completa en selects"""
        result = []
        for record in self:
            name = f"{record.partner_name} - {record.counter_name}"
            if record.counter_code:
                name += f" [{record.counter_code}]"
            name += f": ${record.unit_price:.4f}"
            result.append((record.id, name))
        return result
