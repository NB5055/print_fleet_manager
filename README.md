# Print Fleet Manager

**Gestión y monitoreo centralizado de flotas de impresoras con facturación por uso**

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Odoo](https://img.shields.io/badge/odoo-17.0-brightgreen.svg)
![License](https://img.shields.io/badge/license-LGPL--3-orange.svg)

## 📋 Descripción

Print Fleet Manager es una solución completa de **Managed Print Services (MPS)** para Odoo 18 que permite:

- 🖨️ **Gestionar flotas de impresoras** distribuidas en múltiples ubicaciones
- 💰 **Facturar por consumo real** basado en contadores de páginas
- 📊 **Monitorear en tiempo real** el estado y uso de cada impresora
- 🔔 **Recibir alertas** de mantenimiento y consumibles bajos
- 📈 **Generar reportes** de uso y estadísticas

## ✨ Características Principales

### Gestión Multi-Ubicación
- Organización por ubicaciones físicas o clientes
- Token único de autenticación por ubicación
- Segregación de datos por cliente/ubicación

### Monitoreo en Tiempo Real
- Sincronización automática con PrintServer
- Estado online/offline de impresoras
- Niveles de tinta y toner actualizados
- Contadores de páginas en tiempo real

### Facturación por Uso
- Sistema dinámico de contadores basado en OIDs SNMP
- Soporte para múltiples tipos de contadores por impresora
- Precios individuales por tipo de contador
- Revisión editable antes de generar facturas
- Agrupación por ubicación o impresora individual
- Cálculo automático desde lecturas históricas

### Control de Consumibles
- Tracking de niveles de tinta/toner
- Alertas de consumibles bajos (configurable)
- Historial de reemplazos
- Estimación de páginas restantes

### Sistema de Alertas
- Notificaciones de impresoras offline
- Alertas de tinta/toner bajo
- Avisos de mantenimiento
- Estados críticos y warnings

### API RESTful
- Endpoints seguros para integración con PrintServer
- Autenticación mediante tokens
- Validación por ubicación
- Webhooks para comandos remotos

## 🔧 Requisitos

### Odoo
- Odoo 17.0
- Módulos base: `base`, `mail`, `account`, `product`

### PrintServer
- PrintServer Monitor instalado en cada ubicación
- Python 3.8+
- Conectividad HTTP/HTTPS con Odoo
- Acceso SNMP a las impresoras

### Red
- Conexión entre PrintServer y Odoo (HTTP/HTTPS)
- Puerto configurable (default: 8069 para Odoo)

## 📦 Instalación

### 1. Instalar el módulo

```bash
# Copiar el módulo a la carpeta de addons
cp -r print_fleet_manager /path/to/odoo/addons/

# Reiniciar Odoo
sudo systemctl restart odoo
```

### 2. Activar en Odoo

1. Activar modo desarrollador
2. Apps → Actualizar lista de aplicaciones
3. Buscar "Print Fleet Manager"
4. Hacer clic en "Instalar"

### 3. Configurar ubicaciones

1. Ir a **Print Fleet Manager → Monitor → Ubicaciones**
2. Crear nueva ubicación
3. Seleccionar cliente/partner
4. Hacer clic en **"Generar Nuevo Token"**
5. **Copiar el token** (no se podrá ver después)
6. Hacer clic en **"Activar Token"**

### 4. Configurar PrintServer

Ver documentación de PrintServer para configuración completa.

## 🚀 Uso

### Gestión de Ubicaciones

**Crear ubicación:**
```
Print Fleet Manager → Monitor → Ubicaciones → Crear
```

Cada ubicación representa un sitio físico o cliente donde hay impresoras.

### Visualizar Impresoras

Las impresoras se sincronizan automáticamente desde PrintServer:

```
Print Fleet Manager → Monitor → Impresoras
```

Vistas disponibles:
- **Lista**: Todas las impresoras con estado
- **Formulario**: Detalles completos de una impresora
- **Filtros**: Por ubicación, partner, fabricante, estado

### Generar Facturas

**Nuevo flujo de facturación con revisión editable:**

1. Ir a **Print Fleet Manager → Facturación → Generar Facturas**
2. Seleccionar cliente y período (fecha desde/hasta)
3. Elegir opciones:
   - Agrupar por ubicación
   - Solo lecturas no facturadas
4. Ver previsualización de totales
5. Hacer clic en **"Generar Factura"**

Esto crea una **Revisión de Facturación** en estado borrador donde puedes:
- Ver desglose completo de contadores por impresora
- Editar valores iniciales y finales de contadores
- Excluir impresoras del cobro
- Agregar notas
- Recalcular desde lecturas originales si es necesario

6. Confirmar la revisión
7. Generar la factura final

La factura incluirá:
- Detalle por impresora o por ubicación
- Múltiples tipos de contadores (mono, color, etc.)
- Valores inicial y final de cada contador
- Total de páginas por contador
- Precios individuales por tipo de contador
- Referencia a la revisión de facturación

### Ver Alertas

```
Print Fleet Manager → Monitor → Alertas
```

Estados de alertas:
- **Pendiente**: Nueva alerta
- **Reconocida**: Alerta vista
- **Resuelta**: Problema solucionado

### Reportes de Uso

```
Print Fleet Manager → Facturación → Reporte de Uso
```

Reportes disponibles:
- Uso por ubicación
- Uso por impresora
- Consumo de consumibles
- Tendencias de impresión

### Gestión de Tipos de Contador

```
Print Fleet Manager → Configuración → Tipos de Contador
```

Los tipos de contador se crean automáticamente cuando llegan lecturas con OIDs nuevos, pero puedes editarlos para:
- Asignar un nombre descriptivo
- Asociar un producto para facturación
- Definir precio unitario
- Establecer un código interno
- Activar/desactivar

## 💡 Lógica de Cálculo de Contadores

El sistema calcula el consumo de páginas para un período de facturación de la siguiente manera:

### Para cada tipo de contador de cada impresora:

1. **Contador Final**: Siempre es el valor de la **última lectura DENTRO del período**
2. **Contador Inicial**: Es el valor de la **última lectura ANTES del período** (o 0 si no hay lecturas previas)
3. **Total de Páginas**: `Contador Final - Contador Inicial`

### Ejemplo:

```
Lecturas históricas de una impresora:
- 2025-01-15: 1000 páginas
- 2025-01-20: 1200 páginas
- 2025-01-25: 1500 páginas
- 2025-02-05: 1883 páginas
- 2025-02-10: 2100 páginas

Período de facturación: 2025-02-01 al 2025-02-28

Contador Inicial = 1500 (última lectura antes del período: 2025-01-25)
Contador Final = 2100 (última lectura en el período: 2025-02-10)
Total Facturado = 2100 - 1500 = 600 páginas
```

Esta lógica asegura que:
- Se factura exactamente el consumo del período
- No hay duplicación de cobros entre períodos
- Las impresoras sin actividad en el período no generan cargos
- El primer período de una impresora factura desde 0

## 🔐 Seguridad

### Grupos de Usuarios

**Print Fleet Manager / User:**
- Ver impresoras de sus ubicaciones asignadas
- Ver lecturas y consumibles
- Ver alertas

**Print Fleet Manager / Manager:**
- Todas las funciones de User
- Gestionar ubicaciones
- Generar y gestionar tokens
- Generar facturas
- Acceso completo a todas las ubicaciones

### Tokens de Acceso

- Un token único por ubicación
- Scope limitado a su ubicación
- No expira (se puede desactivar manualmente)
- Se guarda encriptado en base de datos

## 📊 Arquitectura

```
┌─────────────────────────────┐
│   Odoo 18                   │
│   Print Fleet Manager       │
│                             │
│  ┌───────────────────────┐  │
│  │ Ubicación 1           │  │
│  │ Token: ABC123         │  │
│  │ Partner: Cliente A    │  │
│  │   ├─ Impresora 1      │  │
│  │   ├─ Impresora 2      │  │
│  │   └─ Impresora 3      │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │ Ubicación 2           │  │
│  │ Token: XYZ789         │  │
│  │ Partner: Cliente B    │  │
│  │   ├─ Impresora 4      │  │
│  │   └─ Impresora 5      │  │
│  └───────────────────────┘  │
└──────────┬──────────────────┘
           │ API REST
           │ (Token-based)
┌──────────▼──────────────────┐
│  PrintServer Monitor        │
│  (Ubicación 1)              │
│                             │
│  - Escaneo de red           │
│  - Recolección SNMP         │
│  - Sincronización Odoo      │
└─────────────────────────────┘
```

## 🔄 Sincronización de Datos

PrintServer sincroniza automáticamente:

1. **Impresoras**: Datos básicos (IP, modelo, serie, fabricante)
2. **Lecturas**: Contadores de páginas usando OIDs SNMP
   - Sistema dinámico que soporta cualquier OID
   - Creación automática de tipos de contador
   - Múltiples contadores por impresora
3. **Consumibles**: Niveles de tinta/toner
4. **Alertas**: Errores, warnings, estados críticos

Intervalo de sincronización: Configurable (default: 5 minutos)

### Formato de Lecturas

Las lecturas ahora usan un formato basado en OIDs:

```json
{
  "readings": [
    {
      "printer_ip": "10.0.0.14",
      "timestamp": "2025-10-13T10:30:00",
      "status": "online",
      "counters": [
        {"oid": "1.3.6.1.2.1.43.10.2.1.4.1.1", "value": 12345},
        {"oid": "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.1", "value": 10000}
      ]
    }
  ]
}
```

## 🛠️ API Endpoints

### Sincronización

```http
POST /api/printer/sync/printers
Headers:
  X-API-Key: [token-de-ubicacion]
  Content-Type: application/json
Body:
  {
    "printers": [...]
  }
```

### Test de Conexión

```http
GET /api/printer/sync/health
Headers:
  X-API-Key: [token-de-ubicacion]
```

### Webhooks

```http
POST /api/printer/webhook
Headers:
  X-API-Key: [token-de-ubicacion]
  X-Odoo-Signature: [hmac-sha256]
Body:
  {
    "command": "collect_now",
    "data": {...}
  }
```

## 📝 Modelos de Datos

### printer.location
Ubicaciones físicas o clientes

### printer.device
Impresoras individuales

### counter.type
Tipos de contadores SNMP (definidos por OID)
- OID SNMP único
- Código interno
- Producto asociado para facturación
- Precio unitario

### printer.reading
Lecturas de contadores en un momento dado

### printer.reading.counter
Valores de contadores individuales por lectura
- Relación con tipo de contador (OID)
- Valor del contador

### printer.billing.review
Revisiones de facturación editables
- Estado: borrador, confirmado, facturado, cancelado
- Permite ajustar valores antes de facturar
- Historial completo de revisiones

### printer.billing.review.line
Líneas de revisión por impresora
- Contadores editables
- Exclusión de factura
- Notas

### printer.billing.review.counter
Contadores individuales en revisión
- Valor inicial y final
- Precio unitario
- Subtotal

### printer.consumable
Consumibles (tinta/toner)

### printer.alert
Alertas y notificaciones

## 🤝 Contribuir

Este es un módulo custom. Para modificaciones contactar al equipo de desarrollo.

## 📄 Licencia

LGPL-3

## 👥 Autor

Custom Development

## 📞 Soporte

Para soporte técnico:
- Revisar logs de Odoo
- Revisar logs de PrintServer
- Verificar conectividad de red
- Validar tokens activos

---

**Print Fleet Manager** - Solución profesional de Managed Print Services para Odoo 18
