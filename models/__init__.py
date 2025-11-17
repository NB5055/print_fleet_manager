# -*- coding: utf-8 -*-

from . import printer_location
from . import printer
from . import counter_type  # Catálogo de tipos de contadores (independiente)
from . import res_partner  # Extensión de res.partner
from . import partner_counter_price  # Precios por cliente y tipo de contador
from . import printer_reading  # Depende de counter_type
from . import printer_reading_counter  # Depende de printer_reading y counter_type
from . import printer_consumable
from . import printer_alert
from . import printer_sync_config
from . import printer_billing_review_line  # Depende de printer.device
from . import printer_billing_review_counter  # Depende de printer_billing_review_line y counter_type
from . import printer_billing_review  # Depende de printer_billing_review_line
