# PRD - EventCommerce Core

**Proyecto:** EventCommerce Core  
**Tipo:** Backend event-driven para procesamiento de ordenes  
**Stack principal:** Python, FastAPI, PostgreSQL, RabbitMQ, Docker Compose  
**Version:** 1.0  
**Fecha:** 2026-04-30

---

## 1. Resumen ejecutivo

EventCommerce Core es una plataforma backend que simula el procesamiento de ordenes de compra usando una arquitectura orientada a eventos. El objetivo no es construir un ecommerce completo, sino demostrar como un sistema backend moderno coordina procesos distribuidos como creacion de ordenes, reserva de inventario, autorizacion de pagos, confirmacion, cancelacion y notificaciones.

El sistema estara disenado con FastAPI para exponer APIs HTTP, PostgreSQL para persistencia transaccional, RabbitMQ como broker de eventos y workers asincronos para procesar el flujo de negocio. La propuesta busca demostrar conocimientos tecnicos avanzados en arquitectura backend: Event-Driven Architecture, Outbox Pattern, Saga Pattern, consumidores idempotentes, reintentos, dead-letter queue, trazabilidad por correlation ID, documentacion AsyncAPI y observabilidad.

---

## 2. Problema

En sistemas tradicionales, el procesamiento de una orden suele ejecutarse dentro de una unica llamada HTTP. Esto genera acoplamiento entre dominios como ordenes, inventario, pagos y notificaciones. Si un servicio externo falla, toda la operacion puede fallar o quedar en un estado inconsistente.

Ejemplo de problema tradicional:

1. Se crea una orden.
2. Se descuenta inventario.
3. Se intenta procesar el pago.
4. El pago falla.
5. El sistema debe revertir inventario y cancelar la orden.

Sin una arquitectura clara, este flujo puede terminar con inventario bloqueado, ordenes incompletas, pagos duplicados o errores dificiles de rastrear.

---

## 3. Objetivo del producto

Construir un backend funcional que procese ordenes mediante eventos, permitiendo que cada parte del flujo sea desacoplada, observable, tolerante a fallos e idempotente.

El proyecto debe demostrar que el sistema puede:

- Crear ordenes de forma confiable.
- Reservar inventario de manera asincrona.
- Simular autorizaciones de pago.
- Confirmar o cancelar ordenes segun eventos del flujo.
- Reintentar operaciones fallidas.
- Registrar una linea de tiempo completa por orden.
- Evitar efectos duplicados ante eventos repetidos.
- Exponer documentacion tecnica clara para APIs HTTP y eventos.

---

## 4. Usuarios objetivo

### 4.1 Usuario tecnico evaluador

Reclutadores tecnicos, tech leads o entrevistadores que revisan el portafolio y quieren entender la calidad de diseno backend del candidato.

### 4.2 Usuario desarrollador

Desarrolladores que quieren levantar el proyecto localmente, probar el flujo de ordenes, inspeccionar eventos y entender decisiones arquitectonicas.

### 4.3 Usuario operador simulado

Persona que revisa el estado de una orden, inspecciona eventos fallidos y reintenta mensajes desde una dead-letter queue.

---

## 5. Alcance del MVP

El MVP se enfocara en el nucleo del procesamiento de ordenes.

### Incluido

- API HTTP para crear ordenes.
- API HTTP para consultar ordenes.
- API HTTP para consultar timeline de eventos por orden.
- Servicio de ordenes.
- Servicio de inventario.
- Servicio de pagos simulados.
- Servicio de notificaciones simulado.
- Publicacion y consumo de eventos con RabbitMQ.
- PostgreSQL como base de datos principal.
- Outbox Pattern para publicacion confiable de eventos.
- Consumidores idempotentes.
- Reintentos controlados.
- Dead-letter queue.
- Docker Compose para entorno local.
- Tests unitarios e integracion basicos.
- Documentacion README y AsyncAPI.

### No incluido en el MVP

- Carrito de compras completo.
- Frontend ecommerce.
- Pasarela de pagos real.
- Autenticacion avanzada de usuarios finales.
- Gestion completa de productos.
- Facturacion real.
- Sistema de envios real.

---

## 6. Propuesta de valor tecnica

EventCommerce Core se diferencia de un CRUD tradicional porque muestra como resolver problemas de backend reales:

- Coordinacion de procesos distribuidos.
- Fallos parciales.
- Consistencia eventual.
- Desacoplamiento entre dominios.
- Trazabilidad de eventos.
- Reintentos seguros.
- Prevencion de duplicados.
- Compensaciones de negocio.
- Observabilidad.

El proyecto debe comunicar que el foco no es vender productos, sino demostrar arquitectura backend moderna.

---

## 7. Arquitectura de alto nivel

### 7.1 Componentes

- **Order Service:** expone endpoints HTTP, crea ordenes, mantiene estado principal y publica eventos de orden.
- **Inventory Service:** consume eventos de orden creada y reserva o rechaza inventario.
- **Payment Service:** consume eventos de inventario reservado y autoriza o rechaza pagos simulados.
- **Notification Service:** consume eventos de orden confirmada o cancelada y registra notificaciones simuladas.
- **RabbitMQ:** broker de eventos.
- **PostgreSQL:** persistencia de ordenes, inventario, pagos, eventos outbox y eventos procesados.
- **Worker de Outbox:** publica al broker eventos guardados en la tabla outbox.
- **Dead-letter handler:** administra eventos que fallaron despues de varios intentos.

### 7.2 Diagrama logico

```text
Client
  -> FastAPI Order API
      -> PostgreSQL
      -> Outbox Events
          -> Outbox Worker
              -> RabbitMQ
                  -> Inventory Worker
                  -> Payment Worker
                  -> Notification Worker
```

---

## 8. Flujo principal

### 8.1 Flujo exitoso

1. Cliente crea una orden con `POST /orders`.
2. Order Service guarda la orden en estado `pending`.
3. Order Service guarda un evento `OrderCreated` en la tabla `outbox_events`.
4. Outbox Worker publica `OrderCreated` en RabbitMQ.
5. Inventory Service consume `OrderCreated`.
6. Inventory Service reserva stock y publica `InventoryReserved`.
7. Payment Service consume `InventoryReserved`.
8. Payment Service autoriza pago simulado y publica `PaymentAuthorized`.
9. Order Service consume `PaymentAuthorized`.
10. Order Service cambia la orden a `confirmed` y publica `OrderConfirmed`.
11. Notification Service consume `OrderConfirmed` y registra una notificacion simulada.

### 8.2 Flujo con inventario insuficiente

1. Cliente crea una orden.
2. Se publica `OrderCreated`.
3. Inventory Service detecta stock insuficiente.
4. Inventory Service publica `InventoryRejected`.
5. Order Service consume `InventoryRejected`.
6. Order Service cambia la orden a `cancelled`.

### 8.3 Flujo con pago fallido

1. Cliente crea una orden.
2. Inventario se reserva correctamente.
3. Payment Service rechaza el pago.
4. Payment Service publica `PaymentFailed`.
5. Inventory Service consume `PaymentFailed` y libera inventario.
6. Order Service consume `PaymentFailed` y cancela la orden.

---

## 9. Estados de orden

| Estado               | Descripcion                                                                |
| -------------------- | -------------------------------------------------------------------------- |
| `pending`            | Orden creada, esperando procesamiento.                                     |
| `inventory_reserved` | Inventario reservado correctamente.                                        |
| `payment_authorized` | Pago autorizado correctamente.                                             |
| `confirmed`          | Orden confirmada.                                                          |
| `cancelled`          | Orden cancelada por inventario insuficiente, pago fallido o accion manual. |
| `failed`             | Orden en estado de error tecnico no recuperado.                            |

---

## 10. Eventos principales

| Evento              | Productor         | Consumidor                       | Proposito                            |
| ------------------- | ----------------- | -------------------------------- | ------------------------------------ |
| `OrderCreated`      | Order Service     | Inventory Service                | Iniciar reserva de inventario.       |
| `InventoryReserved` | Inventory Service | Payment Service, Order Service   | Indicar que el stock fue reservado.  |
| `InventoryRejected` | Inventory Service | Order Service                    | Cancelar orden por falta de stock.   |
| `PaymentAuthorized` | Payment Service   | Order Service                    | Confirmar pago exitoso.              |
| `PaymentFailed`     | Payment Service   | Order Service, Inventory Service | Cancelar orden y liberar inventario. |
| `OrderConfirmed`    | Order Service     | Notification Service             | Notificar confirmacion de orden.     |
| `OrderCancelled`    | Order Service     | Notification Service             | Notificar cancelacion de orden.      |

---

## 11. Contrato base de evento

Todos los eventos deben seguir una estructura comun:

```json
{
  "event_id": "uuid",
  "event_type": "OrderCreated",
  "aggregate_id": "order_id",
  "correlation_id": "order_id",
  "causation_id": "previous_event_id",
  "occurred_at": "2026-04-30T18:20:00Z",
  "version": 1,
  "payload": {}
}
```

### Campos obligatorios

- `event_id`: identificador unico del evento.
- `event_type`: nombre del evento.
- `aggregate_id`: entidad principal relacionada.
- `correlation_id`: identificador compartido por todo el flujo.
- `causation_id`: evento que causo el evento actual, si aplica.
- `occurred_at`: fecha de ocurrencia.
- `version`: version del contrato.
- `payload`: datos especificos del evento.

---

## 12. Requerimientos funcionales

### RF-001 Crear orden

El sistema debe permitir crear una orden mediante una API HTTP.

**Endpoint:** `POST /orders`

**Criterios de aceptacion:**

- La orden se guarda en PostgreSQL.
- La orden inicia con estado `pending`.
- Se genera un evento `OrderCreated`.
- El evento se guarda en `outbox_events` dentro de la misma transaccion.
- La respuesta devuelve `order_id` y estado inicial.

### RF-002 Consultar orden

El sistema debe permitir consultar una orden por ID.

**Endpoint:** `GET /orders/{order_id}`

**Criterios de aceptacion:**

- Si la orden existe, se devuelve su estado actual.
- Si la orden no existe, se devuelve HTTP 404.
- La respuesta incluye items, estado, timestamps y motivo de cancelacion si aplica.

### RF-003 Consultar timeline de orden

El sistema debe exponer la linea de tiempo de eventos asociados a una orden.

**Endpoint:** `GET /orders/{order_id}/timeline`

**Criterios de aceptacion:**

- Devuelve eventos ordenados por fecha.
- Incluye tipo de evento, timestamp, estado resultante y metadata basica.
- Permite diagnosticar el flujo completo de una orden.

### RF-004 Reservar inventario

Inventory Service debe consumir `OrderCreated` y reservar stock si hay disponibilidad.

**Criterios de aceptacion:**

- Si hay stock suficiente, publica `InventoryReserved`.
- Si no hay stock suficiente, publica `InventoryRejected`.
- El procesamiento es idempotente.
- No se debe descontar stock dos veces por el mismo evento.

### RF-005 Procesar pago simulado

Payment Service debe consumir `InventoryReserved` y simular autorizacion de pago.

**Criterios de aceptacion:**

- Puede autorizar o rechazar pagos segun reglas configurables.
- Si autoriza, publica `PaymentAuthorized`.
- Si rechaza, publica `PaymentFailed`.
- No debe procesar dos veces el mismo evento.

### RF-006 Confirmar orden

Order Service debe confirmar una orden cuando reciba `PaymentAuthorized`.

**Criterios de aceptacion:**

- La orden cambia a `confirmed`.
- Se publica `OrderConfirmed`.
- El evento queda en el timeline.

### RF-007 Cancelar orden

Order Service debe cancelar una orden ante `InventoryRejected` o `PaymentFailed`.

**Criterios de aceptacion:**

- La orden cambia a `cancelled`.
- Se registra motivo de cancelacion.
- Se publica `OrderCancelled`.

### RF-008 Manejar dead-letter queue

El sistema debe registrar eventos que fallan repetidamente.

**Endpoint:** `GET /dead-letter-events`  
**Endpoint:** `POST /dead-letter-events/{event_id}/retry`

**Criterios de aceptacion:**

- Un evento pasa a dead-letter despues de superar el maximo de reintentos.
- El operador puede listar eventos fallidos.
- El operador puede reintentar un evento manualmente.

---

## 13. Requerimientos no funcionales

### RNF-001 Idempotencia

Todos los consumidores deben ser idempotentes. Procesar dos veces el mismo evento no debe generar efectos secundarios duplicados.

### RNF-002 Observabilidad

El sistema debe incluir logs estructurados con `correlation_id`, `event_id` y `order_id`.

### RNF-003 Tolerancia a fallos

Los fallos transitorios deben reintentarse con una politica definida. Los fallos permanentes deben terminar en dead-letter queue.

### RNF-004 Trazabilidad

Cada orden debe tener una linea de tiempo consultable desde la API.

### RNF-005 Documentacion

El proyecto debe incluir:

- README tecnico.
- OpenAPI generado por FastAPI.
- AsyncAPI para contratos de eventos.
- Diagrama de arquitectura.
- Instrucciones para ejecutar localmente.

### RNF-006 Testing

El proyecto debe incluir pruebas para:

- Casos felices.
- Inventario insuficiente.
- Pago fallido.
- Reintentos.
- Idempotencia.
- Transicion de estados.

---

## 14. Modelo de datos inicial

### 14.1 Tabla `orders`

| Campo           | Tipo          | Descripcion                    |
| --------------- | ------------- | ------------------------------ |
| `id`            | UUID          | Identificador de orden.        |
| `customer_id`   | UUID/String   | Cliente asociado.              |
| `status`        | Text          | Estado actual de la orden.     |
| `cancel_reason` | Text nullable | Motivo de cancelacion.         |
| `created_at`    | Timestamp     | Fecha de creacion.             |
| `updated_at`    | Timestamp     | Fecha de ultima actualizacion. |

### 14.2 Tabla `order_items`

| Campo        | Tipo        | Descripcion             |
| ------------ | ----------- | ----------------------- |
| `id`         | UUID        | Identificador del item. |
| `order_id`   | UUID        | Orden asociada.         |
| `product_id` | UUID/String | Producto solicitado.    |
| `quantity`   | Integer     | Cantidad.               |

### 14.3 Tabla `inventory`

| Campo                | Tipo        | Descripcion       |
| -------------------- | ----------- | ----------------- |
| `product_id`         | UUID/String | Producto.         |
| `available_quantity` | Integer     | Stock disponible. |
| `reserved_quantity`  | Integer     | Stock reservado.  |

### 14.4 Tabla `outbox_events`

| Campo          | Tipo               | Descripcion               |
| -------------- | ------------------ | ------------------------- |
| `id`           | UUID               | Identificador del evento. |
| `event_type`   | Text               | Tipo de evento.           |
| `aggregate_id` | UUID/String        | Entidad relacionada.      |
| `payload`      | JSONB              | Payload del evento.       |
| `status`       | Text               | Estado de publicacion.    |
| `created_at`   | Timestamp          | Fecha de creacion.        |
| `published_at` | Timestamp nullable | Fecha de publicacion.     |

### 14.5 Tabla `processed_events`

| Campo           | Tipo      | Descripcion                       |
| --------------- | --------- | --------------------------------- |
| `event_id`      | UUID      | Evento procesado.                 |
| `consumer_name` | Text      | Consumidor que proceso el evento. |
| `processed_at`  | Timestamp | Fecha de procesamiento.           |

### 14.6 Tabla `order_events`

| Campo        | Tipo      | Descripcion            |
| ------------ | --------- | ---------------------- |
| `id`         | UUID      | Identificador interno. |
| `order_id`   | UUID      | Orden asociada.        |
| `event_id`   | UUID      | Evento registrado.     |
| `event_type` | Text      | Tipo de evento.        |
| `payload`    | JSONB     | Datos del evento.      |
| `created_at` | Timestamp | Fecha de registro.     |

---

## 15. API HTTP inicial

### Crear orden

```http
POST /orders
```

Request:

```json
{
  "customer_id": "cus_123",
  "items": [
    {
      "product_id": "prod_1",
      "quantity": 2
    }
  ]
}
```

Response:

```json
{
  "order_id": "ord_123",
  "status": "pending"
}
```

### Consultar orden

```http
GET /orders/{order_id}
```

### Consultar timeline

```http
GET /orders/{order_id}/timeline
```

### Listar eventos fallidos

```http
GET /dead-letter-events
```

### Reintentar evento fallido

```http
POST /dead-letter-events/{event_id}/retry
```

---

## 16. Reglas de negocio

1. Una orden solo puede confirmarse si el inventario fue reservado y el pago autorizado.
2. Una orden cancelada no puede volver a confirmarse.
3. Un evento duplicado no debe modificar el estado dos veces.
4. Si no hay stock suficiente, la orden debe cancelarse.
5. Si el pago falla, el inventario reservado debe liberarse.
6. Las transiciones de estado invalidas deben ser rechazadas y registradas.
7. Todo evento relevante debe aparecer en el timeline de la orden.

---

## 17. Politica de reintentos

| Tipo de error                 | Accion                           |
| ----------------------------- | -------------------------------- |
| Timeout de broker             | Reintentar publicacion.          |
| Error transitorio de DB       | Reintentar procesamiento.        |
| Payload invalido              | Enviar a dead-letter queue.      |
| Estado de orden invalido      | Registrar error y no reprocesar. |
| Maximo de reintentos superado | Enviar a dead-letter queue.      |

Politica inicial:

- Maximo de reintentos: 5.
- Backoff: exponencial.
- Registro de cada intento fallido.

---

## 18. Observabilidad

Cada log debe incluir, cuando aplique:

```json
{
  "correlation_id": "ord_123",
  "event_id": "evt_456",
  "order_id": "ord_123",
  "service": "payment_service",
  "message": "Payment authorized"
}
```

Metricas sugeridas:

- Cantidad de ordenes creadas.
- Cantidad de ordenes confirmadas.
- Cantidad de ordenes canceladas.
- Tiempo promedio de confirmacion.
- Eventos procesados por consumidor.
- Eventos fallidos.
- Eventos en dead-letter queue.

---

## 19. Criterios de exito del proyecto

El proyecto se considerara exitoso si permite demostrar lo siguiente:

- El sistema procesa una orden completa usando eventos.
- Los servicios estan desacoplados.
- Los eventos son persistidos y trazables.
- Los consumidores son idempotentes.
- Los fallos no dejan el sistema en estados incoherentes.
- Existe documentacion suficiente para entender arquitectura y ejecutar localmente.
- El proyecto puede levantarse con Docker Compose.
- Hay tests automatizados que validan el flujo principal y los casos de error.

---

## 20. Roadmap

### Fase 1 - MVP funcional

- FastAPI Order API.
- PostgreSQL.
- RabbitMQ.
- Crear orden.
- Reservar inventario.
- Confirmar o cancelar orden.
- Timeline basico.

### Fase 2 - Pagos y compensaciones

- Payment Service simulado.
- `PaymentAuthorized`.
- `PaymentFailed`.
- Liberacion de inventario ante pago fallido.

### Fase 3 - Resiliencia

- Outbox Pattern.
- Consumidores idempotentes.
- Dead-letter queue.
- Reintentos.

### Fase 4 - Observabilidad y documentacion

- Logs estructurados.
- Prometheus.
- Grafana.
- OpenTelemetry.
- AsyncAPI.
- README completo.

### Fase 5 - Mejoras para portafolio

- Dashboard tecnico simple.
- CLI para crear ordenes de prueba.
- Seed de inventario.
- Diagrama Mermaid.
- Tests de integracion en CI.

---

## 21. Riesgos y mitigaciones

| Riesgo                    | Mitigacion                                                                    |
| ------------------------- | ----------------------------------------------------------------------------- |
| Proyecto demasiado grande | Construir primero un modular monolith event-driven y luego separar servicios. |
| Complejidad de RabbitMQ   | Mantener pocos eventos al inicio y documentar bien los exchanges/queues.      |
| Dificultad para debuggear | Usar correlation ID, timeline y logs estructurados desde el inicio.           |
| Eventos duplicados        | Implementar `processed_events` desde la primera version.                      |
| Estados inconsistentes    | Definir maquina de estados clara para ordenes.                                |

---

## 22. Definicion de terminado

El proyecto estara listo para publicarse en portafolio cuando cumpla:

- `docker compose up` levanta todo el sistema.
- `POST /orders` ejecuta un flujo completo.
- `GET /orders/{id}/timeline` muestra eventos del flujo.
- Hay caso exitoso, caso sin inventario y caso de pago fallido.
- Existen tests automatizados.
- README explica arquitectura, decisiones tecnicas y trade-offs.
- AsyncAPI documenta eventos principales.
- OpenAPI esta disponible desde FastAPI.
- El repositorio tiene una seccion clara de “problemas tecnicos resueltos”.

---

## 23. Nombre recomendado para el repositorio

Opciones:

- `eventcommerce-core`
- `fastapi-event-driven-orders`
- `orderflow-events`
- `saga-commerce-core`
- `event-driven-order-platform`

Nombre recomendado:

```text
eventcommerce-core
```

---

## 24. Pitch para README

EventCommerce Core es un backend event-driven construido con FastAPI, PostgreSQL y RabbitMQ para simular el procesamiento de ordenes en un entorno distribuido. Implementa Outbox Pattern, Saga Pattern, consumidores idempotentes, reintentos, dead-letter queue y trazabilidad por correlation ID. El objetivo del proyecto es demostrar arquitectura backend moderna, manejo de fallos parciales y consistencia eventual en procesos de negocio reales.

---

## 25. Decisiones tecnicas iniciales

| Decision       | Justificacion                                                                       |
| -------------- | ----------------------------------------------------------------------------------- |
| FastAPI        | Framework moderno, rapido y con OpenAPI automatico.                                 |
| PostgreSQL     | Persistencia transaccional robusta y soporte JSONB para eventos.                    |
| RabbitMQ       | Broker adecuado para colas, routing y patrones de mensajeria.                       |
| Outbox Pattern | Evita perder eventos cuando una transaccion de DB ocurre pero la publicacion falla. |
| Idempotency    | Protege contra eventos duplicados y reprocesamientos.                               |
| Docker Compose | Facilita ejecucion local y reproducibilidad.                                        |
| AsyncAPI       | Documenta contratos de eventos de forma explicita.                                  |

---

## 26. Preguntas abiertas

- ¿El proyecto iniciara como modular monolith o como multiples servicios separados?
- ¿RabbitMQ sera usado con exchanges topic o direct?
- ¿Los eventos se versionaran desde el inicio?
- ¿El dashboard tecnico sera parte del MVP o una mejora posterior?
- ¿Se usara SQLModel o SQLAlchemy puro?
- ¿Se incluira autenticacion basica para endpoints administrativos?

---

## 27. Recomendacion de implementacion

Para evitar sobreingenieria inicial, se recomienda comenzar con un modular monolith event-driven:

```text
apps/
  orders/
  inventory/
  payments/
  notifications/
shared/
  events/
  messaging/
  database/
```

Luego, si el proyecto madura, cada modulo puede separarse en un servicio independiente. Esta estrategia permite demostrar arquitectura sin bloquear el avance por complejidad operacional temprana.
