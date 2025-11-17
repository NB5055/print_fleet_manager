# -*- coding: utf-8 -*-
"""
Extensión del modelo res.partner para agregar precios de contadores
"""

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Relación con precios de contadores
    counter_price_ids = fields.One2many(
        'partner.counter.price',
        'partner_id',
        string='Precios de Contadores',
        help='Precios personalizados para tipos de contadores'
    )

    # Campo computado para botón inteligente
    counter_prices_count = fields.Integer(
        compute='_compute_counter_prices_count',
        string='Total Precios'
    )

    @api.depends('counter_price_ids')
    def _compute_counter_prices_count(self):
        """Cuenta la cantidad de precios configurados"""
        for partner in self:
            partner.counter_prices_count = len(partner.counter_price_ids)

    def action_view_counter_prices(self):
        """Abre la vista de precios de contadores para este cliente"""
        self.ensure_one()
        return {
            'name': f'Precios de {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'partner.counter.price',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {
                'default_partner_id': self.id,
                'search_default_partner_id': self.id
            }
        }
