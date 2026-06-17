# Instrucciones para agentes de Archeion

Archeion es un proyecto personal de Django para Ramiro. Es un sistema privado y local-first pensado para registrar y analizar actividad económica personal.

## Identidad del proyecto

Archeion NO es el sistema clínico de pacientes.

- Archeion: ecosistema personal, registro de ingresos, análisis financiero, métricas personales, actividad laboral e integraciones futuras.
- MetaboCore: futuro sistema clínico orientado a pacientes.

No agregar expedientes de pacientes, diagnósticos, tratamientos, recetas, laboratorios ni flujos clínicos a Archeion salvo que se solicite explícitamente.

## Alcance actual

El módulo activo actual es `ledger`.

Ledger v0.1 se enfoca en registrar ingresos y entender ingreso bruto, métodos de pago, canales de cobro, comisiones e ingreso neto.

Conceptos centrales actuales:

- `ConceptoIngreso`: qué generó el ingreso.
- `MetodoPago`: forma general de pago, como efectivo, transferencia o tarjeta.
- `CanalCobro`: herramienta o canal usado para procesar el cobro, como Mercado Pago Tap o Mercado Pago Point.
- `EsquemaComision`: regla de comisión asociada a un canal de cobro.
- `Ingreso`: registro real del ingreso, guardando monto bruto, fotografía congelada de comisión aplicada y monto neto.

## Principios de diseño

Mantener el sistema pequeño, claro y local-first.

Preferir modelos simples de Django, mejoras al admin, tests y migraciones antes de agregar dashboards o APIs.

No agregar facturación, CFDI, gastos, dashboards, REST APIs, cambios de autenticación ni servicios de despliegue salvo que se solicite explícitamente.

No introducir dependencias grandes sin justificación.

Usar nombres y verbose names en español para elementos visibles al usuario cuando corresponda.

Usar `Decimal`, no `float`, para dinero y porcentajes.

Los registros históricos de ingresos no deben cambiar si después se editan los esquemas de comisión. `Ingreso` debe guardar una fotografía congelada de:

- monto bruto
- porcentaje de comisión aplicado
- monto de comisión
- monto neto

## Lógica de comisiones

Los esquemas de comisión pueden no tener fechas exactas de vigencia. Evitar campos rígidos como `vigente_desde` y `vigente_hasta`, salvo que se soliciten explícitamente.

Preferir campos flexibles como:

- `fecha_referencia`
- `activo`
- `notas`

Un `Ingreso` puede usar un `EsquemaComision`, pero debe guardar los valores aplicados de forma independiente.

Si `comision_manual` es `False`:

- si no hay esquema de comisión, la comisión es cero y el neto es igual al bruto
- si hay esquema de comisión, calcular porcentaje, comisión y neto automáticamente

Si `comision_manual` es `True`:

- no sobrescribir la comisión escrita manualmente
- calcular el neto como bruto menos comisión
- calcular el porcentaje aplicado a partir de la comisión manual cuando sea posible

## Comandos de validación

Antes de terminar una tarea, ejecutar:

```bash
python manage.py check
python manage.py test ledger