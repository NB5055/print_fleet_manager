# -*- coding: utf-8 -*-
"""
Líneas de Revisión de Facturación
Permite editar manualmente los contadores antes de generar factura
"""

from odoo import models, fields, api


class PrinterBillingReviewWizardLine(models.TransientModel):
    _name = 'printer.billing.review.wizard.line'
    _description = 'Línea de Revisión de Facturación (Wizard)'
    _order = 'printer_name'

    # Relación con wizard principal
    wizard_id = fields.Many2one(
        'printer.billing.review.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )

    # Impresora y Ubicación
    printer_id = fields.Many2one(
        'printer.device',
        string='Impresora',
        required=True,
        readonly=True
    )
    printer_name = fields.Char(
        string='Nombre de Impresora',
        related='printer_id.name',
        store=True
    )
    location_id = fields.Many2one(
        'printer.location',
        string='Ubicación',
        related='printer_id.location_id',
        store=True,
        readonly=True
    )
    location_name = fields.Char(
        string='Ubicación',
        related='location_id.name'
    )

    # Contadores Totales (EDITABLES)
    counter_start = fields.Integer(
        string='Contador Inicial',
        required=True,
        help='Contador total al inicio del período'
    )
    counter_end = fields.Integer(
        string='Contador Final',
        required=True,
        help='Contador total al final del período'
    )

    # Contadores Mono (EDITABLES)
    mono_start = fields.Integer(
        string='Mono Inicial',
        default=0
    )
    mono_end = fields.Integer(
        string='Mono Final',
        default=0
    )

    # Contadores Color (EDITABLES)
    color_start = fields.Integer(
        string='Color Inicial',
        default=0
    )
    color_end = fields.Integer(
        string='Color Final',
        default=0
    )

    # Campos Computados
    total_pages = fields.Integer(
        string='Total Páginas',
        compute='_compute_totals',
        store=True
    )
    mono_pages = fields.Integer(
        string='Páginas Mono',
        compute='_compute_totals',
        store=True
    )
    color_pages = fields.Integer(
        string='Páginas Color',
        compute='_compute_totals',
        store=True
    )

    # Notas
    notes = fields.Text(
        string='Notas',
        help='Notas u observaciones sobre esta impresora'
    )

    # Campo para excluir de facturación
    include_in_invoice = fields.Boolean(
        string='Incluir en Factura',
        default=True,
        help='Desmarcar para excluir esta impresora de la factura'
    )

    @api.depends('counter_start', 'counter_end', 'mono_start', 'mono_end', 'color_start', 'color_end')
    def _compute_totals(self):
        """Calcula los totales automáticamente"""
        for line in self:
            line.total_pages = max(0, line.counter_end - line.counter_start)
            line.mono_pages = max(0, line.mono_end - line.mono_start)
            line.color_pages = max(0, line.color_end - line.color_start)

    @api.constrains('counter_start', 'counter_end')
    def _check_counters(self):
        """Valida que los contadores sean coherentes"""
        for line in self:
            if line.counter_end < line.counter_start:
                from odoo.exceptions import ValidationError
                raise ValidationError(
                    f"El contador final ({line.counter_end}) no puede ser menor "
                    f"que el contador inicial ({line.counter_start}) para {line.printer_name}"
                )
