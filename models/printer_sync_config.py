# -*- coding: utf-8 -*-
"""
Configuración de Sincronización con PrintServer
Manejo de autenticación y seguridad
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import secrets
import hashlib
import hmac
import logging

_logger = logging.getLogger(__name__)


class PrinterSyncConfig(models.Model):
    _name = 'printer.sync.config'
    _description = 'Configuración de Sincronización PrintServer'

    name = fields.Char(
        string='Nombre',
        required=True,
        default='PrintServer Principal'
    )

    # Configuración de Conexión
    printserver_url = fields.Char(
        string='URL PrintServer',
        required=True,
        help='URL base del PrintServer (ej: https://printserver.local:8000)'
    )

    # Autenticación
    auth_method = fields.Selection([
        ('api_key', 'API Key'),
        ('jwt', 'JWT Token'),
        ('oauth2', 'OAuth 2.0'),
        ('hmac', 'HMAC Signature')
    ], string='Método de Autenticación', default='api_key', required=True)

    api_key = fields.Char(
        string='API Key',
        help='Clave de API para autenticación'
    )
    api_secret = fields.Char(
        string='API Secret',
        help='Secreto para firmar peticiones (HMAC)'
    )

    # Estado
    is_active = fields.Boolean(
        string='Activo',
        default=True
    )
    last_sync = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )
    last_sync_status = fields.Selection([
        ('success', 'Exitosa'),
        ('error', 'Error'),
        ('pending', 'Pendiente')
    ], string='Estado Última Sync', readonly=True)

    # Configuración de Sincronización
    sync_interval = fields.Integer(
        string='Intervalo de Sincronización (minutos)',
        default=5,
        help='Frecuencia de sincronización automática'
    )
    auto_sync = fields.Boolean(
        string='Sincronización Automática',
        default=True
    )

    # Configuración de Webhook
    webhook_enabled = fields.Boolean(
        string='Webhook Habilitado',
        default=True,
        help='Recibir notificaciones en tiempo real desde PrintServer'
    )
    webhook_secret = fields.Char(
        string='Webhook Secret',
        help='Secreto para validar webhooks entrantes'
    )

    # SSL/TLS
    verify_ssl = fields.Boolean(
        string='Verificar SSL',
        default=True,
        help='Verificar certificado SSL del PrintServer'
    )
    ssl_cert_path = fields.Char(
        string='Ruta Certificado SSL',
        help='Ruta al certificado SSL si es autofirmado'
    )

    # Logs
    log_requests = fields.Boolean(
        string='Log de Peticiones',
        default=False,
        help='Registrar todas las peticiones HTTP en logs'
    )

    # Estadísticas
    total_syncs = fields.Integer(
        string='Total Sincronizaciones',
        readonly=True,
        default=0
    )
    failed_syncs = fields.Integer(
        string='Sincronizaciones Fallidas',
        readonly=True,
        default=0
    )

    @api.model
    def generate_api_key(self):
        """Genera una API Key segura"""
        return secrets.token_urlsafe(32)

    @api.model
    def generate_webhook_secret(self):
        """Genera un secreto para webhook"""
        return secrets.token_hex(32)

    def action_generate_api_key(self):
        """Acción para generar nueva API Key"""
        self.ensure_one()
        self.api_key = self.generate_api_key()
        _logger.info(f"Nueva API Key generada para {self.name}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'API Key Generada',
                'message': 'Nueva API Key generada exitosamente. Guárdela de forma segura.',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_generate_webhook_secret(self):
        """Acción para generar nuevo secreto de webhook"""
        self.ensure_one()
        self.webhook_secret = self.generate_webhook_secret()
        _logger.info(f"Nuevo Webhook Secret generado para {self.name}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Webhook Secret Generado',
                'message': 'Nuevo secreto generado. Configure este valor en PrintServer.',
                'type': 'success',
                'sticky': False,
            }
        }

    def validate_webhook_signature(self, payload, signature):
        """
        Valida la firma HMAC de un webhook

        Args:
            payload: Cuerpo del webhook (string o bytes)
            signature: Firma HMAC recibida

        Returns:
            bool: True si la firma es válida
        """
        self.ensure_one()
        if not self.webhook_secret:
            _logger.warning("Webhook secret no configurado")
            return False

        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        expected_signature = hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def test_connection(self):
        """Prueba la conexión con PrintServer"""
        self.ensure_one()
        # TODO: Implementar prueba de conexión
        _logger.info(f"Probando conexión con {self.printserver_url}")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conexión',
                'message': 'Probando conexión con PrintServer...',
                'type': 'info',
                'sticky': False,
            }
        }

    @api.constrains('printserver_url')
    def _check_url(self):
        """Valida formato de URL"""
        import re
        url_pattern = r'^https?://.+'
        for record in self:
            if record.printserver_url:
                if not re.match(url_pattern, record.printserver_url):
                    raise ValidationError(
                        "URL inválida. Debe comenzar con http:// o https://"
                    )
