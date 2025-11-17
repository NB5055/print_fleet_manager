# -*- coding: utf-8 -*-
"""
Contadores en Líneas de Revisión de Facturación
Almacena valores de contadores específicos para cada línea de revisión
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PrinterBillingReviewCounter(models.Model):
    _name = 'printer.billing.review.counter'
    _description = 'Contador en Línea de Revisión de Facturación'
    _order = 'review_line_id, counter_type_id'
    _rec_name = 'display_name'

    # Relaciones
    review_line_id = fields.Many2one(
        'printer.billing.review.line',
        string='Línea de Revisión',
        required=True,
        ondelete='cascade',
        index=True
    )
    review_id = fields.Many2one(
        'printer.billing.review',
        string='Revisión',
        related='review_line_id.review_id',
        store=True,
        readonly=True,
        index=True
    )
    printer_id = fields.Many2one(
        'printer.device',
        string='Impresora',
        related='review_line_id.printer_id',
        store=True,
        readonly=True
    )
    printer_name = fields.Char(
        string='Impresora',
        related='review_line_id.printer_name',
        store=True,
        readonly=True
    )
    location_name = fields.Char(
        string='Ubicación',
        related='review_line_id.location_name',
        store=True,
        readonly=True
    )
    counter_type_id = fields.Many2one(
        'counter.type',
        string='Tipo de Contador',
        required=True,
        index=True
    )

    # Valores del Contador
    counter_start = fields.Integer(
        string='Contador Inicial',
        default=0,
        help='Valor del contador al inicio del período'
    )
    counter_end = fields.Integer(
        string='Contador Final',
        default=0,
        help='Valor del contador al final del período'
    )

    # Campos Calculados
    total_pages = fields.Integer(
        string='Total Páginas',
        compute='_compute_totals',
        store=True,
        help='Diferencia entre contador final e inicial'
    )
    unit_price = fields.Float(
        string='Precio Unitario',
        default=0.0,
        help='Precio por página (editable durante revisión)'
    )
    subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )

    # Campos Relacionados
    counter_name = fields.Char(
        string='Nombre',
        related='counter_type_id.name',
        readonly=True
    )
    counter_code = fields.Char(
        string='Código',
        related='counter_type_id.code',
        readonly=True
    )
    oid = fields.Char(
        string='OID',
        related='counter_type_id.oid',
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        related='counter_type_id.product_id',
        readonly=True
    )

    # Estado de la revisión (para readonly en vista)
    review_state = fields.Selection(
        related='review_line_id.review_state',
        string='Estado de Revisión'
    )

    # Moneda
    currency_id = fields.Many2one(
        'res.currency',
        related='review_line_id.currency_id',
        readonly=True
    )

    # Display name computado
    display_name = fields.Char(
        compute='_compute_display_name',
        string='Descripción'
    )

    # Constraint SQL para evitar duplicados
    _sql_constraints = [
        ('review_line_counter_unique',
         'UNIQUE(review_line_id, counter_type_id)',
         'No puede haber dos contadores del mismo tipo en una línea de revisión')
    ]

    @api.depends('counter_name', 'total_pages', 'subtotal')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            if record.counter_name and record.total_pages:
                record.display_name = f"{record.counter_name}: {record.total_pages:,} páginas (${record.subtotal:,.2f})"
            elif record.counter_name:
                record.display_name = f"{record.counter_name}"
            else:
                record.display_name = f"Contador #{record.id}"

    @api.depends('counter_start', 'counter_end', 'unit_price')
    def _compute_totals(self):
        """Calcula total de páginas y subtotal"""
        for record in self:
            # Calcular páginas
            record.total_pages = max(0, record.counter_end - record.counter_start)

            # Calcular subtotal usando unit_price editable
            record.subtotal = record.total_pages * record.unit_price

    @api.constrains('counter_start', 'counter_end')
    def _check_counters_valid(self):
        """Valida que los contadores sean válidos"""
        for record in self:
            if record.counter_start < 0:
                raise ValidationError(
                    f"El contador inicial no puede ser negativo: {record.counter_start}"
                )
            if record.counter_end < 0:
                raise ValidationError(
                    f"El contador final no puede ser negativo: {record.counter_end}"
                )
            if record.counter_end < record.counter_start:
                raise ValidationError(
                    f"El contador final ({record.counter_end:,}) no puede ser menor "
                    f"que el inicial ({record.counter_start:,}) para {record.counter_name}"
                )

    def get_billing_description(self):
        """Genera descripción para línea de factura"""
        self.ensure_one()

        description = f"{self.counter_name}\n"
        description += f"Contador inicial: {self.counter_start:,}\n"
        description += f"Contador final: {self.counter_end:,}\n"
        description += f"Total: {self.total_pages:,} páginas"

        return description
