# -*- coding: utf-8 -*-
"""
Tests para el controlador REST de PrintServer (printer_api.py):
  - Autenticación por token (X-Location-Token)
  - Rutas /api/printer/* (HttpCase)
  - Deduplicación de lecturas
  - Helpers: parse_timestamp, normalize_severity
"""

import hashlib
import json
from datetime import datetime

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger


class TestPrinterApiHelpers(TransactionCase):
    """Tests unitarios para las funciones helper del controlador."""

    def _get_parse_timestamp(self):
        from odoo.addons.print_fleet_manager.controllers.printer_api import parse_timestamp
        return parse_timestamp

    def _get_normalize_severity(self):
        from odoo.addons.print_fleet_manager.controllers.printer_api import normalize_severity
        return normalize_severity

    def test_parse_timestamp_iso_with_microseconds(self):
        """parse_timestamp debe manejar ISO con microsegundos."""
        parse_timestamp = self._get_parse_timestamp()
        result = parse_timestamp('2025-10-19T10:57:00.161493')
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 10)
        self.assertEqual(result.day, 19)
        self.assertEqual(result.hour, 10)

    def test_parse_timestamp_iso_without_microseconds(self):
        """parse_timestamp debe manejar ISO sin microsegundos."""
        parse_timestamp = self._get_parse_timestamp()
        result = parse_timestamp('2025-10-19T10:57:00')
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2025)

    def test_parse_timestamp_odoo_format(self):
        """parse_timestamp debe manejar formato Odoo estándar."""
        parse_timestamp = self._get_parse_timestamp()
        result = parse_timestamp('2025-10-19 10:57:00')
        self.assertIsInstance(result, datetime)

    def test_parse_timestamp_empty_returns_now(self):
        """parse_timestamp retorna datetime.now() si se pasa None o vacío."""
        parse_timestamp = self._get_parse_timestamp()
        before = datetime.now()
        result = parse_timestamp(None)
        after = datetime.now()
        self.assertIsInstance(result, datetime)
        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, after)

    def test_normalize_severity_info_to_low(self):
        """info → low"""
        normalize_severity = self._get_normalize_severity()
        self.assertEqual(normalize_severity('info'), 'low')

    def test_normalize_severity_warning_to_medium(self):
        """warning → medium"""
        normalize_severity = self._get_normalize_severity()
        self.assertEqual(normalize_severity('warning'), 'medium')

    def test_normalize_severity_error_to_high(self):
        """error → high"""
        normalize_severity = self._get_normalize_severity()
        self.assertEqual(normalize_severity('error'), 'high')

    def test_normalize_severity_critical_unchanged(self):
        """critical → critical"""
        normalize_severity = self._get_normalize_severity()
        self.assertEqual(normalize_severity('critical'), 'critical')

    @mute_logger('odoo.addons.print_fleet_manager.controllers.printer_api')
    def test_normalize_severity_unknown_defaults_medium(self):
        """Un valor desconocido debe devolver 'medium'."""
        normalize_severity = self._get_normalize_severity()
        self.assertEqual(normalize_severity('foobar'), 'medium')

    def test_normalize_severity_valid_values_unchanged(self):
        """Valores ya válidos (low, medium, high) no se modifican."""
        normalize_severity = self._get_normalize_severity()
        for val in ('low', 'medium', 'high'):
            self.assertEqual(normalize_severity(val), val)


class TestPrinterApiTokenAuth(TransactionCase):
    """Tests de autenticación por token de ubicación."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Cliente Token Test',
            'is_company': True,
        })
        self.location = self.env['printer.location'].create({
            'name': 'Ubicación Token Test',
            'partner_id': self.partner.id,
            'access_token': 'valid-token-abc123',
            'is_active': True,
        })

    def test_location_found_by_valid_token(self):
        """Una ubicación activa puede encontrarse por su access_token."""
        found = self.env['printer.location'].sudo().search([
            ('access_token', '=', 'valid-token-abc123'),
            ('is_active', '=', True),
        ], limit=1)
        self.assertTrue(found)
        self.assertEqual(found.id, self.location.id)

    def test_location_not_found_by_invalid_token(self):
        """Un token inexistente no retorna ubicación."""
        found = self.env['printer.location'].sudo().search([
            ('access_token', '=', 'invalid-token-xyz'),
            ('is_active', '=', True),
        ], limit=1)
        self.assertFalse(found)

    def test_inactive_location_not_returned(self):
        """Una ubicación inactiva no se retorna aunque el token sea correcto."""
        self.location.is_active = False
        found = self.env['printer.location'].sudo().search([
            ('access_token', '=', 'valid-token-abc123'),
            ('is_active', '=', True),
        ], limit=1)
        self.assertFalse(found)


class TestPrinterApiSyncReadings(TransactionCase):
    """Tests para la lógica de sincronización de lecturas."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Cliente Sync Test',
            'is_company': True,
        })
        self.location = self.env['printer.location'].create({
            'name': 'Ubicación Sync Test',
            'partner_id': self.partner.id,
            'access_token': 'sync-token-001',
        })
        self.printer = self.env['printer.device'].create({
            'name': 'Printer Sync Test',
            'ip_address': '10.0.1.1',
            'location_id': self.location.id,
            'serial_number': 'SN-SYNC-001',
        })

    def test_reading_deduplication_via_find_duplicate(self):
        """Dos llamadas al API con el mismo timestamp no deben crear duplicados."""
        ts = datetime(2025, 5, 10, 8, 0, 0)
        # Simula primer sync: crea la lectura
        reading = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': ts,
            'status': 'online',
        })
        # Simula segundo sync: _find_duplicate_reading debe retornar la existente
        dup = self.env['printer.reading']._find_duplicate_reading(
            self.printer.id, ts
        )
        self.assertEqual(dup.id, reading.id)

        # Solo hay una lectura para este printer+timestamp
        count = self.env['printer.reading'].search_count([
            ('printer_id', '=', self.printer.id),
            ('timestamp', '=', ts),
        ])
        self.assertEqual(count, 1)

    def test_serial_unique_per_location(self):
        """No puede haber dos impresoras con el mismo serial en una ubicación."""
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.env['printer.device'].create({
                'name': 'Printer con IP cambiada',
                'ip_address': '10.0.1.99',
                'location_id': self.location.id,
                'serial_number': 'SN-SYNC-001',  # Mismo serial que self.printer
            })

    def test_serial_first_printer_lookup(self):
        """La búsqueda por serial_number encuentra la impresora aunque cambie su IP."""
        # Otra impresora en la IP "nueva" de la primera (DHCP)
        self.env['printer.device'].create({
            'name': 'Otra impresora',
            'ip_address': '10.0.1.2',
            'location_id': self.location.id,
            'serial_number': 'SN-SYNC-002',
        })
        found_by_serial = self.env['printer.device'].sudo().search([
            ('location_id', '=', self.location.id),
            ('serial_number', '=', 'SN-SYNC-001'),
        ], limit=1)
        self.assertEqual(found_by_serial, self.printer)


class TestLocationTokenLookup(TransactionCase):
    """Búsqueda de ubicación por token (huella + comparación en tiempo constante)."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Cliente Hash Test'})
        self.location = self.env['printer.location'].create({
            'name': 'Ubicación Hash Test',
            'partner_id': self.partner.id,
        })

    def test_token_generated_and_hashed(self):
        token = self.location.access_token
        self.assertTrue(token)
        self.assertEqual(self.location.access_token_hash, hashlib.sha256(token.encode()).hexdigest())

    def test_lookup_by_token(self):
        Location = self.env['printer.location']
        self.assertEqual(Location._get_by_access_token(self.location.access_token), self.location)
        self.assertFalse(Location._get_by_access_token(self.location.access_token + 'x'))
        self.assertFalse(Location._get_by_access_token(''))
        self.assertFalse(Location._get_by_access_token(None))

    def test_lookup_inactive_location(self):
        Location = self.env['printer.location']
        self.location.is_active = False
        self.assertFalse(Location._get_by_access_token(self.location.access_token))
        self.assertEqual(
            Location._get_by_access_token(self.location.access_token, active_only=False),
            self.location,
        )

    def test_regenerate_token_invalidates_old(self):
        old_token = self.location.access_token
        self.location.action_generate_token()
        self.assertNotEqual(self.location.access_token, old_token)
        Location = self.env['printer.location']
        self.assertFalse(Location._get_by_access_token(old_token))
        self.assertEqual(Location._get_by_access_token(self.location.access_token), self.location)

    def test_duplicate_token_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['printer.location'].create({
                'name': 'Otra ubicación',
                'partner_id': self.partner.id,
                'access_token': self.location.access_token,
            })


@tagged('post_install', '-at_install')
class TestPrinterApiHttp(HttpCase):
    """Smoke test de las rutas HTTP/JSON del PrintServer."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente HTTP Test'})
        cls.location = cls.env['printer.location'].create({
            'name': 'Ubicación HTTP Test',
            'partner_id': cls.partner.id,
            'access_token': 'http-token-0123456789abcdef',
        })
        cls.token = 'http-token-0123456789abcdef'

    def _post(self, route, payload, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Location-Token'] = token
        self.env.flush_all()
        response = self.url_open(route, data=json.dumps(payload), headers=headers)
        self.env.invalidate_all()
        return response

    def _result(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertNotIn('error', body, body)
        return body['result']

    def test_health(self):
        response = self.url_open('/api/printer/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    @mute_logger('odoo.addons.print_fleet_manager.controllers.printer_api')
    def test_sync_requires_token(self):
        response = self._post('/api/printer/sync/printers', {'printers': []})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'error')

    def test_sync_rejects_invalid_token(self):
        with self.assertLogs('odoo.addons.print_fleet_manager.controllers.printer_api', 'WARNING') as logs:
            response = self._post('/api/printer/sync/printers', {'printers': []}, token='bad-token-ABCDEFGHIJ')
        self.assertEqual(response.status_code, 403)
        # El token (ni un prefijo) no debe aparecer en el log
        self.assertFalse(any('bad-token' in line for line in logs.output), logs.output)

    @mute_logger('odoo.addons.print_fleet_manager.controllers.printer_api')
    def test_sync_rejects_deactivated_token(self):
        self.location.token_active = False
        response = self._post('/api/printer/sync/printers', {'printers': []}, token=self.token)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'Token desactivado')

    @mute_logger('odoo.addons.print_fleet_manager.controllers.printer_api')
    def test_location_info(self):
        self.env.flush_all()
        response = self.url_open('/api/printer/location/info', headers={'X-Location-Token': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['location']['id'], self.location.id)
        response = self.url_open('/api/printer/location/info', headers={'X-Location-Token': 'nope'})
        self.assertEqual(response.status_code, 403)
        response = self.url_open('/api/printer/location/info')
        self.assertEqual(response.status_code, 401)

    @mute_logger('odoo.sql_db', 'odoo.addons.print_fleet_manager.controllers.printer_api')
    def test_full_sync_flow(self):
        # 1) Impresoras (cuerpo JSON plano, como lo envía PrintServer)
        result = self._result(self._post('/api/printer/sync/printers', {
            'printers': [
                {'ip_address': '10.9.0.1', 'serial_number': 'SN-HTTP-1', 'model': 'EPSON WF-6590',
                 'manufacturer': 'EPSON', 'status': 'online'},
                {'ip_address': '10.9.0.2', 'serial_number': 'SN-HTTP-2', 'model': 'HP M404'},
                {'serial_number': 'SIN-IP'},
            ],
            'sync_timestamp': '2026-10-27T10:00:00',
        }, token=self.token))
        self.assertEqual(result['created'], 2)
        self.assertEqual(result['status'], 'partial_success')
        printer = self.env['printer.device'].search([('serial_number', '=', 'SN-HTTP-1')])
        self.assertEqual(printer.location_id, self.location)
        self.assertEqual(self.location.token_requests_count, 1)

        # Re-sincronizar: la impresora 2 cambió de IP y choca con la 1 -> error
        # aislado (savepoint) sin abortar el lote
        result = self._result(self._post('/api/printer/sync/printers', {
            'printers': [
                {'ip_address': '10.9.0.1', 'serial_number': 'SN-HTTP-2'},
                {'ip_address': '10.9.0.1', 'serial_number': 'SN-HTTP-1', 'model': 'EPSON WF-6590 v2'},
            ],
        }, token=self.token))
        self.assertEqual(result['updated'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(printer.model, 'EPSON WF-6590 v2')

        # 2) Lecturas: formato legacy y formato OID; la repetida se omite
        payload = {'readings': [
            {'printer_serial': 'SN-HTTP-1', 'timestamp': '2026-10-01T08:00:00.123456',
             'status': 'online', 'total_pages': 1000, 'mono_pages': 800, 'color_pages': 200},
            {'printer_ip': '10.9.0.2', 'timestamp': '2026-10-01T08:00:00', 'status': 'online',
             'counters': [{'oid': '1.3.6.1.2.1.43.10.2.1.4.1.1', 'value': 500},
                          {'oid': '1.3.6.1.4.1.99999.1', 'value': 7}]},
            {'printer_ip': '10.9.9.9', 'timestamp': '2026-10-01T08:00:00'},
        ]}
        result = self._result(self._post('/api/printer/sync/readings', payload, token=self.token))
        self.assertEqual(result['created'], 2)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(printer.total_pages, 1000)
        self.assertEqual(printer.color_pages, 200)
        self.assertTrue(self.env['counter.type'].search([('oid', '=', '1.3.6.1.4.1.99999.1')]))
        result = self._result(self._post('/api/printer/sync/readings', payload, token=self.token))
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['skipped'], 3)

        # 3) Consumibles
        result = self._result(self._post('/api/printer/sync/consumables', {'consumables': [
            {'printer_ip': '10.9.0.1', 'supply_name': 'Toner Negro', 'supply_type': 'toner',
             'color': 'black', 'level_percent': 8.0},
        ]}, token=self.token))
        self.assertEqual(result['created'], 1)
        result = self._result(self._post('/api/printer/sync/consumables', {'consumables': [
            {'printer_ip': '10.9.0.1', 'supply_name': 'Toner Negro', 'level_percent': 5.0},
        ]}, token=self.token))
        self.assertEqual(result['updated'], 1)
        consumable = printer.consumable_ids
        self.assertEqual(consumable.status, 'critical')
        self.assertTrue(consumable.needs_replacement)
        self.assertIn(consumable, self.env['printer.consumable'].search([('needs_replacement', '=', True)]))

        # 4) Alertas (con deduplicación)
        alert_payload = {'alerts': [
            {'printer_ip': '10.9.0.1', 'alert_type': 'paper_jam', 'severity': 'error',
             'message': 'Atasco bandeja 1', 'timestamp': '2026-10-27T09:00:00'},
        ]}
        result = self._result(self._post('/api/printer/sync/alerts', alert_payload, token=self.token))
        self.assertEqual(result['created'], 1)
        result = self._result(self._post('/api/printer/sync/alerts', alert_payload, token=self.token))
        self.assertEqual(result['duplicates'], 1)
        alert = printer.alert_ids
        self.assertEqual(alert.severity, 'high')
        self.assertIn(alert, self.env['printer.alert'].search([('is_active', '=', True)]))
        self.assertNotIn(alert, self.env['printer.alert'].search([('is_active', '=', False)]))

    def test_jsonrpc_envelope_accepted(self):
        """Un cliente que envíe el sobre JSON-RPC también funciona."""
        result = self._result(self._post('/api/printer/sync/printers', {
            'jsonrpc': '2.0', 'method': 'call',
            'params': {'printers': [{'ip_address': '10.9.1.1', 'serial_number': 'SN-RPC-1'}]},
        }, token=self.token))
        self.assertEqual(result['created'], 1)
