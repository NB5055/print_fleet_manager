# -*- coding: utf-8 -*-
"""
Modelo de Ubicaciones de Impresoras
Gestión de tokens por ubicación/conexión
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import hashlib
import hmac
import secrets
import logging

_logger = logging.getLogger(__name__)


class PrinterLocation(models.Model):
    _name = 'printer.location'
    _description = 'Ubicación de Impresoras'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'partner_id, name'
    _rec_name = 'name'

    # Información Básica
    name = fields.Char(
        string='Nombre de Ubicación',
        required=True,
        help='Nombre descriptivo de la ubicación (ej: Oficina Central, Sucursal Norte)'
    )

    # Cliente
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
        help='Cliente al que pertenece esta ubicación'
    )

    # Dirección
    street = fields.Char(string='Calle')
    street2 = fields.Char(string='Calle 2')
    city = fields.Char(string='Ciudad')
    state_id = fields.Many2one(
        'res.country.state',
        string='Estado'
    )
    zip = fields.Char(string='Código Postal')
    country_id = fields.Many2one(
        'res.country',
        string='País'
    )

    # Token de Acceso (UN TOKEN POR UBICACIÓN)
    access_token = fields.Char(
        string='Token de Acceso',
        readonly=True,
        copy=False,
        groups='print_fleet_manager.group_printer_manager',
        help='Token único para autenticación de PrintServer en esta ubicación'
    )
    # Huella SHA-256 del token: la API busca por la huella (indexada) y luego
    # compara el token en tiempo constante, sin usar el token como clave de búsqueda.
    access_token_hash = fields.Char(
        string='Huella del Token',
        compute='_compute_access_token_hash',
        store=True,
        index=True,
        copy=False,
        groups='print_fleet_manager.group_printer_manager',
    )
    token_active = fields.Boolean(
        string='Token Activo',
        default=True,
        help='Si está desactivado, el PrintServer no podrá enviar datos'
    )
    token_created_date = fields.Datetime(
        string='Token Creado',
        readonly=True
    )
    token_last_used = fields.Datetime(
        string='Token Usado Por Última Vez',
        readonly=True
    )

    # Configuración
    description = fields.Text(string='Descripción')
    notes = fields.Text(string='Notas Internas')

    # Estado
    is_active = fields.Boolean(
        string='Ubicación Activa',
        default=True,
        index=True
    )

    # Sincronización
    last_sync = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )
    sync_status = fields.Selection([
        ('never', 'Nunca Sincronizado'),
        ('success', 'Sincronización Exitosa'),
        ('error', 'Error en Sincronización'),
        ('pending', 'Pendiente')
    ], string='Estado de Sincronización', default='never', readonly=True)

    # Timestamps
    created_date = fields.Datetime(
        string='Fecha de Creación',
        default=fields.Datetime.now,
        readonly=True
    )

    # Relaciones
    printer_ids = fields.One2many(
        'printer.device',
        'location_id',
        string='Impresoras',
        help='Impresoras registradas en esta ubicación'
    )

    # Campos Computados - Estadísticas
    printer_count = fields.Integer(
        string='Total de Impresoras',
        compute='_compute_stats',
        store=True
    )
    active_printer_count = fields.Integer(
        string='Impresoras Activas',
        compute='_compute_stats',
        store=True
    )
    total_pages_month = fields.Integer(
        string='Páginas Este Mes',
        compute='_compute_usage_stats',
        help='Total de páginas impresas en el mes actual'
    )
    mono_pages_month = fields.Integer(
        string='Páginas B/N Este Mes',
        compute='_compute_usage_stats'
    )
    color_pages_month = fields.Integer(
        string='Páginas Color Este Mes',
        compute='_compute_usage_stats'
    )

    # Estadísticas de Uso de Token
    token_requests_count = fields.Integer(
        string='Peticiones con Token',
        readonly=True,
        default=0,
        help='Número de peticiones recibidas usando este token'
    )

    @api.depends('printer_ids', 'printer_ids.is_active')
    def _compute_stats(self):
        """Calcula estadísticas de impresoras"""
        for record in self:
            record.printer_count = len(record.printer_ids)
            record.active_printer_count = len(
                record.printer_ids.filtered(lambda p: p.is_active)
            )

    @api.depends('printer_ids.reading_ids', 'printer_ids.reading_ids.counter_ids')
    def _compute_usage_stats(self):
        """Calcula estadísticas de uso mensual usando sistema dinámico de contadores"""
        for record in self:
            # Obtener primer y último día del mes actual
            today = fields.Date.today()
            first_day = today.replace(day=1)

            total_pages = 0
            mono_pages = 0
            color_pages = 0

            for printer in record.printer_ids:
                # Buscar lecturas del mes actual
                readings = printer.reading_ids.filtered(
                    lambda r: r.timestamp and r.timestamp.date() >= first_day
                )

                if readings:
                    # Tomar primera y última lectura del mes
                    sorted_readings = readings.sorted('timestamp')
                    first_reading = sorted_readings[0]
                    last_reading = sorted_readings[-1]

                    # Calcular diferencia usando get_counter_value
                    total_last = last_reading.get_counter_value('total')
                    total_first = first_reading.get_counter_value('total')
                    mono_last = last_reading.get_counter_value('mono')
                    mono_first = first_reading.get_counter_value('mono')
                    color_last = last_reading.get_counter_value('color')
                    color_first = first_reading.get_counter_value('color')

                    total_pages += max(0, total_last - total_first)
                    mono_pages += max(0, mono_last - mono_first)
                    color_pages += max(0, color_last - color_first)

            record.total_pages_month = total_pages
            record.mono_pages_month = mono_pages
            record.color_pages_month = color_pages

    @api.model
    def _generate_token(self):
        """Genera un token seguro de 32 caracteres"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest() if token else False

    @api.depends('access_token')
    def _compute_access_token_hash(self):
        for record in self:
            record.access_token_hash = self._hash_token(record.access_token)

    @api.model
    def _get_by_access_token(self, token, active_only=True):
        """Devuelve la ubicación (sudo) cuyo token coincide, o un recordset vacío.

        La búsqueda se hace por la huella SHA-256 y la comparación final del
        token se hace en tiempo constante (hmac.compare_digest).
        """
        if not token or not isinstance(token, str):
            return self.sudo().browse()
        domain = [('access_token_hash', '=', self._hash_token(token))]
        if active_only:
            domain.append(('is_active', '=', True))
        for location in self.sudo().search(domain):
            if location.access_token and hmac.compare_digest(
                location.access_token.encode('utf-8'), token.encode('utf-8')
            ):
                return location
        return self.sudo().browse()

    @api.model_create_multi
    def create(self, vals_list):
        """Al crear, genera automáticamente un token si no existe"""
        for vals in vals_list:
            if not vals.get('access_token'):
                vals['access_token'] = self._generate_token()
                vals['token_created_date'] = fields.Datetime.now()
        return super().create(vals_list)

    def action_generate_token(self):
        """Genera un nuevo token de acceso y muestra wizard con el token"""
        self.ensure_one()
        new_token = self._generate_token()

        self.write({
            'access_token': new_token,
            'token_created_date': fields.Datetime.now(),
            'token_last_used': False,
            'token_requests_count': 0,
        })

        _logger.info(
            f"Nuevo token generado para ubicación '{self.name}' "
            f"(Cliente: {self.partner_id.name})"
        )

        # Crear wizard para mostrar el token
        wizard = self.env['token.display.wizard'].create({
            'location_id': self.id,
            'access_token': new_token,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Token de Acceso Generado',
            'res_model': 'token.display.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_deactivate_token(self):
        """Desactiva el token actual"""
        self.ensure_one()
        self.token_active = False
        _logger.warning(
            f"Token desactivado para ubicación '{self.name}' "
            f"(Cliente: {self.partner_id.name})"
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Token Desactivado',
                'message': f'El token de {self.name} ha sido desactivado. '
                          'El PrintServer no podrá enviar datos hasta reactivarlo.',
                'type': 'warning',
                'sticky': False,
            }
        }

    def action_activate_token(self):
        """Activa el token"""
        self.ensure_one()
        if not self.access_token:
            return self.action_generate_token()

        self.token_active = True
        _logger.info(f"Token activado para ubicación '{self.name}'")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Token Activado',
                'message': f'El token de {self.name} ha sido activado.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_printers(self):
        """Abre vista de impresoras de esta ubicación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Impresoras - {self.name}',
            'res_model': 'printer.device',
            'view_mode': 'kanban,list,form',
            'domain': [('location_id', '=', self.id)],
            'context': {
                'default_location_id': self.id,
                'default_partner_id': self.partner_id.id,
            }
        }

    def action_view_usage_report(self):
        """Abre reporte de uso de esta ubicación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Reporte de Uso - {self.name}',
            'res_model': 'printer.reading',
            'view_mode': 'graph,pivot,list',
            'domain': [('printer_id.location_id', '=', self.id)],
            'context': {
                'search_default_group_printer': 1,
                'search_default_this_month': 1,
            }
        }

    def update_token_usage(self):
        """Actualiza estadísticas de uso del token"""
        self.ensure_one()
        self.write({
            'token_last_used': fields.Datetime.now(),
            'token_requests_count': self.token_requests_count + 1,
        })

    @api.constrains('name', 'partner_id')
    def _check_unique_name_per_partner(self):
        """Valida que no existan ubicaciones con el mismo nombre para el mismo cliente"""
        for record in self:
            existing = self.search([
                ('id', '!=', record.id),
                ('partner_id', '=', record.partner_id.id),
                ('name', '=', record.name)
            ])
            if existing:
                raise ValidationError(
                    f"Ya existe una ubicación con el nombre '{record.name}' "
                    f"para el cliente {record.partner_id.name}"
                )

    @api.constrains('access_token')
    def _check_unique_token(self):
        """Valida que el token sea único"""
        for record in self:
            if record.access_token:
                existing = self.sudo().search_count([
                    ('id', '!=', record.id),
                    ('access_token_hash', '=', self._hash_token(record.access_token))
                ], limit=1)
                if existing:
                    raise ValidationError(
                        "El token de acceso debe ser único. "
                        "Por favor, genere un nuevo token."
                    )

    @api.depends('name', 'partner_id.name', 'printer_count')
    def _compute_display_name(self):
        """Personaliza el nombre mostrado"""
        for record in self:
            name = f"{record.partner_id.name} - {record.name}"
            if record.printer_count:
                name += f" ({record.printer_count} impresoras)"
            record.display_name = name
