# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TokenDisplayWizard(models.TransientModel):
    _name = 'token.display.wizard'
    _description = 'Wizard para mostrar token de acceso generado'

    location_id = fields.Many2one(
        'printer.location',
        string='Ubicación',
        readonly=True
    )

    access_token = fields.Char(
        string='Token de Acceso',
        readonly=True,
        help='Token de acceso para configurar en el PrintServer'
    )

    token_url = fields.Char(
        string='URL de Odoo',
        compute='_compute_token_url',
        readonly=True
    )

    @api.depends('location_id')
    def _compute_token_url(self):
        """Calcula la URL base de Odoo para mostrar en las instrucciones"""
        for wizard in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            wizard.token_url = base_url or 'http://localhost:8069'

    def action_copy_instructions(self):
        """Cierra el wizard - el botón de copiar es manejado por JavaScript"""
        return {'type': 'ir.actions.act_window_close'}
