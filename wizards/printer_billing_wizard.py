# -*- coding: utf-8 -*-
"""
Wizard para generar facturas basadas en uso de impresoras
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PrinterBillingWizard(models.TransientModel):
    _name = 'printer.billing.wizard'
    _description = 'Generar Facturas de Uso de Impresoras'

    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        domain=lambda self: self._get_partners_with_readings_domain()
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        default=fields.Date.today
    )
    group_by_location = fields.Boolean(
        string='Agrupar por Ubicación',
        default=True,
        help='Crear una línea de factura por ubicación'
    )
    only_not_billed = fields.Boolean(
        string='Solo Lecturas No Facturadas',
        default=True
    )

    # Previsualización
    location_ids = fields.Many2many(
        'printer.location',
        string='Ubicaciones',
        compute='_compute_preview'
    )
    total_pages = fields.Integer(
        string='Total Páginas',
        compute='_compute_preview'
    )
    total_printers = fields.Integer(
        string='Total Impresoras',
        compute='_compute_preview'
    )

    @api.model
    def _get_partners_with_readings_domain(self):
        """
        Obtiene dominio de partners que tienen lecturas de impresoras
        Solo muestra clientes con datos reales para facturar
        """
        partner_ids = self.env['printer.reading'].search([]).mapped('partner_id').ids
        if not partner_ids:
            # Si no hay lecturas, retornar dominio vacío
            return [('id', '=', False)]
        return [('id', 'in', partner_ids)]

    @api.depends('partner_id', 'date_from', 'date_to')
    def _compute_preview(self):
        for wizard in self:
            if wizard.partner_id and wizard.date_from and wizard.date_to:
                # Buscar ubicaciones del cliente
                locations = self.env['printer.location'].search([
                    ('partner_id', '=', wizard.partner_id.id)
                ])
                wizard.location_ids = locations

                # Contar impresoras
                printers = self.env['printer.device'].search([
                    ('partner_id', '=', wizard.partner_id.id)
                ])
                wizard.total_printers = len(printers)

                # Calcular páginas totales del período
                readings = self.env['printer.reading'].search([
                    ('partner_id', '=', wizard.partner_id.id),
                    ('timestamp', '>=', wizard.date_from),
                    ('timestamp', '<=', wizard.date_to)
                ])

                if readings:
                    # Calcular uso con nueva estructura dinámica
                    usage_data = self.env['printer.reading'].calculate_usage_by_printer(
                        wizard.partner_id.id,
                        fields.Datetime.to_datetime(wizard.date_from),
                        fields.Datetime.to_datetime(wizard.date_to)
                    )
                    # Sumar todas las páginas de todos los contadores de todas las impresoras
                    total = 0
                    for printer_data in usage_data:
                        for counter in printer_data.get('counters', []):
                            total += counter.get('total_pages', 0)
                    wizard.total_pages = total
                else:
                    wizard.total_pages = 0
            else:
                wizard.location_ids = False
                wizard.total_pages = 0
                wizard.total_printers = 0

    def action_generate_invoice(self):
        """Crea revisión de facturación en borrador y abre formulario"""
        self.ensure_one()

        if not self.partner_id:
            raise UserError("Debe seleccionar un cliente")

        # Calcular uso con lógica híbrida
        usage_data = self.env['printer.reading'].calculate_usage_by_printer(
            self.partner_id.id,
            fields.Datetime.to_datetime(self.date_from),
            fields.Datetime.to_datetime(self.date_to)
        )

        if not usage_data:
            raise UserError(
                "No hay datos de uso para el período seleccionado.\n\n"
                "Verifique que:\n"
                "• Existen lecturas de impresoras para este cliente\n"
                "• El período seleccionado contiene lecturas\n"
                "• Las impresoras están correctamente asignadas al cliente"
            )

        # Calcular total de páginas
        total_pages = 0
        for printer_data in usage_data:
            for counter in printer_data.get('counters', []):
                total_pages += counter.get('total_pages', 0)

        _logger.info(
            f"Creando revisión para {self.partner_id.name}: "
            f"{len(usage_data)} impresoras encontradas, "
            f"{total_pages:,} páginas totales"
        )

        # Crear revisión PERSISTENTE en estado borrador
        review = self.env['printer.billing.review'].create({
            'partner_id': self.partner_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'group_by_location': self.group_by_location,
            'only_not_billed': self.only_not_billed,
            'state': 'draft',
        })

        # Crear líneas con contadores dinámicos
        for printer_data in usage_data:
            # Crear la línea de la impresora
            line = self.env['printer.billing.review.line'].create({
                'review_id': review.id,
                'printer_id': printer_data['printer'].id,
                'include_in_invoice': True,
            })

            # Crear los contadores de esta línea
            for counter_data in printer_data.get('counters', []):
                # Obtener precio configurado para este cliente y tipo de contador
                unit_price = self.env['partner.counter.price'].get_price_for_partner_counter(
                    self.partner_id.id,
                    counter_data['counter_type_id']
                )

                self.env['printer.billing.review.counter'].create({
                    'review_line_id': line.id,
                    'counter_type_id': counter_data['counter_type_id'],
                    'counter_start': counter_data['counter_start'],
                    'counter_end': counter_data['counter_end'],
                    'unit_price': unit_price,  # Asignar precio del cliente (o 0.0)
                })

        _logger.info(
            f"Revisión creada: {review.name} con {len(review.line_ids)} líneas "
            f"y {sum(len(line.counter_line_ids) for line in review.line_ids)} contadores"
        )

        # Abrir formulario de revisión (NO modal, ventana completa)
        return {
            'type': 'ir.actions.act_window',
            'name': f'Revisión de Facturación - {review.name}',
            'res_model': 'printer.billing.review',
            'res_id': review.id,
            'view_mode': 'form',
            'target': 'current',  # Pantalla completa, no modal
            'context': {'create': False},  # No permitir crear desde esta vista
        }
