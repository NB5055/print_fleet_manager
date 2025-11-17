# -*- coding: utf-8 -*-
{
    'name': 'Print Fleet Manager',
    'version': '1.0.0',
    'category': 'Services/Management',
    'summary': 'Gestión y monitoreo centralizado de flotas de impresoras con facturación por uso',
    'description': """
Print Fleet Manager - Managed Print Services
=============================================

Solución completa para gestión de flotas de impresoras, facturación por consumo
y monitoreo en tiempo real integrado con PrintServer.

Características Principales:
-----------------------------
* **Gestión Multi-Ubicación**: Administre impresoras en múltiples sitios/clientes
* **Monitoreo en Tiempo Real**: Sincronización automática con PrintServer
* **Facturación por Uso**: Genere facturas basadas en contadores de páginas
* **Control de Consumibles**: Tracking automático de niveles de tinta/toner
* **Sistema de Alertas**: Notificaciones de mantenimiento y consumibles bajos
* **Reportes Avanzados**: Gráficos y análisis de uso por ubicación/impresora
* **Arquitectura Multi-Tenant**: Tokens únicos por ubicación para seguridad
* **API RESTful**: Integración segura mediante tokens de acceso
* **Historial Completo**: Auditoría de lecturas y cambios

Casos de Uso:
-------------
* Empresas de servicios de impresión (MPS)
* Proveedores de equipos con facturación por página
* Gestión de flotas corporativas
* Monitoreo de parques de impresoras distribuidas

Requisitos Técnicos:
--------------------
* PrintServer Monitor instalado en cada ubicación
* Conectividad HTTP/HTTPS entre PrintServer y Odoo
* Tokens de acceso configurados por ubicación

Autor: Custom Development
Licencia: LGPL-3
    """,
    'author': 'Custom Development',
    'website': 'https://github.com/your-repo/print-fleet-manager',
    'license': 'LGPL-3',

    # Dependencias
    'depends': [
        'base',
        'mail',  # Para chatter y tracking
        'account',  # Para facturación
        'product',  # Para productos (cartuchos, tintas, servicios)
    ],

    # Datos
    'data': [
        # Seguridad
        'security/printer_security.xml',
        'security/ir.model.access.csv',

        # Datos iniciales (secuencias y tipos de contadores)
        'data/printer_sequences.xml',
        'data/counter_type_data.xml',  # Tipos de contadores estándar

        # Vistas principales
        'views/printer_location_views.xml',
        'views/printer_views.xml',
        'views/printer_data_views.xml',  # readings, consumables, alerts
        'views/counter_type_views.xml',  # tipos de contadores
        'views/res_partner_views.xml',  # extensión de cliente con precios
        'views/partner_counter_price_views.xml',  # precios por cliente
        'views/printer_billing_review_views.xml',  # revisiones de facturación

        # Wizards (antes de los menús)
        'wizards/printer_billing_wizard_views.xml',
        # 'wizards/printer_billing_review_wizard_views.xml',  # Ya no se usa - reemplazado por modelo persistente
        'wizards/token_display_wizard_views.xml',

        # Menús (al final para que todo esté definido)
        'views/printer_menus.xml',

        # Datos adicionales (si existen)
        # 'data/printer_data.xml',
        # 'data/cron_jobs.xml',

        # Reportes (si existen)
        # 'reports/printer_reports.xml',
    ],

    # Demos
    'demo': [],

    # Assets (JavaScript, CSS)
    # 'assets': {
    #     'web.assets_backend': [
    #         'print_fleet_manager/static/src/js/printer_widget.js',
    #         'print_fleet_manager/static/src/css/printer_styles.css',
    #     ],
    # },

    # Configuración
    'installable': True,
    'application': True,
    'auto_install': False,

    # Versión de Odoo compatible
    'version': '17.0.1.0.0',

    # Imágenes
    'images': ['static/description/icon.png'],

    # Configuración adicional
    'external_dependencies': {
        'python': ['requests', 'cryptography'],
    },
}
