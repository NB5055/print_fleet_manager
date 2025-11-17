# -*- coding: utf-8 -*-
"""
Wizard de Revisión de Facturación
Permite revisar y editar contadores antes de generar factura
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PrinterBillingReviewWizard(models.TransientModel):
    _name = 'printer.billing.review.wizard'
    _description = 'Revisión de Facturación de Impresoras'

    # Datos del Cliente y Período
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        readonly=True
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        readonly=True
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain=[('type', '=', 'service')],
        help='Producto a usar en la factura'
    )

    # Opciones
    group_by_location = fields.Boolean(
        string='Agrupar por Ubicación',
        default=True
    )
    only_not_billed = fields.Boolean(
        string='Solo Lecturas No Facturadas',
        default=True
    )

    # Líneas Editables
    line_ids = fields.One2many(
        'printer.billing.review.wizard.line',
        'wizard_id',
        string='Impresoras'
    )

    # Totales Computados
    total_printers = fields.Integer(
        string='Total Impresoras',
        compute='_compute_totals'
    )
    total_pages_all = fields.Integer(
        string='Total Páginas',
        compute='_compute_totals'
    )
    total_mono_all = fields.Integer(
        string='Total Mono',
        compute='_compute_totals'
    )
    total_color_all = fields.Integer(
        string='Total Color',
        compute='_compute_totals'
    )

    @api.depends('line_ids', 'line_ids.total_pages', 'line_ids.include_in_invoice')
    def _compute_totals(self):
        """Calcula totales generales"""
        for wizard in self:
            included_lines = wizard.line_ids.filtered(lambda l: l.include_in_invoice)
            wizard.total_printers = len(included_lines)
            wizard.total_pages_all = sum(included_lines.mapped('total_pages'))
            wizard.total_mono_all = sum(included_lines.mapped('mono_pages'))
            wizard.total_color_all = sum(included_lines.mapped('color_pages'))

    def action_generate_invoice(self):
        """Genera la factura con los valores revisados"""
        self.ensure_one()

        # Filtrar solo líneas incluidas
        lines_to_bill = self.line_ids.filtered(lambda l: l.include_in_invoice and l.total_pages > 0)

        if not lines_to_bill:
            raise UserError("No hay impresoras con páginas para facturar")

        # Crear factura
        invoice_vals = {
            'partner_id': self.partner_id.id,
            'move_type': 'out_invoice',
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': []
        }

        if self.group_by_location:
            # Agrupar por ubicación
            by_location = {}
            for line in lines_to_bill:
                location_name = line.location_name or 'Sin ubicación'
                if location_name not in by_location:
                    by_location[location_name] = {
                        'total_pages': 0,
                        'mono_pages': 0,
                        'color_pages': 0,
                        'printers': []
                    }
                by_location[location_name]['total_pages'] += line.total_pages
                by_location[location_name]['mono_pages'] += line.mono_pages
                by_location[location_name]['color_pages'] += line.color_pages
                by_location[location_name]['printers'].append(line.printer_name)

            # Crear líneas de factura por ubicación
            for location_name, data in by_location.items():
                description = f"Servicio de impresión - {location_name}\n"
                description += f"Período: {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}\n"
                description += f"Total páginas: {data['total_pages']:,}\n"
                description += f"  • Monocromáticas: {data['mono_pages']:,}\n"
                description += f"  • Color: {data['color_pages']:,}\n"
                description += f"Impresoras: {', '.join(data['printers'])}"

                invoice_vals['invoice_line_ids'].append((0, 0, {
                    'product_id': self.product_id.id,
                    'name': description,
                    'quantity': data['total_pages'],
                    'price_unit': self.product_id.list_price,
                }))

        else:
            # Línea por impresora
            for line in lines_to_bill:
                description = f"Servicio de impresión - {line.printer_name}\n"
                description += f"Ubicación: {line.location_name or 'Sin ubicación'}\n"
                description += f"Período: {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}\n"
                description += f"Contador inicial: {line.counter_start:,}\n"
                description += f"Contador final: {line.counter_end:,}\n"
                description += f"Total páginas: {line.total_pages:,}\n"
                description += f"  • Monocromáticas: {line.mono_pages:,}\n"
                description += f"  • Color: {line.color_pages:,}"

                if line.notes:
                    description += f"\nNotas: {line.notes}"

                invoice_vals['invoice_line_ids'].append((0, 0, {
                    'product_id': self.product_id.id,
                    'name': description,
                    'quantity': line.total_pages,
                    'price_unit': self.product_id.list_price,
                }))

        # Crear la factura
        invoice = self.env['account.move'].create(invoice_vals)

        # Marcar lecturas como facturadas si corresponde
        if self.only_not_billed:
            readings_to_mark = self.env['printer.reading'].search([
                ('partner_id', '=', self.partner_id.id),
                ('timestamp', '>=', self.date_from),
                ('timestamp', '<=', self.date_to),
                ('is_billed', '=', False)
            ])
            readings_to_mark.write({
                'is_billed': True,
                'invoice_id': invoice.id,
                'billed_date': fields.Datetime.now()
            })

        _logger.info(
            f"Factura generada: {invoice.name} para {self.partner_id.name} "
            f"({len(invoice.invoice_line_ids)} líneas, {self.total_pages_all:,} páginas)"
        )

        # Retornar acción para abrir la factura
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_recalculate_all(self):
        """Recalcula todos los contadores (útil si se editaron mal)"""
        self.ensure_one()

        # Obtener datos frescos
        usage_data = self.env['printer.reading'].calculate_usage_by_printer(
            self.partner_id.id,
            fields.Datetime.to_datetime(self.date_from),
            fields.Datetime.to_datetime(self.date_to)
        )

        # Actualizar líneas existentes
        for line in self.line_ids:
            printer_data = next((d for d in usage_data if d['printer'].id == line.printer_id.id), None)
            if printer_data:
                line.write({
                    'counter_start': printer_data['counter_start'],
                    'counter_end': printer_data['counter_end'],
                    'mono_start': printer_data['mono_start'],
                    'mono_end': printer_data['mono_end'],
                    'color_start': printer_data['color_start'],
                    'color_end': printer_data['color_end'],
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Contadores Recalculados',
                'message': 'Se han recalculado todos los contadores desde las lecturas originales.',
                'type': 'success',
                'sticky': False,
            }
        }
