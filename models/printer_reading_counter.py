# -*- coding: utf-8 -*-
"""
Valores de Contadores en Lecturas
Almacena el valor de cada tipo de contador para una lectura específica
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PrinterReadingCounter(models.Model):
    _name = 'printer.reading.counter'
    _description = 'Valor de Contador en Lectura'
    _order = 'reading_id, counter_type_id'
    _rec_name = 'display_name'

    # Relaciones
    reading_id = fields.Many2one(
        'printer.reading',
        string='Lectura',
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

    # Valor del Contador
    value = fields.Integer(
        string='Valor',
        required=True,
        default=0,
        help='Valor acumulado del contador en el momento de la lectura'
    )

    # Campos relacionados para facilitar búsquedas y reportes
    oid = fields.Char(
        string='OID',
        related='counter_type_id.oid',
        store=True,
        readonly=True,
        index=True
    )
    counter_code = fields.Char(
        string='Código',
        related='counter_type_id.code',
        store=True,
        readonly=True,
        index=True
    )
    counter_name = fields.Char(
        string='Nombre',
        related='counter_type_id.name',
        readonly=True
    )

    # Información de la lectura (para reportes)
    printer_id = fields.Many2one(
        'printer.device',
        related='reading_id.printer_id',
        store=True,
        readonly=True,
        index=True
    )
    timestamp = fields.Datetime(
        related='reading_id.timestamp',
        store=True,
        readonly=True,
        index=True
    )

    # Display name computado
    display_name = fields.Char(
        compute='_compute_display_name',
        string='Descripción'
    )

    # Constraint SQL para evitar duplicados
    _sql_constraints = [
        ('reading_counter_unique',
         'UNIQUE(reading_id, counter_type_id)',
         'No puede haber dos valores del mismo tipo de contador en una lectura')
    ]

    @api.depends('counter_name', 'value', 'oid')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            if record.counter_name and record.value is not False:
                record.display_name = f"{record.counter_name}: {record.value:,}"
            else:
                record.display_name = f"Contador #{record.id}"

    @api.constrains('value')
    def _check_value_positive(self):
        """Valida que el valor no sea negativo"""
        for record in self:
            if record.value < 0:
                raise ValidationError(
                    f"El valor del contador no puede ser negativo: {record.value}"
                )

    def get_previous_value(self):
        """Obtiene el valor anterior del mismo tipo de contador para la misma impresora"""
        self.ensure_one()

        previous_counter = self.search([
            ('printer_id', '=', self.printer_id.id),
            ('counter_type_id', '=', self.counter_type_id.id),
            ('timestamp', '<', self.timestamp),
            ('id', '!=', self.id)
        ], order='timestamp desc', limit=1)

        return previous_counter.value if previous_counter else 0

    def get_increment_since_last(self):
        """Calcula el incremento desde la lectura anterior"""
        self.ensure_one()
        previous_value = self.get_previous_value()
        return max(0, self.value - previous_value)
