# -*- coding: utf-8 -*-
"""
Modelo de Alertas de Impresoras
Sistema de notificaciones y alertas para impresoras
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class PrinterAlert(models.Model):
    _name = 'printer.alert'
    _description = 'Alerta de Impresora'
    _order = 'timestamp desc, severity desc'
    _rec_names_search = ['message', 'printer_id']

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

    # Tipo y Severidad
    alert_type = fields.Selection([
        ('offline', 'Fuera de Línea'),
        ('online', 'Vuelto en Línea'),
        ('consumable_low', 'Consumible Bajo'),
        ('consumable_critical', 'Consumible Crítico'),
        ('consumable_empty', 'Consumible Vacío'),
        ('paper_jam', 'Atasco de Papel'),
        ('paper_out', 'Sin Papel'),
        ('door_open', 'Puerta Abierta'),
        ('maintenance', 'Mantenimiento Requerido'),
        ('error', 'Error General'),
        ('warning', 'Advertencia'),
        ('high_usage', 'Uso Elevado'),
        ('connection_lost', 'Conexión Perdida'),
        ('other', 'Otro')
    ], string='Tipo de Alerta', required=True, index=True)

    severity = fields.Selection([
        ('low', 'Baja'),
        ('medium', 'Media'),
        ('high', 'Alta'),
        ('critical', 'Crítica')
    ], string='Severidad', required=True, default='medium', index=True)

    # Mensaje
    message = fields.Text(
        string='Mensaje',
        required=True,
        help='Descripción detallada de la alerta'
    )
    notes = fields.Text(
        string='Notas',
        help='Notas adicionales sobre la alerta'
    )

    # Timestamps
    timestamp = fields.Datetime(
        string='Fecha y Hora',
        default=fields.Datetime.now,
        required=True,
        index=True,
        help='Momento en que se generó la alerta'
    )

    # Resolución
    resolved = fields.Boolean(
        string='Resuelta',
        default=False,
        index=True
    )
    resolved_at = fields.Datetime(
        string='Resuelta El',
        readonly=True
    )
    resolved_by = fields.Many2one(
        'res.users',
        string='Resuelta Por',
        readonly=True
    )
    resolution_notes = fields.Text(
        string='Notas de Resolución',
        help='Detalles sobre cómo se resolvió la alerta'
    )

    # Reconocimiento
    acknowledged = fields.Boolean(
        string='Reconocida',
        default=False,
        help='Indica si la alerta ha sido vista/reconocida'
    )
    acknowledged_at = fields.Datetime(
        string='Reconocida El',
        readonly=True
    )
    acknowledged_by = fields.Many2one(
        'res.users',
        string='Reconocida Por',
        readonly=True
    )

    # Sincronización
    printserver_id = fields.Integer(
        string='PrintServer ID',
        help='ID de la alerta en PrintServer',
        index=True
    )

    # Campos Computados
    age_days = fields.Integer(
        string='Antigüedad (días)',
        compute='_compute_age',
        help='Días desde que se generó la alerta'
    )
    is_active = fields.Boolean(
        string='Activa',
        compute='_compute_is_active',
        search='_search_is_active',
        help='Alerta no resuelta'
    )

    def _get_alert_label(self):
        """Nombre descriptivo de la alerta (sin iconos)"""
        self.ensure_one()
        alert_type_label = dict(self._fields['alert_type'].selection).get(self.alert_type, '')
        severity_label = dict(self._fields['severity'].selection).get(self.severity, '')
        parts = [
            f"[{severity_label.upper()}]" if severity_label else "",
            alert_type_label,
            f"- {self.printer_id.name}" if self.printer_id else "",
            f"({self.timestamp.strftime('%Y-%m-%d %H:%M')})" if self.timestamp else ""
        ]
        return ' '.join(filter(None, parts)) or 'Alerta Sin Nombre'

    @api.depends('printer_id.name', 'alert_type', 'timestamp', 'severity', 'resolved')
    def _compute_display_name(self):
        """Personaliza el nombre mostrado"""
        for record in self:
            severity_icon = {
                'low': '🔵',
                'medium': '🟡',
                'high': '🟠',
                'critical': '🔴'
            }.get(record.severity, '⚪')
            status = "✓" if record.resolved else "⚠"
            record.display_name = f"{severity_icon} {status} {record._get_alert_label()}"

    @api.depends('timestamp')
    def _compute_age(self):
        """Calcula la antigüedad de la alerta"""
        now = fields.Datetime.now()
        for record in self:
            if record.timestamp:
                delta = now - record.timestamp
                record.age_days = delta.days
            else:
                record.age_days = 0

    @api.depends('resolved')
    def _compute_is_active(self):
        """Determina si la alerta está activa"""
        for record in self:
            record.is_active = not record.resolved

    def _search_is_active(self, operator, value):
        """Permite buscar alertas activas (is_active == not resolved)"""
        if operator not in ('in', 'not in'):
            return NotImplemented
        return [('resolved', operator, [not bool(v) for v in value])]

    def action_acknowledge(self):
        """Reconoce la alerta (marca como vista)"""
        self.ensure_one()
        self.write({
            'acknowledged': True,
            'acknowledged_at': fields.Datetime.now(),
            'acknowledged_by': self.env.user.id
        })
        _logger.info(f"Alerta reconocida: {self._get_alert_label()} por {self.env.user.name}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Alerta Reconocida',
                'message': f'La alerta ha sido marcada como vista',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_resolve(self):
        """Resuelve la alerta"""
        self.ensure_one()
        self.write({
            'resolved': True,
            'resolved_at': fields.Datetime.now(),
            'resolved_by': self.env.user.id
        })
        _logger.info(f"Alerta resuelta: {self._get_alert_label()} por {self.env.user.name}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Alerta Resuelta',
                'message': f'La alerta ha sido marcada como resuelta',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_unresolve(self):
        """Marca la alerta como no resuelta"""
        self.ensure_one()
        self.write({
            'resolved': False,
            'resolved_at': False,
            'resolved_by': False,
            'resolution_notes': False
        })
        _logger.info(f"Alerta reabierta: {self._get_alert_label()} por {self.env.user.name}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Alerta Reabierta',
                'message': f'La alerta ha sido marcada como no resuelta',
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_bulk_resolve(self):
        """Resuelve múltiples alertas"""
        for record in self:
            if not record.resolved:
                record.action_resolve()
        return True

    def action_bulk_acknowledge(self):
        """Reconoce múltiples alertas"""
        for record in self:
            if not record.acknowledged:
                record.action_acknowledge()
        return True

    @api.model
    def auto_resolve_offline_alerts(self):
        """
        Método cron para auto-resolver alertas de "offline"
        cuando la impresora vuelve a estar online
        """
        # Buscar impresoras online
        online_printers = self.env['printer.device'].search([
            ('status', '=', 'online')
        ])

        # Buscar alertas de offline no resueltas para estas impresoras
        offline_alerts = self.search([
            ('printer_id', 'in', online_printers.ids),
            ('alert_type', '=', 'offline'),
            ('resolved', '=', False)
        ])

        for alert in offline_alerts:
            alert.write({
                'resolved': True,
                'resolved_at': fields.Datetime.now(),
                'resolution_notes': 'Auto-resuelto: Impresora volvió en línea'
            })

            # Crear alerta informativa de "online"
            self.create({
                'printer_id': alert.printer_id.id,
                'alert_type': 'online',
                'severity': 'low',
                'message': f'{alert.printer_id.name} ha vuelto en línea',
                'resolved': True,
                'resolved_at': fields.Datetime.now()
            })

        _logger.info(f"Auto-resueltas {len(offline_alerts)} alertas de offline")
        return len(offline_alerts)

    @api.model
    def cleanup_old_resolved_alerts(self, days=90):
        """
        Elimina alertas resueltas antiguas

        Args:
            days: Días de antigüedad mínima para eliminar
        """
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_alerts = self.search([
            ('resolved', '=', True),
            ('resolved_at', '<', cutoff_date)
        ])

        count = len(old_alerts)
        old_alerts.unlink()

        _logger.info(f"Eliminadas {count} alertas resueltas con más de {days} días")
        return count

    @api.constrains('severity', 'alert_type')
    def _check_severity_for_type(self):
        """Valida que la severidad sea apropiada para el tipo de alerta"""
        critical_types = ['consumable_empty', 'paper_jam', 'error']
        for record in self:
            if record.alert_type in critical_types and record.severity == 'low':
                _logger.warning(
                    f"Alerta de tipo '{record.alert_type}' con severidad 'low'. "
                    "Considere usar una severidad mayor."
                )
