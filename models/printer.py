# -*- coding: utf-8 -*-
"""
Modelo de Impresoras
Réplica sincronizada con PrintServer
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class Printer(models.Model):
    _name = 'printer.device'
    _description = 'Impresora'
    _order = 'name'
    _rec_name = 'name'

    # Información Básica
    name = fields.Char(
        string='Nombre',
        compute='_compute_name',
        store=True
    )
    ip_address = fields.Char(
        string='Dirección IP',
        required=True,
        index=True
    )
    mac_address = fields.Char(
        string='Dirección MAC',
        size=17,
        index=True,
        help='Dirección MAC del adaptador de red (identificador único de hardware)'
    )
    serial_number = fields.Char(
        string='Número de Serie',
        index=True
    )
    model = fields.Char(string='Modelo')
    manufacturer = fields.Char(string='Fabricante')
    hostname = fields.Char(string='Hostname')

    # Ubicación y Cliente (NUEVO - Arquitectura token por ubicación)
    location_id = fields.Many2one(
        'printer.location',
        string='Ubicación',
        required=True,
        ondelete='restrict',
        index=True,
        help='Ubicación física donde está instalada la impresora'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='location_id.partner_id',
        store=True,
        readonly=True,
        index=True,
        help='Cliente al que pertenece la impresora (heredado de ubicación)'
    )

    # Ubicación Legacy (mantener por compatibilidad)
    location = fields.Char(
        string='Ubicación (Texto)',
        help='Campo de texto libre para información adicional de ubicación'
    )
    department = fields.Char(string='Departamento')

    # Estado y Conectividad
    status = fields.Selection([
        ('online', 'En Línea'),
        ('offline', 'Fuera de Línea'),
        ('error', 'Error'),
        ('maintenance', 'Mantenimiento'),
        ('unknown', 'Desconocido')
    ], string='Estado', default='unknown', index=True)

    is_active = fields.Boolean(
        string='Activo',
        default=True,
        index=True
    )

    # Vista Kanban
    color = fields.Integer(
        string='Color',
        help='Color para la vista kanban'
    )

    # Configuración SNMP
    community_string = fields.Char(
        string='Community String',
        default='public'
    )
    snmp_version = fields.Selection([
        ('1', 'SNMP v1'),
        ('2c', 'SNMP v2c'),
        ('3', 'SNMP v3')
    ], string='Versión SNMP', default='2c')

    # Sincronización con PrintServer
    printserver_id = fields.Integer(
        string='PrintServer ID',
        help='ID de la impresora en PrintServer',
        index=True
    )
    last_sync = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )
    sync_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('synced', 'Sincronizado'),
        ('error', 'Error')
    ], string='Estado de Sincronización', default='pending')

    # Timestamps
    last_seen = fields.Datetime(string='Última Vez Visto')
    last_reading = fields.Datetime(string='Última Lectura')
    created_date = fields.Datetime(
        string='Fecha de Creación',
        default=fields.Datetime.now,
        readonly=True
    )

    # Relaciones
    reading_ids = fields.One2many(
        'printer.reading',
        'printer_id',
        string='Lecturas'
    )
    consumable_ids = fields.One2many(
        'printer.consumable',
        'printer_id',
        string='Consumibles'
    )
    alert_ids = fields.One2many(
        'printer.alert',
        'printer_id',
        string='Alertas'
    )

    # Campos Computados
    total_pages = fields.Integer(
        string='Total de Páginas',
        compute='_compute_counters',
        store=True
    )
    mono_pages = fields.Integer(
        string='Páginas Monocromáticas',
        compute='_compute_counters',
        store=True
    )
    color_pages = fields.Integer(
        string='Páginas a Color',
        compute='_compute_counters',
        store=True
    )

    active_alerts_count = fields.Integer(
        string='Alertas Activas',
        compute='_compute_active_alerts'
    )

    # Restricciones SQL
    _sql_constraints = [
        ('unique_serial_per_location',
         'UNIQUE(location_id, serial_number)',
         'Ya existe una impresora con este número de serie en esta ubicación'),
        ('unique_ip_per_location',
         'UNIQUE(location_id, ip_address)',
         'Ya existe una impresora con esta IP en esta ubicación'),
    ]

    @api.depends('model', 'serial_number', 'ip_address', 'location_id')
    def _compute_name(self):
        """Genera el nombre de la impresora"""
        for record in self:
            if record.model and record.serial_number:
                record.name = f"{record.model} ({record.serial_number})"
            elif record.model:
                record.name = f"{record.model} - {record.ip_address}"
            else:
                record.name = record.ip_address or 'Nueva Impresora'

            # Agregar ubicación si está disponible
            if record.location_id:
                record.name = f"[{record.location_id.name}] {record.name}"

    @api.depends('reading_ids', 'reading_ids.counter_ids', 'reading_ids.counter_ids.value')
    def _compute_counters(self):
        """Calcula los contadores desde la última lectura usando sistema dinámico"""
        for record in self:
            last_reading = record.reading_ids.sorted('timestamp', reverse=True)[:1]
            if last_reading:
                # Usar el método helper para obtener valores de contadores por código
                record.total_pages = last_reading.get_counter_value('total')
                record.mono_pages = last_reading.get_counter_value('mono')
                record.color_pages = last_reading.get_counter_value('color')
            else:
                record.total_pages = 0
                record.mono_pages = 0
                record.color_pages = 0

    @api.depends('alert_ids')
    def _compute_active_alerts(self):
        """Cuenta alertas activas"""
        for record in self:
            record.active_alerts_count = len(
                record.alert_ids.filtered(lambda a: not a.resolved)
            )

    @api.constrains('ip_address')
    def _check_ip_address(self):
        """Valida formato de dirección IP"""
        import re
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        for record in self:
            if record.ip_address:
                if not re.match(ip_pattern, record.ip_address):
                    raise ValidationError(
                        f"Dirección IP inválida: {record.ip_address}"
                    )

    def action_view_readings(self):
        """Abre vista de lecturas"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Lecturas - {self.name}',
            'res_model': 'printer.reading',
            'view_mode': 'tree,form,graph',
            'domain': [('printer_id', '=', self.id)],
            'context': {'default_printer_id': self.id}
        }

    def action_view_consumables(self):
        """Abre vista de consumibles"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Consumibles - {self.name}',
            'res_model': 'printer.consumable',
            'view_mode': 'tree,form',
            'domain': [('printer_id', '=', self.id)],
            'context': {'default_printer_id': self.id}
        }

    def action_view_alerts(self):
        """Abre vista de alertas"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Alertas - {self.name}',
            'res_model': 'printer.alert',
            'view_mode': 'tree,form',
            'domain': [('printer_id', '=', self.id)],
            'context': {'default_printer_id': self.id}
        }

    def action_sync_with_printserver(self):
        """Sincroniza datos con PrintServer"""
        # Esta función será implementada en el controller
        self.ensure_one()
        _logger.info(f"Sincronizando impresora {self.name} con PrintServer")
        # TODO: Implementar llamada a API de PrintServer
        return True
