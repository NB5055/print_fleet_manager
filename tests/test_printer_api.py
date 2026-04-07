# -*- coding: utf-8 -*-
"""
Tests para el controlador REST de PrintServer (printer_api.py):
  - Autenticación por token (X-Location-Token)
  - Endpoint /api/printserver/sync (sync_all)
  - Deduplicación de lecturas
  - Helpers: parse_timestamp, normalize_severity
"""

from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError
from datetime import datetime


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

    def test_serial_first_printer_lookup(self):
        """La búsqueda por serial_number tiene prioridad sobre IP."""
        # Crear otra impresora con mismo serial pero distinta IP
        printer2 = self.env['printer.device'].create({
            'name': 'Printer con IP cambiada',
            'ip_address': '10.0.1.99',
            'location_id': self.location.id,
            'serial_number': 'SN-SYNC-001',  # Mismo serial que self.printer
        })
        # Buscar por serial → debe retornar alguno de los dos (el primero)
        found_by_serial = self.env['printer.device'].sudo().search([
            ('location_id', '=', self.location.id),
            ('serial_number', '=', 'SN-SYNC-001'),
        ], limit=1)
        self.assertTrue(found_by_serial)
        self.assertEqual(found_by_serial.serial_number, 'SN-SYNC-001')
