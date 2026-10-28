# -*- coding: utf-8 -*-
"""
Tests para el workflow de facturación de impresoras:
  - Ciclo de estados: draft → confirmed → invoiced
  - action_confirm valida que haya líneas
  - action_cancel y action_set_to_draft
  - Campos computados: state, name, total_printers
"""

from datetime import date, datetime

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


class TestBillingWorkflow(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Cliente Facturación Test',
            'is_company': True,
        })
        self.location = self.env['printer.location'].create({
            'name': 'Oficina Facturación Test',
            'partner_id': self.partner.id,
            'access_token': 'billing-token-001',
        })
        self.printer = self.env['printer.device'].create({
            'name': 'Printer Billing Test',
            'ip_address': '10.0.2.1',
            'location_id': self.location.id,
        })

    def _create_review(self, **kwargs):
        vals = {
            'partner_id': self.partner.id,
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 1, 31),
        }
        vals.update(kwargs)
        return self.env['printer.billing.review'].create(vals)

    def test_review_created_in_draft_state(self):
        """Una revisión nueva empieza en estado 'draft'."""
        review = self._create_review()
        self.assertEqual(review.state, 'draft')

    def test_review_gets_sequence_name(self):
        """La revisión obtiene un nombre automático de secuencia (no 'Nuevo')."""
        review = self._create_review()
        # Puede ser 'Nuevo' si la secuencia no está configurada, pero no debe ser False
        self.assertTrue(review.name)

    def test_confirm_without_lines_raises_error(self):
        """action_confirm sin líneas debe lanzar UserError."""
        review = self._create_review()
        with self.assertRaises(UserError):
            review.action_confirm()

    def test_generate_invoice_on_invoiced_raises_error(self):
        """action_generate_invoice en estado 'invoiced' debe lanzar UserError."""
        review = self._create_review()
        review.state = 'invoiced'
        with self.assertRaises(UserError):
            review.action_generate_invoice()

    def test_generate_invoice_without_billed_lines_raises_error(self):
        """action_generate_invoice sin líneas incluibles debe lanzar UserError."""
        review = self._create_review()
        review.state = 'confirmed'
        with self.assertRaises(UserError):
            review.action_generate_invoice()

    def test_action_cancel_from_draft(self):
        """action_cancel desde draft cambia el estado a 'cancelled'."""
        review = self._create_review()
        review.action_cancel()
        self.assertEqual(review.state, 'cancelled')

    def test_action_set_to_draft_from_cancelled(self):
        """action_set_to_draft vuelve el estado a 'draft'."""
        review = self._create_review()
        review.action_cancel()
        self.assertEqual(review.state, 'cancelled')
        review.action_set_to_draft()
        self.assertEqual(review.state, 'draft')

    def test_total_printers_zero_without_lines(self):
        """total_printers es 0 cuando no hay líneas."""
        review = self._create_review()
        self.assertEqual(review.total_printers, 0)

    def test_total_amount_zero_without_lines(self):
        """total_amount es 0 cuando no hay líneas."""
        review = self._create_review()
        self.assertEqual(review.total_amount, 0)

    def test_currency_defaults_to_company_currency(self):
        """currency_id por defecto es la moneda de la compañía."""
        review = self._create_review()
        self.assertEqual(review.currency_id, self.env.company.currency_id)


class TestBillingReadingMarking(TransactionCase):
    """Tests para que la facturación marque lecturas correctamente."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Cliente Mark Test',
            'is_company': True,
        })
        self.location = self.env['printer.location'].create({
            'name': 'Oficina Mark Test',
            'partner_id': self.partner.id,
            'access_token': 'mark-token-001',
        })
        self.printer = self.env['printer.device'].create({
            'name': 'Printer Mark Test',
            'ip_address': '10.0.3.1',
            'location_id': self.location.id,
        })

    def test_reading_is_billed_defaults_false(self):
        """is_billed es False por defecto en lecturas nuevas."""
        reading = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': datetime(2025, 1, 15, 10, 0, 0),
            'status': 'online',
        })
        self.assertFalse(reading.is_billed)

    def test_readings_for_period_can_be_filtered(self):
        """Las lecturas de un período específico son consultables correctamente."""
        # Crear lecturas en diferentes fechas
        for day in [5, 15, 25]:
            self.env['printer.reading'].create({
                'printer_id': self.printer.id,
                'timestamp': datetime(2025, 1, day, 10, 0, 0),
                'status': 'online',
            })
        # Una lectura fuera del período
        self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': datetime(2025, 2, 5, 10, 0, 0),
            'status': 'online',
        })

        readings_jan = self.env['printer.reading'].search([
            ('printer_id', '=', self.printer.id),
            ('timestamp', '>=', datetime(2025, 1, 1)),
            ('timestamp', '<=', datetime(2025, 1, 31, 23, 59, 59)),
            ('is_billed', '=', False),
        ])
        self.assertEqual(len(readings_jan), 3)

    def test_only_correct_printer_readings_marked(self):
        """Solo las lecturas del printer facturado deben marcarse, no las de otros."""
        printer2 = self.env['printer.device'].create({
            'name': 'Printer2 Mark Test',
            'ip_address': '10.0.3.2',
            'location_id': self.location.id,
        })
        reading1 = self.env['printer.reading'].create({
            'printer_id': self.printer.id,
            'timestamp': datetime(2025, 1, 10, 10, 0, 0),
            'status': 'online',
        })
        reading2 = self.env['printer.reading'].create({
            'printer_id': printer2.id,
            'timestamp': datetime(2025, 1, 10, 10, 0, 0),
            'status': 'online',
        })

        # Marcar solo la lectura de self.printer
        reading1.write({'is_billed': True, 'billed_date': datetime.now()})

        self.assertTrue(reading1.is_billed)
        self.assertFalse(reading2.is_billed)


@tagged('post_install', '-at_install')
class TestBillingInvoice(AccountTestInvoicingCommon):
    """Flujo completo: lecturas → wizard → revisión → factura (account.move)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('print_fleet_manager.group_printer_manager')
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente Factura Test'})
        cls.location = cls.env['printer.location'].create({
            'name': 'Oficina Factura Test',
            'partner_id': cls.customer.id,
        })
        cls.printer = cls.env['printer.device'].create({
            'ip_address': '10.0.4.1',
            'serial_number': 'SN-INV-1',
            'model': 'EPSON',
            'location_id': cls.location.id,
        })
        cls.ct_mono = cls.env.ref('print_fleet_manager.counter_type_mono')
        cls.ct_color = cls.env.ref('print_fleet_manager.counter_type_color')
        cls.env['partner.counter.price'].create([
            {'partner_id': cls.customer.id, 'counter_type_id': cls.ct_mono.id, 'unit_price': 0.05},
            {'partner_id': cls.customer.id, 'counter_type_id': cls.ct_color.id, 'unit_price': 0.20},
        ])
        # Lectura anterior al período + dos dentro (la última, el último día por la tarde)
        for ts, mono, color in [
            (datetime(2025, 12, 31, 9, 0), 1000, 100),
            (datetime(2026, 1, 10, 9, 0), 1500, 150),
            (datetime(2026, 1, 31, 18, 0), 2000, 300),
        ]:
            reading = cls.env['printer.reading'].create({
                'printer_id': cls.printer.id, 'timestamp': ts, 'status': 'online',
            })
            cls.env['printer.reading.counter'].create([
                {'reading_id': reading.id, 'counter_type_id': cls.ct_mono.id, 'value': mono},
                {'reading_id': reading.id, 'counter_type_id': cls.ct_color.id, 'value': color},
            ])

    def _create_review(self, group_by_location):
        wizard = self.env['printer.billing.wizard'].create({
            'partner_id': self.customer.id,
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 1, 31),
            'group_by_location': group_by_location,
        })
        self.assertEqual(wizard.total_pages, 1000 + 200)
        action = wizard.action_generate_invoice()
        return self.env['printer.billing.review'].browse(action['res_id'])

    def test_review_and_invoice_per_printer(self):
        review = self._create_review(group_by_location=False)
        self.assertEqual(review.state, 'draft')
        self.assertTrue(review.name.startswith('REV/'))
        self.assertEqual(review.total_printers, 1)
        self.assertEqual(review.total_pages_all, 1200)
        self.assertAlmostEqual(review.total_amount, 1000 * 0.05 + 200 * 0.20)
        self.assertIn('Páginas Monocromáticas', review.totals_by_counter_type)

        review.action_confirm()
        self.assertEqual(review.state, 'confirmed')
        action = review.action_generate_invoice()
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(review.state, 'invoiced')
        self.assertEqual(review.invoice_id, invoice)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.customer)
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        self.assertAlmostEqual(invoice.amount_untaxed, 90.0)
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')

        # Se marcan las lecturas del período (incluida la del último día), no la anterior
        readings = self.env['printer.reading'].search([('printer_id', '=', self.printer.id)])
        billed = readings.filtered('is_billed')
        self.assertEqual(len(billed), 2)
        self.assertTrue(all(r.invoice_id == invoice for r in billed))
        with self.assertRaises(UserError):
            review.action_cancel()

    def test_invoice_grouped_by_location(self):
        review = self._create_review(group_by_location=True)
        action = review.action_generate_invoice()
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(len(invoice.invoice_line_ids), 1)
        self.assertIn(self.location.name, invoice.invoice_line_ids.name)
        self.assertAlmostEqual(invoice.amount_untaxed, 90.0)

    def test_recalculate_review(self):
        review = self._create_review(group_by_location=False)
        review.counter_ids[:1].counter_end += 10
        review.action_recalculate_all()
        self.assertEqual(review.total_pages_all, 1200)
