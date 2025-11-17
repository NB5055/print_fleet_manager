# -*- coding: utf-8 -*-
"""
Líneas de Revisión de Facturación de Impresoras (PERSISTENTE)
Contadores editables por impresora
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PrinterBillingReviewLine(models.Model):
    _name = 'printer.billing.review.line'
    _description = 'Línea de Revisión de Facturación'
    _order = 'printer_name'
    _rec_name = 'printer_name'

    # Relación con Revisión
    review_id = fields.Many2one(
        'printer.billing.review',
        string='Revisión',
        required=True,
        ondelete='cascade',
        index=True
    )
    review_state = fields.Selection(
        related='review_id.state',
        string='Estado de Revisión',
        store=True,
        readonly=True
    )

    # Impresora
    printer_id = fields.Many2one(
        'printer.device',
        string='Impresora',
        required=True,
        readonly=True,
        index=True
    )
    printer_name = fields.Char(
        string='Nombre',
        related='printer_id.name',
        store=True,
        readonly=True
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
        related='printer_id.location_id.name',
        store=True,
        readonly=True
    )

    # Contadores Dinámicos (One2many)
    counter_line_ids = fields.One2many(
        'printer.billing.review.counter',
        'review_line_id',
        string='Contadores',
        help='Valores de contadores editables para esta impresora'
    )

    # Totales Computados desde Contadores
    total_pages = fields.Integer(
        string='Total Páginas',
        compute='_compute_totals',
        store=True,
        help='Suma de todas las páginas de todos los contadores'
    )

    # Control de Facturación
    include_in_invoice = fields.Boolean(
        string='Incluir en Factura',
        default=True,
        help='Si está marcado, esta impresora se incluirá en la factura'
    )

    # Notas
    notes = fields.Text(
        string='Notas',
        help='Observaciones sobre esta línea'
    )

    # Monto Estimado
    estimated_amount = fields.Monetary(
        string='Monto Estimado',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help='Monto estimado basado en precio del producto'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='review_id.currency_id',
        store=True
    )

    @api.depends(
        'counter_line_ids',
        'counter_line_ids.total_pages',
        'counter_line_ids.subtotal',
        'include_in_invoice'
    )
    def _compute_totals(self):
        """Calcula totales desde los contadores dinámicos"""
        for line in self:
            # Sumar páginas de todos los contadores
            line.total_pages = sum(line.counter_line_ids.mapped('total_pages'))

            # Calcular monto como suma de subtotales de contadores
            if line.include_in_invoice:
                line.estimated_amount = sum(line.counter_line_ids.mapped('subtotal'))
            else:
                line.estimated_amount = 0

    def name_get(self):
        """Personaliza el nombre mostrado"""
        result = []
        for record in self:
            name = f"{record.printer_name or 'Sin Impresora'}"
            if record.total_pages > 0:
                name += f" ({record.total_pages:,} páginas)"
            else:
                name += " (0 páginas)"
            result.append((record.id, name))
        return result
