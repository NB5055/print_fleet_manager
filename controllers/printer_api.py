# -*- coding: utf-8 -*-
"""
API REST para sincronización con PrintServer
Validación de token por ubicación y endpoints de sincronización
"""

import json
import logging
from datetime import datetime
from odoo import http, fields
from odoo.http import request, Response
from functools import wraps

_logger = logging.getLogger(__name__)


def parse_timestamp(timestamp_str):
    """
    Parsea timestamp en formato ISO (con o sin microsegundos) y lo convierte a datetime

    Soporta formatos:
    - ISO con microsegundos: "2025-10-19T10:57:00.161493"
    - ISO sin microsegundos: "2025-10-19T10:57:00"
    - Formato Odoo: "2025-10-19 10:57:00"

    Returns:
        datetime object
    """
    if not timestamp_str:
        return datetime.now()

    try:
        # Intentar parsear como ISO (formato enviado por PrintServer)
        # Python 3.7+ soporta datetime.fromisoformat()
        if 'T' in timestamp_str:
            # Remover microsegundos si existen para compatibilidad
            if '.' in timestamp_str:
                timestamp_str = timestamp_str.split('.')[0]
            return datetime.fromisoformat(timestamp_str)
        else:
            # Formato Odoo estándar
            return fields.Datetime.from_string(timestamp_str)
    except Exception as e:
        _logger.warning(f"Error parseando timestamp '{timestamp_str}': {e}, usando datetime.now()")
        return datetime.now()


def normalize_severity(severity_str):
    """
    Normaliza el valor de severity para compatibilidad con el modelo de Odoo

    PrintServer puede enviar: info, warning, error, critical
    Odoo acepta: low, medium, high, critical

    Mapeo:
    - info → low
    - warning → medium
    - error → high
    - critical → critical
    - low, medium, high → sin cambios

    Returns:
        str: Valor válido para el modelo printer.alert
    """
    severity_map = {
        'info': 'low',
        'warning': 'medium',
        'error': 'high',
        'critical': 'critical',
        # Valores ya válidos
        'low': 'low',
        'medium': 'medium',
        'high': 'high'
    }

    normalized = severity_map.get(severity_str, 'medium')

    if severity_str not in severity_map:
        _logger.warning(f"Severity desconocido '{severity_str}', usando 'medium' por defecto")

    return normalized


def validate_location_token(func):
    """
    Decorador para validar Location Token en peticiones

    El token debe enviarse en el header 'X-Location-Token'
    Este token es único por ubicación y permite enviar datos
    de todas las impresoras de esa ubicación
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Obtener token del header
        location_token = request.httprequest.headers.get('X-Location-Token')

        if not location_token:
            _logger.warning("Intento de acceso sin token de ubicación")
            return Response(
                json.dumps({
                    'status': 'error',
                    'error': 'Location Token requerido',
                    'message': 'Debe proporcionar el token de ubicación en el header X-Location-Token'
                }),
                status=401,
                mimetype='application/json'
            )

        # Buscar ubicación con este token
        location = request.env['printer.location'].sudo().search([
            ('access_token', '=', location_token),
            ('is_active', '=', True)
        ], limit=1)

        if not location:
            _logger.warning(f"Intento de acceso con token inválido: {location_token[:10]}...")
            return Response(
                json.dumps({
                    'status': 'error',
                    'error': 'Token inválido o inactivo',
                    'message': 'El token de ubicación no es válido o ha sido desactivado'
                }),
                status=403,
                mimetype='application/json'
            )

        # Verificar que el token esté activo
        if not location.token_active:
            _logger.warning(f"Intento de acceso con token desactivado para: {location.name}")
            return Response(
                json.dumps({
                    'status': 'error',
                    'error': 'Token desactivado',
                    'message': f'El token para la ubicación "{location.name}" ha sido desactivado'
                }),
                status=403,
                mimetype='application/json'
            )

        # Actualizar estadísticas de uso del token
        location.update_token_usage()

        # Almacenar ubicación en request para uso posterior
        request.printer_location = location

        _logger.info(
            f"Acceso autorizado - Ubicación: {location.name}, "
            f"Cliente: {location.partner_id.name}, "
            f"Token usado {location.token_requests_count} veces"
        )

        return func(*args, **kwargs)

    return wrapper


class PrinterAPIController(http.Controller):
    """
    Controlador de API REST para PrintServer
    """

    @http.route('/api/printer/sync/printers', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_location_token
    def sync_printers(self, **kwargs):
        """
        Endpoint para sincronizar datos de impresoras desde PrintServer

        El PrintServer envía datos de todas las impresoras de su ubicación.
        Todas las impresoras se asocian automáticamente a la ubicación del token.

        Header requerido:
            X-Location-Token: <token de la ubicación>

        Payload esperado:
        {
            "printers": [
                {
                    "ip_address": "10.0.0.14",
                    "serial_number": "XYZ123",
                    "model": "EPSON WF-6590",
                    "manufacturer": "EPSON",
                    "hostname": "printer-01",
                    "status": "online",
                    "last_seen": "2025-10-13T10:30:00"
                }
            ]
        }

        Returns:
        {
            "status": "success",
            "location": "Oficina Central",
            "partner": "Cliente ABC",
            "created": 2,
            "updated": 3,
            "total": 5
        }
        """
        try:
            data = json.loads(request.httprequest.data)
            printers_data = data.get('printers', [])

            # Obtener ubicación desde el decorador
            location = request.printer_location

            created = 0
            updated = 0
            errors = []

            for printer_data in printers_data:
                try:
                    ip_address = printer_data.get('ip_address')
                    mac_address = printer_data.get('mac_address')
                    serial_number = printer_data.get('serial_number')

                    if not ip_address:
                        errors.append(f"Impresora sin IP address: {printer_data}")
                        continue

                    # Buscar impresora existente en ESTA ubicación
                    # Prioridad: 1) MAC address, 2) Serial number, 3) IP address
                    printer = None

                    # Intento 1: Buscar por MAC address (más confiable)
                    if mac_address:
                        printer = request.env['printer.device'].sudo().search([
                            ('location_id', '=', location.id),
                            ('mac_address', '=', mac_address)
                        ], limit=1)

                    # Intento 2: Si no se encontró por MAC, buscar por serial number
                    if not printer and serial_number:
                        printer = request.env['printer.device'].sudo().search([
                            ('location_id', '=', location.id),
                            ('serial_number', '=', serial_number)
                        ], limit=1)

                    # Intento 3: Si no se encontró por MAC ni serial, buscar por IP (fallback)
                    if not printer:
                        printer = request.env['printer.device'].sudo().search([
                            ('location_id', '=', location.id),
                            ('ip_address', '=', ip_address)
                        ], limit=1)

                    # Preparar valores
                    values = self._prepare_printer_values(printer_data, location)

                    if printer:
                        # Actualizar impresora existente
                        printer.write(values)
                        updated += 1
                        _logger.info(
                            f"Impresora actualizada: {printer.name} "
                            f"({printer.ip_address}) en {location.name}"
                        )
                    else:
                        # Crear nueva impresora
                        new_printer = request.env['printer.device'].sudo().create(values)
                        created += 1
                        _logger.info(
                            f"Impresora creada: {new_printer.name} "
                            f"({new_printer.ip_address}) en {location.name}"
                        )

                except Exception as e:
                    error_msg = f"Error procesando impresora {printer_data.get('ip_address', 'unknown')}: {str(e)}"
                    _logger.error(error_msg)
                    errors.append(error_msg)
                    continue

            # Actualizar última sincronización de la ubicación
            location.write({
                'last_sync': fields.Datetime.now(),
                'sync_status': 'success' if not errors else 'error'
            })

            response = {
                'status': 'success',
                'location': location.name,
                'partner': location.partner_id.name,
                'created': created,
                'updated': updated,
                'total': len(printers_data),
                'processed': created + updated
            }

            if errors:
                response['errors'] = errors
                response['status'] = 'partial_success'

            return response

        except Exception as e:
            _logger.error(f"Error crítico sincronizando impresoras: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/api/printer/sync/readings', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_location_token
    def sync_readings(self, **kwargs):
        """
        Endpoint para sincronizar lecturas de contadores.

        Soporta DOS formatos de payload:

        Formato 1 - Campos directos (PrintServer legacy):
        {
            "readings": [
                {
                    "printer_ip": "10.0.0.14",
                    "timestamp": "2025-10-13T10:30:00",
                    "status": "online",
                    "total_pages": 12345,
                    "mono_pages": 10000,
                    "color_pages": 2345
                }
            ]
        }

        Formato 2 - Con OIDs dinámicos:
        {
            "readings": [
                {
                    "printer_ip": "10.0.0.14",
                    "timestamp": "2025-10-13T10:30:00",
                    "status": "online",
                    "counters": [
                        {"oid": "1.3.6.1.2.1.43.10.2.1.4.1.1", "value": 12345}
                    ]
                }
            ]
        }
        """
        try:
            data = json.loads(request.httprequest.data)
            readings_data = data.get('readings', [])

            location = request.printer_location

            created = 0
            skipped = 0
            errors = []

            # Mapeo de campos legacy a códigos de contador
            LEGACY_COUNTER_MAP = {
                'total_pages': ('total', 'Total de Páginas'),
                'mono_pages': ('mono', 'Páginas Monocromáticas'),
                'color_pages': ('color', 'Páginas a Color'),
                'total_simplex': ('simplex', 'Total Simplex'),
                'total_duplex': ('duplex', 'Total Duplex'),
                'total_scans': ('scans', 'Total Escaneos'),
                'total_copies': ('copies', 'Total Copias'),
            }

            for reading_data in readings_data:
                try:
                    # Identificar impresora por IP (debe pertenecer a esta ubicación)
                    printer_ip = reading_data.get('printer_ip')
                    if not printer_ip:
                        errors.append("Lectura sin printer_ip")
                        skipped += 1
                        continue

                    # Buscar impresora en ESTA ubicación
                    printer = request.env['printer.device'].sudo().search([
                        ('location_id', '=', location.id),
                        ('ip_address', '=', printer_ip)
                    ], limit=1)

                    if not printer:
                        _logger.warning(
                            f"Impresora {printer_ip} no encontrada en ubicación {location.name}"
                        )
                        skipped += 1
                        continue

                    # Crear lectura (solo timestamp y status)
                    reading_values = {
                        'printer_id': printer.id,
                        'timestamp': parse_timestamp(reading_data.get('timestamp')),
                        'status': reading_data.get('status', 'unknown'),
                    }

                    reading = request.env['printer.reading'].sudo().create(reading_values)

                    # Procesar contadores
                    counters_to_create = []

                    # Formato 1: Campos legacy (total_pages, mono_pages, etc.)
                    has_legacy_counters = False
                    for field_name, (code, name) in LEGACY_COUNTER_MAP.items():
                        if field_name in reading_data and reading_data[field_name] is not None:
                            has_legacy_counters = True
                            value = reading_data[field_name]

                            # Buscar o crear tipo de contador por código
                            counter_type = request.env['counter.type'].sudo().search([
                                ('code', '=', code)
                            ], limit=1)

                            if not counter_type:
                                counter_type = request.env['counter.type'].sudo().create({
                                    'name': name,
                                    'code': code,
                                    'oid': f'legacy.{code}',
                                    'active': True,
                                })
                                _logger.info(f"Tipo de contador legacy creado: {code}")

                            counters_to_create.append({
                                'reading_id': reading.id,
                                'counter_type_id': counter_type.id,
                                'value': int(value) if value else 0,
                            })

                    # Formato 2: Con OIDs dinámicos
                    if 'counters' in reading_data and not has_legacy_counters:
                        for counter_data in reading_data.get('counters', []):
                            oid = counter_data.get('oid')
                            value = counter_data.get('value', 0)

                            if not oid:
                                continue

                            # Buscar o crear tipo de contador por OID
                            counter_type = request.env['counter.type'].sudo().search([
                                ('oid', '=', oid)
                            ], limit=1)

                            if not counter_type:
                                counter_type = request.env['counter.type'].sudo().create({
                                    'name': f'Contador {oid}',
                                    'code': f'auto_{oid.replace(".", "_")}',
                                    'oid': oid,
                                    'active': True,
                                })
                                _logger.info(f"Tipo de contador creado automáticamente: {oid}")

                            counters_to_create.append({
                                'reading_id': reading.id,
                                'counter_type_id': counter_type.id,
                                'value': int(value) if value else 0,
                            })

                    # Crear todos los contadores de una vez
                    if counters_to_create:
                        request.env['printer.reading.counter'].sudo().create(counters_to_create)

                    created += 1

                    # Actualizar last_reading en impresora
                    printer.write({
                        'last_reading': reading_values['timestamp'],
                        'status': reading_values['status']
                    })

                except Exception as e:
                    error_msg = f"Error procesando lectura de {reading_data.get('printer_ip', 'unknown')}: {str(e)}"
                    _logger.error(error_msg)
                    errors.append(error_msg)
                    continue

            response = {
                'status': 'success',
                'location': location.name,
                'created': created,
                'skipped': skipped,
                'total': len(readings_data)
            }

            if errors:
                response['errors'] = errors
                response['status'] = 'partial_success'

            return response

        except Exception as e:
            _logger.error(f"Error crítico sincronizando lecturas: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/api/printer/sync/consumables', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_location_token
    def sync_consumables(self, **kwargs):
        """
        Endpoint para sincronizar consumibles

        Solo se procesan consumibles de impresoras que pertenecen a la ubicación del token.

        Payload esperado:
        {
            "consumables": [
                {
                    "printer_ip": "10.0.0.14",
                    "supply_name": "Toner Negro",
                    "supply_type": "toner",
                    "color": "black",
                    "level_percent": 75.5,
                    "status": "ok",
                    "model": "T6710"
                }
            ]
        }
        """
        try:
            data = json.loads(request.httprequest.data)
            consumables_data = data.get('consumables', [])

            location = request.printer_location

            created = 0
            updated = 0
            skipped = 0
            errors = []

            for consumable_data in consumables_data:
                try:
                    printer_ip = consumable_data.get('printer_ip')
                    supply_name = consumable_data.get('supply_name')

                    if not printer_ip or not supply_name:
                        errors.append("Consumible sin printer_ip o supply_name")
                        skipped += 1
                        continue

                    # Buscar impresora en ESTA ubicación
                    printer = request.env['printer.device'].sudo().search([
                        ('location_id', '=', location.id),
                        ('ip_address', '=', printer_ip)
                    ], limit=1)

                    if not printer:
                        _logger.warning(
                            f"Impresora {printer_ip} no encontrada en ubicación {location.name}"
                        )
                        skipped += 1
                        continue

                    # Buscar consumible existente
                    consumable = request.env['printer.consumable'].sudo().search([
                        ('printer_id', '=', printer.id),
                        ('supply_name', '=', supply_name)
                    ], limit=1)

                    values = {
                        'printer_id': printer.id,
                        'supply_name': supply_name,
                        'supply_type': consumable_data.get('supply_type'),
                        'color': consumable_data.get('color'),
                        'level_percent': consumable_data.get('level_percent'),
                        'model': consumable_data.get('model'),
                        'last_update': fields.Datetime.now(),
                    }

                    # No enviar status si no viene, dejar que el modelo lo calcule
                    if 'status' in consumable_data:
                        values['status'] = consumable_data['status']

                    if consumable:
                        consumable.write(values)
                        updated += 1
                    else:
                        request.env['printer.consumable'].sudo().create(values)
                        created += 1

                except Exception as e:
                    error_msg = f"Error procesando consumible {consumable_data.get('supply_name', 'unknown')}: {str(e)}"
                    _logger.error(error_msg)
                    errors.append(error_msg)
                    continue

            response = {
                'status': 'success',
                'location': location.name,
                'created': created,
                'updated': updated,
                'skipped': skipped,
                'total': len(consumables_data)
            }

            if errors:
                response['errors'] = errors
                response['status'] = 'partial_success'

            return response

        except Exception as e:
            _logger.error(f"Error crítico sincronizando consumibles: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    @http.route('/api/printer/sync/alerts', type='json', auth='none', methods=['POST'], csrf=False)
    @validate_location_token
    def sync_alerts(self, **kwargs):
        """
        Endpoint para sincronizar alertas

        Solo se procesan alertas de impresoras que pertenecen a la ubicación del token.

        Payload esperado:
        {
            "alerts": [
                {
                    "printer_ip": "10.0.0.14",
                    "alert_type": "consumable_low",
                    "severity": "medium",
                    "message": "Toner Negro bajo: 15%",
                    "timestamp": "2025-10-13T10:30:00",
                    "resolved": false
                }
            ]
        }
        """
        try:
            data = json.loads(request.httprequest.data)
            alerts_data = data.get('alerts', [])

            location = request.printer_location

            created = 0
            skipped = 0
            duplicates = 0
            errors = []

            for alert_data in alerts_data:
                try:
                    printer_ip = alert_data.get('printer_ip')
                    if not printer_ip:
                        errors.append("Alerta sin printer_ip")
                        skipped += 1
                        continue

                    # Buscar impresora en ESTA ubicación
                    printer = request.env['printer.device'].sudo().search([
                        ('location_id', '=', location.id),
                        ('ip_address', '=', printer_ip)
                    ], limit=1)

                    if not printer:
                        _logger.warning(
                            f"Impresora {printer_ip} no encontrada en ubicación {location.name}"
                        )
                        skipped += 1
                        continue

                    # Verificar si ya existe una alerta similar reciente (últimas 24 horas)
                    timestamp = alert_data.get('timestamp')
                    if timestamp:
                        from datetime import timedelta
                        parsed_timestamp = parse_timestamp(timestamp)
                        time_threshold = parsed_timestamp - timedelta(hours=24)
                    else:
                        from datetime import timedelta
                        parsed_timestamp = datetime.now()
                        time_threshold = datetime.now() - timedelta(hours=24)
                        timestamp = parsed_timestamp

                    existing = request.env['printer.alert'].sudo().search([
                        ('printer_id', '=', printer.id),
                        ('alert_type', '=', alert_data.get('alert_type')),
                        ('message', '=', alert_data.get('message')),
                        ('timestamp', '>=', time_threshold),
                        ('resolved', '=', False)
                    ], limit=1)

                    if existing:
                        duplicates += 1
                        continue

                    # Crear alerta
                    alert_values = {
                        'printer_id': printer.id,
                        'alert_type': alert_data.get('alert_type', 'other'),
                        'severity': normalize_severity(alert_data.get('severity', 'medium')),
                        'message': alert_data.get('message'),
                        'timestamp': parsed_timestamp,
                        'resolved': alert_data.get('resolved', False),
                        'resolved_at': alert_data.get('resolved_at'),
                    }

                    request.env['printer.alert'].sudo().create(alert_values)
                    created += 1

                except Exception as e:
                    error_msg = f"Error procesando alerta para {alert_data.get('printer_ip', 'unknown')}: {str(e)}"
                    _logger.error(error_msg)
                    errors.append(error_msg)
                    continue

            response = {
                'status': 'success',
                'location': location.name,
                'created': created,
                'duplicates': duplicates,
                'skipped': skipped,
                'total': len(alerts_data)
            }

            if errors:
                response['errors'] = errors
                response['status'] = 'partial_success'

            return response

        except Exception as e:
            _logger.error(f"Error crítico sincronizando alertas: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e)
            }

    def _prepare_printer_values(self, data, location):
        """
        Prepara valores para crear/actualizar impresora

        Args:
            data: Datos de la impresora desde PrintServer
            location: Objeto printer.location al que pertenece la impresora

        Returns:
            dict: Valores preparados para create/write
        """
        values = {
            'location_id': location.id,
            'ip_address': data.get('ip_address'),
            'mac_address': data.get('mac_address'),
            'serial_number': data.get('serial_number'),
            'model': data.get('model'),
            'manufacturer': data.get('manufacturer'),
            'hostname': data.get('hostname'),
            'location': data.get('location'),  # Campo de texto libre legacy
            'department': data.get('department'),
            'status': data.get('status', 'unknown'),
            'is_active': data.get('is_active', True),
            'community_string': data.get('community_string', 'public'),
            'snmp_version': data.get('snmp_version', '2c'),
            'last_seen': data.get('last_seen') or fields.Datetime.now(),
            'last_sync': fields.Datetime.now(),
            'sync_status': 'synced',
        }

        # Eliminar valores None/False que no queremos actualizar
        return {k: v for k, v in values.items() if v is not None}

    @http.route('/api/printer/health', type='http', auth='none', methods=['GET'], csrf=False)
    def health_check(self):
        """
        Health check endpoint - Sin autenticación

        Returns información básica del servicio
        """
        return Response(
            json.dumps({
                'status': 'ok',
                'service': 'Odoo Printer Monitor API',
                'version': '2.0.0',
                'api_type': 'location_token_based',
                'authentication': 'X-Location-Token header required for sync endpoints'
            }),
            status=200,
            mimetype='application/json'
        )

    @http.route('/api/printer/location/info', type='http', auth='none', methods=['GET'], csrf=False)
    def location_info(self):
        """
        Endpoint para verificar información de una ubicación con su token

        Header requerido:
            X-Location-Token: <token>

        Returns información de la ubicación y estadísticas
        """
        location_token = request.httprequest.headers.get('X-Location-Token')

        if not location_token:
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'X-Location-Token header requerido'
                }),
                status=401,
                mimetype='application/json'
            )

        location = request.env['printer.location'].sudo().search([
            ('access_token', '=', location_token)
        ], limit=1)

        if not location:
            return Response(
                json.dumps({
                    'status': 'error',
                    'message': 'Token no válido'
                }),
                status=403,
                mimetype='application/json'
            )

        return Response(
            json.dumps({
                'status': 'success',
                'location': {
                    'id': location.id,
                    'name': location.name,
                    'partner': location.partner_id.name,
                    'is_active': location.is_active,
                    'token_active': location.token_active,
                    'printer_count': location.printer_count,
                    'active_printer_count': location.active_printer_count,
                    'last_sync': location.last_sync.isoformat() if location.last_sync else None,
                    'sync_status': location.sync_status,
                    'token_requests_count': location.token_requests_count,
                }
            }),
            status=200,
            mimetype='application/json'
        )
