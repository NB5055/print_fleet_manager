# -*- coding: utf-8 -*-
"""
Tipos de Contadores SNMP
Catálogo maestro de tipos de contadores identificados por OID
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class CounterType(models.Model):
    _name = 'counter.type'
    _description = 'Tipo de Contador SNMP'
    _order = 'sequence, name'
    _rec_name = 'name'

    # Identificación
    oid = fields.Char(
        string='OID SNMP',
        required=True,
        index=True,
        help='Object Identifier SNMP único para este tipo de contador'
    )
    name = fields.Char(
        string='Nombre Descriptivo',
        required=True,
        help='Nombre editable para mostrar en interfaz (ej: "Páginas Monocromáticas")'
    )
    code = fields.Char(
        string='Código Interno',
        help='Código alfanumérico para referencia programática (ej: total, mono, color, duplex)'
    )

    # Facturación
    product_id = fields.Many2one(
        'product.product',
        string='Producto para Facturación',
        domain=[('type', '=', 'service')],
        help='Producto de servicio a usar en facturas para este tipo de contador'
    )
    unit_price = fields.Float(
        string='Precio Unitario',
        related='product_id.list_price',
        readonly=True
    )

    # Configuración
    sequence = fields.Integer(
        string='Orden de Visualización',
        default=10,
        help='Orden en que aparece en listas y reportes'
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Desmarcar para ocultar este tipo sin eliminarlo'
    )

    # Metadatos
    usage_count = fields.Integer(
        string='Lecturas Registradas',
        compute='_compute_usage_count',
        help='Cantidad de lecturas que usan este tipo'
    )

    # Constraint SQL
    _sql_constraints = [
        ('oid_unique', 'UNIQUE(oid)', 'El OID debe ser único. Ya existe un tipo con este OID.')
    ]

    @api.depends()
    def _compute_usage_count(self):
        """Calcula cuántas lecturas usan este tipo de contador"""
        for counter_type in self:
            counter_type.usage_count = self.env['printer.reading.counter'].search_count([
                ('counter_type_id', '=', counter_type.id)
            ])

    @api.constrains('oid')
    def _check_oid_format(self):
        """Valida formato básico de OID"""
        for record in self:
            if record.oid and not record.oid.replace('.', '').replace('1', '').replace('2', '').replace('3', '').replace('4', '').replace('5', '').replace('6', '').replace('7', '').replace('8', '').replace('9', '').replace('0', ''):
                continue
            elif record.oid:
                # Validación simple: debe empezar con número y contener puntos
                if not record.oid[0].isdigit() or '.' not in record.oid:
                    raise ValidationError(
                        f"OID inválido: '{record.oid}'. Debe ser formato SNMP (ej: 1.3.6.1.2.1.43.10.2.1.4.1.1)"
                    )

    def name_get(self):
        """Muestra OID junto al nombre"""
        result = []
        for record in self:
            name = f"{record.name}"
            if record.code:
                name += f" [{record.code}]"
            result.append((record.id, name))
        return result
