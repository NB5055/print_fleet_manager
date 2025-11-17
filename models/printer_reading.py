# -*- coding: utf-8 -*-
"""
Modelo de Lecturas de Contadores
Almacena las lecturas históricas de contadores de impresoras
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PrinterReading(models.Model):
    _name = 'printer.reading'
    _description = 'Lectura de Contadores de Impresora'
    _order = 'timestamp desc'
    _rec_name = 'display_name'

    # Relaciones
    printer_id = fields.Many2one(
        'printer.device',
        string='Impresora',
        required=True,
        ondelete='cascade',
        index=True
    )
    location_id = fields.Many2one(
        'printer.location',
        string='Ubicación',
        related='printer_id.location_id',
        store=True,
        readonly=True,
        index=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='printer_id.partner_id',
        store=True,
        readonly=True,
        index=True
    )

    # Timestamp
    timestamp = fields.Datetime(
        string='Fecha y Hora',
        required=True,
        default=fields.Datetime.now,
        index=True
    )

    # Contadores Dinámicos (One2many)
    counter_ids = fields.One2many(
        'printer.reading.counter',
        'reading_id',
        string='Contadores',
        help='Valores de contadores SNMP para esta lectura'
    )

    # Estado
    status = fields.Selection([
        ('online', 'En Línea'),
        ('offline', 'Fuera de Línea'),
        ('error', 'Error'),
        ('warning', 'Advertencia'),
        ('printing', 'Imprimiendo'),
        ('idle', 'Inactivo'),
        ('unknown', 'Desconocido')
    ], string='Estado', default='unknown')

    # Sincronización
    printserver_id = fields.Integer(
        string='PrintServer ID',
        help='ID de la lectura en PrintServer',
        index=True
    )
    sync_timestamp = fields.Datetime(
        string='Fecha de Sincronización',
        default=fields.Datetime.now,
        readonly=True
    )

    # Campos para Facturación
    billing_period = fields.Char(
        string='Período de Facturación',
        compute='_compute_billing_period',
        store=True,
        index=True,
        help='Período en formato YYYY-MM'
    )
    is_billed = fields.Boolean(
        string='Facturado',
        default=False,
        index=True,
        help='Indica si esta lectura ha sido incluida en una factura'
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura',
        readonly=True,
        help='Factura relacionada si ya fue facturada'
    )
    billed_date = fields.Datetime(
        string='Fecha de Facturación',
        readonly=True
    )

    # Campos Computados para Análisis
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name'
    )

    @api.depends('printer_id', 'timestamp')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            if record.printer_id and record.timestamp:
                record.display_name = f"{record.printer_id.name} - {record.timestamp.strftime('%Y-%m-%d %H:%M')}"
            else:
                record.display_name = f"Lectura #{record.id or 'Nueva'}"

    @api.depends('timestamp')
    def _compute_billing_period(self):
        """Calcula el período de facturación (año-mes)"""
        for record in self:
            if record.timestamp:
                record.billing_period = record.timestamp.strftime('%Y-%m')
            else:
                record.billing_period = False

    @api.constrains('timestamp', 'printer_id')
    def _check_timestamp_order(self):
        """Valida que no haya timestamps duplicados para la misma impresora"""
        for record in self:
            if record.printer_id and record.timestamp:
                existing = self.search([
                    ('printer_id', '=', record.printer_id.id),
                    ('timestamp', '=', record.timestamp),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(
                        f"Ya existe una lectura para {record.printer_id.name} "
                        f"en {record.timestamp}"
                    )

    def action_mark_as_billed(self):
        """Marca la lectura como facturada"""
        self.ensure_one()
        self.write({
            'is_billed': True,
            'billed_date': fields.Datetime.now()
        })
        return True

    def action_unmark_billed(self):
        """Desmarca la lectura como facturada"""
        self.ensure_one()
        if self.invoice_id:
            raise ValidationError(
                "No se puede desmarcar una lectura que tiene una factura asociada"
            )
        self.write({
            'is_billed': False,
            'billed_date': False
        })
        return True

    @api.model
    def get_readings_for_billing(self, partner_id, date_from, date_to):
        """
        Obtiene lecturas pendientes de facturar para un cliente

        Args:
            partner_id: ID del cliente
            date_from: Fecha desde
            date_to: Fecha hasta

        Returns:
            Recordset de lecturas
        """
        return self.search([
            ('partner_id', '=', partner_id),
            ('timestamp', '>=', date_from),
            ('timestamp', '<=', date_to),
            ('is_billed', '=', False)
        ])

    @api.model
    def calculate_usage_by_printer(self, partner_id, date_from, date_to):
        """
        Calcula el uso por impresora para un período con contadores dinámicos

        Lógica híbrida por cada tipo de contador:
        - Caso 1: Solo 1 lectura en período + NO hay lecturas anteriores
          → contador inicial = 0, contador final = valor de esa lectura
        - Caso 2: Múltiples lecturas en período
          → contador inicial = lectura menor, contador final = lectura mayor
        - Caso 3: Solo 1 lectura en período + SÍ hay lecturas anteriores
          → contador inicial = última lectura anterior, contador final = lectura del período
        - Caso 4: NO hay lecturas en período
          → no incluir esta impresora

        Args:
            partner_id: ID del cliente
            date_from: Fecha desde
            date_to: Fecha hasta

        Returns:
            Lista de diccionarios con uso por impresora (con contadores dinámicos)
        """
        from datetime import datetime

        # Obtener impresoras del cliente
        Printer = self.env['printer.device']
        printers = Printer.search([('partner_id', '=', partner_id)])

        # Convertir date_to a datetime para incluir TODO el día final
        if isinstance(date_to, datetime):
            date_to_end = date_to.replace(hour=23, minute=59, second=59)
        else:
            date_to_end = datetime.combine(date_to, datetime.max.time())

        usage_by_printer = []

        for printer in printers:
            # Buscar lecturas en el período
            readings_in_period = self.search([
                ('printer_id', '=', printer.id),
                ('timestamp', '>=', date_from),
                ('timestamp', '<=', date_to_end)
            ], order='timestamp')

            if not readings_in_period:
                # CASO 4: No hay lecturas en período, saltar esta impresora
                continue

            _logger.info(
                f"Impresora {printer.name}: {len(readings_in_period)} lecturas en período"
            )

            # Obtener todos los tipos de contadores presentes en las lecturas
            counter_types_in_period = self.env['counter.type']
            for reading in readings_in_period:
                counter_types_in_period |= reading.counter_ids.mapped('counter_type_id')

            if not counter_types_in_period:
                _logger.warning(f"  {printer.name}: No tiene contadores registrados")
                continue

            # Calcular contadores por tipo
            counters_data = []

            for counter_type in counter_types_in_period:
                # Determinar lectura inicial y final para este tipo de contador
                first_reading = None
                last_reading = None
                first_value = 0
                last_value = 0

                # Encontrar última lectura del período que tenga este tipo de contador
                readings_with_counter = readings_in_period.filtered(
                    lambda r: counter_type.id in r.counter_ids.mapped('counter_type_id').ids
                )

                if not readings_with_counter:
                    continue

                # El contador FINAL siempre es la última lectura del período
                last_reading = readings_with_counter[-1]
                last_value = last_reading.get_counter_value(counter_type.oid)

                # El contador INICIAL es la última lectura ANTES del período (o 0)
                previous_reading = self.search([
                    ('printer_id', '=', printer.id),
                    ('timestamp', '<', date_from)
                ], order='timestamp desc', limit=1)

                if previous_reading:
                    # Hay lectura anterior: usar su valor
                    first_reading = previous_reading
                    first_value = previous_reading.get_counter_value(counter_type.oid)
                else:
                    # No hay lecturas anteriores: contador inicial = 0
                    first_value = 0

                # Calcular diferencia
                total = max(0, last_value - first_value)

                counters_data.append({
                    'counter_type_id': counter_type.id,
                    'counter_type': counter_type,
                    'oid': counter_type.oid,
                    'code': counter_type.code,
                    'name': counter_type.name,
                    'counter_start': first_value,
                    'counter_end': last_value,
                    'total_pages': total,
                })

                _logger.info(
                    f"  {printer.name} - {counter_type.name}: "
                    f"Inicial={first_value}, Final={last_value}, Total={total}"
                )

            # Agregar datos de la impresora
            if counters_data:
                usage_by_printer.append({
                    'printer': printer,
                    'printer_name': printer.name,
                    'location': printer.location_id.name if printer.location_id else 'Sin ubicación',
                    'counters': counters_data,
                })

        return usage_by_printer

    def name_get(self):
        """Personaliza el nombre mostrado"""
        result = []
        for record in self:
            name = f"{record.printer_id.name if record.printer_id else 'Sin Impresora'} - "
            name += f"{record.timestamp.strftime('%Y-%m-%d %H:%M') if record.timestamp else 'Sin Fecha'}"
            name += f" ({len(record.counter_ids)} contadores)"
            result.append((record.id, name))
        return result

    def get_counter_value(self, oid_or_code):
        """
        Obtiene el valor de un contador por OID o código

        Args:
            oid_or_code: OID SNMP o código interno del contador

        Returns:
            Valor del contador o 0 si no existe
        """
        self.ensure_one()

        counter = self.counter_ids.filtered(
            lambda c: c.oid == oid_or_code or c.counter_code == oid_or_code
        )

        return counter.value if counter else 0
