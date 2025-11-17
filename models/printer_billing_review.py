# -*- coding: utf-8 -*-
"""
Revisión de Facturación de Impresoras (PERSISTENTE)
Guarda historial completo de revisiones y facturación
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PrinterBillingReview(models.Model):
    _name = 'printer.billing.review'
    _description = 'Revisión de Facturación de Impresoras'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    # Nombre automático
    name = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo',
        tracking=True
    )

    # Estado
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('invoiced', 'Facturado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True, index=True)

    # Datos del Cliente y Período
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        tracking=True,
        index=True
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        tracking=True
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        tracking=True
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
        'printer.billing.review.line',
        'review_id',
        string='Impresoras'
    )

    # Todos los Contadores (vista plana)
    counter_ids = fields.One2many(
        'printer.billing.review.counter',
        'review_id',
        string='Todos los Contadores',
        help='Vista plana de todos los contadores de todas las impresoras'
    )

    # Factura Generada
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura Generada',
        readonly=True,
        copy=False,
        tracking=True
    )
    invoice_state = fields.Selection(
        related='invoice_id.state',
        string='Estado de Factura',
        store=True
    )

    # Totales Computados
    total_printers = fields.Integer(
        string='Total Impresoras',
        compute='_compute_totals',
        store=True
    )
    total_pages_all = fields.Integer(
        string='Total Páginas',
        compute='_compute_totals',
        store=True
    )
    total_amount = fields.Monetary(
        string='Monto Total',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )

    # Totales por Tipo de Contador (HTML)
    totals_by_counter_type = fields.Html(
        string='Totales por Tipo de Contador',
        compute='_compute_totals_by_counter_type'
    )

    # Moneda
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    # Notas
    notes = fields.Text(string='Notas Internas')

    # Auditoría
    user_id = fields.Many2one(
        'res.users',
        string='Creado Por',
        default=lambda self: self.env.user,
        readonly=True
    )
    confirmed_by = fields.Many2one(
        'res.users',
        string='Confirmado Por',
        readonly=True,
        copy=False
    )
    confirmed_date = fields.Datetime(
        string='Fecha de Confirmación',
        readonly=True,
        copy=False
    )
    invoiced_date = fields.Datetime(
        string='Fecha de Facturación',
        readonly=True,
        copy=False
    )

    @api.model
    def create(self, vals):
        """Genera secuencia automática para el nombre"""
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code('printer.billing.review') or 'Nuevo'
        return super(PrinterBillingReview, self).create(vals)

    @api.depends('line_ids', 'line_ids.total_pages', 'line_ids.estimated_amount', 'line_ids.include_in_invoice')
    def _compute_totals(self):
        """Calcula totales generales desde líneas con contadores dinámicos"""
        for review in self:
            included_lines = review.line_ids.filtered(lambda l: l.include_in_invoice)
            review.total_printers = len(included_lines)
            review.total_pages_all = sum(included_lines.mapped('total_pages'))

            # Calcular monto total como suma de montos estimados de líneas
            # (cada línea suma subtotales de sus contadores)
            review.total_amount = sum(included_lines.mapped('estimated_amount'))

    @api.depends('counter_ids', 'counter_ids.total_pages', 'counter_ids.subtotal', 'line_ids.include_in_invoice')
    def _compute_totals_by_counter_type(self):
        """Genera tabla HTML con totales por tipo de contador"""
        for review in self:
            # Filtrar contadores de líneas incluidas en factura
            included_lines = review.line_ids.filtered(lambda l: l.include_in_invoice)
            included_counters = review.counter_ids.filtered(
                lambda c: c.review_line_id.id in included_lines.ids
            )

            if not included_counters:
                review.totals_by_counter_type = '<p>No hay contadores para mostrar</p>'
                continue

            # Agrupar por tipo de contador
            counter_totals = {}
            for counter in included_counters:
                counter_type = counter.counter_type_id
                if counter_type.id not in counter_totals:
                    counter_totals[counter_type.id] = {
                        'name': counter_type.name,
                        'code': counter_type.code,
                        'oid': counter_type.oid,
                        'total_pages': 0,
                        'unit_price': counter_type.unit_price,
                        'subtotal': 0,
                        'printers_count': set()
                    }
                counter_totals[counter_type.id]['total_pages'] += counter.total_pages
                counter_totals[counter_type.id]['subtotal'] += counter.subtotal
                counter_totals[counter_type.id]['printers_count'].add(counter.printer_id.id)

            # Generar HTML
            html = '''
                <table class="table table-sm table-striped">
                    <thead>
                        <tr>
                            <th>Tipo de Contador</th>
                            <th>Código</th>
                            <th class="text-end">Impresoras</th>
                            <th class="text-end">Total Páginas</th>
                            <th class="text-end">Precio Unit.</th>
                            <th class="text-end">Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
            '''

            total_pages_sum = 0
            total_amount_sum = 0

            for counter_data in sorted(counter_totals.values(), key=lambda x: x['name']):
                total_pages_sum += counter_data['total_pages']
                total_amount_sum += counter_data['subtotal']

                html += f'''
                    <tr>
                        <td><strong>{counter_data['name']}</strong></td>
                        <td><small class="text-muted">{counter_data['code']}</small></td>
                        <td class="text-end">{len(counter_data['printers_count'])}</td>
                        <td class="text-end">{counter_data['total_pages']:,}</td>
                        <td class="text-end">${counter_data['unit_price']:,.2f}</td>
                        <td class="text-end"><strong>${counter_data['subtotal']:,.2f}</strong></td>
                    </tr>
                '''

            # Fila de totales
            html += f'''
                    </tbody>
                    <tfoot>
                        <tr class="table-info">
                            <th colspan="3">TOTAL</th>
                            <th class="text-end">{total_pages_sum:,}</th>
                            <th></th>
                            <th class="text-end">${total_amount_sum:,.2f}</th>
                        </tr>
                    </tfoot>
                </table>
            '''

            review.totals_by_counter_type = html

    def action_confirm(self):
        """Confirma la revisión"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Debe tener al menos una impresora en la revisión")

        self.write({
            'state': 'confirmed',
            'confirmed_by': self.env.user.id,
            'confirmed_date': fields.Datetime.now()
        })

    def action_generate_invoice(self):
        """Genera la factura con los valores revisados"""
        self.ensure_one()

        if self.state == 'invoiced':
            raise UserError("Esta revisión ya tiene una factura generada")

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
                        'counters': {},  # {counter_type_name: total_pages}
                        'total_amount': 0,
                        'printers': []
                    }

                # Agregar contadores de esta línea
                for counter in line.counter_line_ids:
                    counter_name = counter.counter_name
                    if counter_name not in by_location[location_name]['counters']:
                        by_location[location_name]['counters'][counter_name] = {
                            'pages': 0,
                            'amount': 0
                        }
                    by_location[location_name]['counters'][counter_name]['pages'] += counter.total_pages
                    by_location[location_name]['counters'][counter_name]['amount'] += counter.subtotal

                by_location[location_name]['total_amount'] += line.estimated_amount
                by_location[location_name]['printers'].append(line.printer_name)

            # Crear líneas de factura por ubicación
            for location_name, data in by_location.items():
                description = f"Servicio de impresión - {location_name}\n"
                description += f"Período: {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}\n"
                description += f"Detalle de contadores:\n"

                total_quantity = 0
                for counter_name, counter_data in data['counters'].items():
                    description += f"  • {counter_name}: {counter_data['pages']:,} páginas\n"
                    total_quantity += counter_data['pages']

                description += f"Impresoras: {', '.join(data['printers'])}\n"
                description += f"Revisión: {self.name}"

                invoice_vals['invoice_line_ids'].append((0, 0, {
                    'name': description,
                    'quantity': 1,  # Cantidad 1, el precio ya incluye todo
                    'price_unit': data['total_amount'],
                }))

        else:
            # Línea por impresora
            for line in lines_to_bill:
                description = f"Servicio de impresión - {line.printer_name}\n"
                description += f"Ubicación: {line.location_name or 'Sin ubicación'}\n"
                description += f"Período: {self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')}\n"
                description += f"Detalle de contadores:\n"

                # Listar todos los contadores de esta línea
                for counter in line.counter_line_ids:
                    description += f"  • {counter.counter_name}: "
                    description += f"{counter.counter_start:,} → {counter.counter_end:,} "
                    description += f"({counter.total_pages:,} páginas)\n"

                description += f"Total: {line.total_pages:,} páginas\n"
                description += f"Revisión: {self.name}"

                if line.notes:
                    description += f"\nNotas: {line.notes}"

                invoice_vals['invoice_line_ids'].append((0, 0, {
                    'name': description,
                    'quantity': 1,  # Cantidad 1, el precio ya incluye todo
                    'price_unit': line.estimated_amount,
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

        # Actualizar revisión
        self.write({
            'state': 'invoiced',
            'invoice_id': invoice.id,
            'invoiced_date': fields.Datetime.now()
        })

        _logger.info(
            f"Factura generada: {invoice.name} desde revisión {self.name} para {self.partner_id.name} "
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

    def action_view_invoice(self):
        """Abre la factura generada"""
        self.ensure_one()
        if not self.invoice_id:
            raise UserError("No hay factura generada para esta revisión")

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_recalculate_all(self):
        """Recalcula todos los contadores desde las lecturas"""
        self.ensure_one()

        if self.state != 'draft':
            raise UserError("Solo se pueden recalcular revisiones en borrador")

        # Obtener datos frescos desde las lecturas
        usage_data = self.env['printer.reading'].calculate_usage_by_printer(
            self.partner_id.id,
            fields.Datetime.to_datetime(self.date_from),
            fields.Datetime.to_datetime(self.date_to)
        )

        # Eliminar líneas existentes y recrear
        self.line_ids.unlink()

        # Crear nuevas líneas con contadores dinámicos
        for printer_data in usage_data:
            # Crear la línea de la impresora
            line = self.env['printer.billing.review.line'].create({
                'review_id': self.id,
                'printer_id': printer_data['printer'].id,
                'include_in_invoice': True,
            })

            # Crear los contadores de esta línea
            for counter_data in printer_data.get('counters', []):
                # Obtener precio configurado para este cliente y tipo de contador
                unit_price = self.env['partner.counter.price'].get_price_for_partner_counter(
                    self.partner_id.id,
                    counter_data['counter_type_id']
                )

                self.env['printer.billing.review.counter'].create({
                    'review_line_id': line.id,
                    'counter_type_id': counter_data['counter_type_id'],
                    'counter_start': counter_data['counter_start'],
                    'counter_end': counter_data['counter_end'],
                    'unit_price': unit_price,  # Asignar precio del cliente (o 0.0)
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

    def action_cancel(self):
        """Cancela la revisión"""
        self.ensure_one()
        if self.state == 'invoiced':
            raise UserError("No se puede cancelar una revisión que ya tiene factura generada")

        self.state = 'cancelled'

    def action_set_to_draft(self):
        """Vuelve a borrador"""
        self.ensure_one()
        if self.invoice_id:
            raise UserError("No se puede volver a borrador una revisión con factura")

        self.state = 'draft'
