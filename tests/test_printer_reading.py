# -*- coding: utf-8 -*-
"""
Tests para printer.reading:
  - Creación de lectura
  - Deduplicación (_find_duplicate_reading)
  - Cálculo de billing_period
  - Marcado como facturado
"""

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from datetime import datetime


class TestPrinterReading(TransactionCase):

    def setUp(self):
        super().setUp()
        # Crear partner y ubicación mínimos
        self.partner = self.env['res.partner'].create({
            'name': 'Test Client SA',
            'is_company': True,
        })
        self.location = self.env['printer.location'].create({
            'name': 'Oficina Central Test',
            'partner_id': self.partner.id,
            'access_token': 'test-token-001',
        })
        self.printer = self.env['printer.device'].create({
            'name': 'EPSON WF-3820 Test',
            'ip_address': '10.0.0.99',
            'location_id': self.location.id,
            'serial_number': 'SN-TEST-001',
        })

    def test_reading_creation(self):
        """Una lectura se crea correctamente con los campos obligatorios."""
        reading = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': datetime(2025, 1, 15, 10, 0, 0),
            'status': 'online',
        })
        self.assertTrue(reading.id)
        self.assertEqual(reading.printer_id, self.printer)
        self.assertEqual(reading.status, 'online')

    def test_billing_period_computed(self):
        """billing_period se calcula como YYYY-MM a partir del timestamp."""
        reading = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': datetime(2025, 3, 15, 8, 0, 0),
            'status': 'online',
        })
        self.assertEqual(reading.billing_period, '2025-03')

    def test_billing_period_different_months(self):
        """billing_period refleja correctamente distintos meses."""
        for month, expected in [(1, '2025-01'), (6, '2025-06'), (12, '2025-12')]:
            reading = self.env['printer.reading'].create({
                'printer_id': self.printer.id,
                'timestamp': datetime(2025, month, 1, 0, 0, 0),
                'status': 'online',
            })
            self.assertEqual(reading.billing_period, expected)

    def test_find_duplicate_reading_returns_existing(self):
        """_find_duplicate_reading retorna la lectura si existe mismo printer+timestamp."""
        ts = datetime(2025, 2, 20, 9, 0, 0)
        original = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': ts,
            'status': 'online',
        })
        found = self.env['printer.reading']._find_duplicate_reading(
            self.printer.id, ts
        )
        self.assertEqual(found.id, original.id)

    def test_find_duplicate_reading_returns_empty_for_new(self):
        """_find_duplicate_reading retorna vacío si no hay duplicado."""
        ts = datetime(2025, 2, 21, 9, 0, 0)
        found = self.env['printer.reading']._find_duplicate_reading(
            self.printer.id, ts
        )
        self.assertFalse(found)

    def test_find_duplicate_reading_different_printer(self):
        """_find_duplicate_reading no confunde lecturas de distintas impresoras."""
        ts = datetime(2025, 2, 22, 9, 0, 0)
        printer2 = self.env['printer.device'].create({
            'name': 'HP LaserJet Test',
            'ip_address': '10.0.0.100',
            'location_id': self.location.id,
        })
        self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': ts,
            'status': 'online',
        })
        # Buscar para printer2 → no debe encontrar la de printer
        found = self.env['printer.reading']._find_duplicate_reading(
            printer2.id, ts
        )
        self.assertFalse(found)

    def test_display_name_computed(self):
        """display_name incluye el nombre de la impresora y el timestamp."""
        ts = datetime(2025, 4, 1, 12, 0, 0)
        reading = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': ts,
            'status': 'online',
        })
        self.assertIn(self.printer.name, reading.display_name)

    def test_is_billed_default_false(self):
        """Las lecturas nuevas tienen is_billed=False por defecto."""
        reading = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': datetime(2025, 1, 1, 0, 0, 0),
            'status': 'online',
        })
        self.assertFalse(reading.is_billed)
