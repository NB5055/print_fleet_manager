# -*- coding: utf-8 -*-
"""
Modelo de Consumibles de Impresoras
Seguimiento de niveles de tintas, toners y otros consumibles
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PrinterConsumable(models.Model):
    _name = 'printer.consumable'
    _description = 'Consumible de Impresora'
    _order = 'printer_id, supply_name'
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

    # Información del Consumible
    supply_name = fields.Char(
        string='Nombre del Consumible',
        required=True,
        help='Nombre descriptivo del consumible'
    )
    supply_type = fields.Selection([
        ('toner', 'Toner'),
        ('ink', 'Tinta'),
        ('drum', 'Tambor'),
        ('fuser', 'Fusor'),
        ('transfer_belt', 'Correa de Transferencia'),
        ('maintenance_kit', 'Kit de Mantenimiento'),
        ('waste_toner', 'Depósito de Residuos'),
        ('other', 'Otro')
    ], string='Tipo de Consumible', index=True)

    color = fields.Selection([
        ('black', 'Negro'),
        ('cyan', 'Cyan'),
        ('magenta', 'Magenta'),
        ('yellow', 'Amarillo'),
        ('lc', 'Light Cyan'),
        ('lm', 'Light Magenta'),
        ('tricolor', 'Tricolor'),
        ('other', 'Otro')
    ], string='Color')

    model = fields.Char(
        string='Modelo de Cartucho/Código',
        help='Número de modelo o código del cartucho'
    )

    # Niveles y Estado
    level_percent = fields.Float(
        string='Nivel Actual (%)',
        digits=(5, 2),
        help='Nivel actual del consumible en porcentaje'
    )
    previous_level = fields.Float(
        string='Nivel Anterior (%)',
        digits=(5, 2),
        readonly=True,
        help='Nivel en la última actualización'
    )

    status = fields.Selection([
        ('ok', 'OK'),
        ('low', 'Bajo'),
        ('critical', 'Crítico'),
        ('empty', 'Vacío'),
        ('replace', 'Reemplazar'),
        ('missing', 'Faltante'),
        ('unknown', 'Desconocido')
    ], string='Estado', default='unknown', index=True)

    # Umbrales de Alerta
    low_threshold = fields.Float(
        string='Umbral Bajo (%)',
        default=25.0,
        digits=(5, 2),
        help='Nivel de consumible para generar alerta de "Bajo"'
    )
    critical_threshold = fields.Float(
        string='Umbral Crítico (%)',
        default=10.0,
        digits=(5, 2),
        help='Nivel de consumible para generar alerta "Crítica"'
    )

    # Timestamps
    last_update = fields.Datetime(
        string='Última Actualización',
        default=fields.Datetime.now,
        readonly=True
    )
    first_detected = fields.Datetime(
        string='Primera Detección',
        default=fields.Datetime.now,
        readonly=True
    )
    replacement_date = fields.Datetime(
        string='Fecha de Reemplazo',
        help='Fecha en que se reemplazó el consumible'
    )

    # Estado Activo
    is_active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está inactivo, no se mostrará en las alertas'
    )

    # Sincronización
    printserver_id = fields.Integer(
        string='PrintServer ID',
        help='ID del consumible en PrintServer',
        index=True
    )

    # Campos Computados
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name'
    )
    level_status = fields.Char(
        string='Estado del Nivel',
        compute='_compute_level_status'
    )
    needs_replacement = fields.Boolean(
        string='Necesita Reemplazo',
        compute='_compute_needs_replacement',
        search='_search_needs_replacement'
    )

    @api.depends('supply_name', 'printer_id', 'color', 'supply_type')
    def _compute_display_name(self):
        """Genera nombre descriptivo"""
        for record in self:
            parts = []
            if record.printer_id:
                parts.append(record.printer_id.name)
            if record.supply_type:
                parts.append(dict(record._fields['supply_type'].selection).get(record.supply_type, ''))
            if record.color and record.color != 'other':
                parts.append(dict(record._fields['color'].selection).get(record.color, ''))
            if record.supply_name:
                parts.append(record.supply_name)

            record.display_name = ' - '.join(filter(None, parts)) or 'Consumible Sin Nombre'

    @api.depends('level_percent', 'status')
    def _compute_level_status(self):
        """Genera descripción del estado del nivel"""
        for record in self:
            if record.level_percent is not None:
                record.level_status = f"{record.level_percent:.1f}% - {record.status or 'Sin Estado'}"
            else:
                record.level_status = 'Nivel desconocido'

    @api.depends('level_percent', 'critical_threshold', 'status')
    def _compute_needs_replacement(self):
        """Determina si el consumible necesita reemplazo"""
        for record in self:
            record.needs_replacement = (
                record.is_active and
                (record.status in ['critical', 'empty', 'replace'] or
                 (record.level_percent is not None and record.level_percent <= record.critical_threshold))
            )

    def _search_needs_replacement(self, operator, value):
        """Permite buscar consumibles que necesitan reemplazo"""
        consumables = self.search([('is_active', '=', True)])
        result_ids = []
        for consumable in consumables:
            needs = (
                consumable.status in ['critical', 'empty', 'replace'] or
                (consumable.level_percent is not None and
                 consumable.level_percent <= consumable.critical_threshold)
            )
            if (operator == '=' and needs == value) or (operator == '!=' and needs != value):
                result_ids.append(consumable.id)
        return [('id', 'in', result_ids)]

    @api.constrains('level_percent')
    def _check_level_percent(self):
        """Valida que el nivel esté entre 0 y 100"""
        for record in self:
            if record.level_percent is not None:
                if record.level_percent < 0 or record.level_percent > 100:
                    raise ValidationError(
                        f"El nivel del consumible debe estar entre 0% y 100%. "
                        f"Valor actual: {record.level_percent}%"
                    )

    @api.constrains('low_threshold', 'critical_threshold')
    def _check_thresholds(self):
        """Valida que los umbrales sean lógicos"""
        for record in self:
            if record.critical_threshold and record.low_threshold:
                if record.critical_threshold >= record.low_threshold:
                    raise ValidationError(
                        "El umbral crítico debe ser menor que el umbral bajo"
                    )

    @api.model
    def create(self, vals):
        """Al crear, registra la primera detección"""
        if 'first_detected' not in vals:
            vals['first_detected'] = fields.Datetime.now()
        return super(PrinterConsumable, self).create(vals)

    def write(self, vals):
        """Al actualizar nivel, guarda el nivel anterior"""
        if 'level_percent' in vals:
            for record in self:
                vals['previous_level'] = record.level_percent
                vals['last_update'] = fields.Datetime.now()

                # Auto-actualizar status basado en nivel
                new_level = vals['level_percent']
                if new_level is not None:
                    if new_level <= 0:
                        vals['status'] = 'empty'
                    elif new_level <= record.critical_threshold:
                        vals['status'] = 'critical'
                    elif new_level <= record.low_threshold:
                        vals['status'] = 'low'
                    else:
                        vals['status'] = 'ok'

        return super(PrinterConsumable, self).write(vals)

    def action_mark_as_replaced(self):
        """Marca el consumible como reemplazado"""
        self.ensure_one()
        self.write({
            'replacement_date': fields.Datetime.now(),
            'level_percent': 100.0,
            'status': 'ok',
            'previous_level': self.level_percent or 0.0
        })
        _logger.info(f"Consumible marcado como reemplazado: {self.display_name}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Consumible Reemplazado',
                'message': f'{self.display_name} ha sido marcado como reemplazado',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_create_alert(self):
        """Crea una alerta para este consumible"""
        self.ensure_one()
        alert_type = 'consumable_low' if self.status == 'low' else 'consumable_critical'
        severity = 'medium' if self.status == 'low' else 'high'

        self.env['printer.alert'].create({
            'printer_id': self.printer_id.id,
            'alert_type': alert_type,
            'severity': severity,
            'message': f"{self.display_name}: Nivel al {self.level_percent:.1f}%",
            'resolved': False,
        })
        return True

    @api.model
    def check_and_create_alerts(self):
        """Método cron para verificar niveles y crear alertas"""
        # Buscar consumibles con nivel bajo o crítico sin alertas activas
        consumables = self.search([
            ('is_active', '=', True),
            ('status', 'in', ['low', 'critical', 'empty'])
        ])

        alert_model = self.env['printer.alert']
        created_count = 0

        for consumable in consumables:
            # Verificar si ya existe una alerta activa para este consumible
            existing_alert = alert_model.search([
                ('printer_id', '=', consumable.printer_id.id),
                ('alert_type', 'in', ['consumable_low', 'consumable_critical']),
                ('resolved', '=', False),
                ('message', 'ilike', consumable.supply_name)
            ], limit=1)

            if not existing_alert:
                consumable.action_create_alert()
                created_count += 1

        _logger.info(f"Verificación de consumibles completada. {created_count} alertas creadas.")
        return created_count

    def name_get(self):
        """Personaliza el nombre mostrado"""
        result = []
        for record in self:
            name = record.display_name
            if record.level_percent is not None:
                name += f" ({record.level_percent:.1f}%)"
            result.append((record.id, name))
        return result
