# Arquitectura Backend — EventCommerce Core

## Visión general

El backend sigue una **arquitectura modular orientada a dominio** (Domain-Driven Design ligero) con separación de responsabilidades en cuatro capas principales por módulo:

- `domain/` — Entidades, eventos, value objects, errores, repositorios (protocolos) y servicios de dominio puros.
- `application/` — Casos de uso con **screaming architecture**: los nombres describen la intención de negocio (`CreateOrder`, `ReserveInventory`, `AuthorizePayment`).
- `infrastructure/` — Implementaciones técnicas concretas, como repositorios sobre SQLAlchemy.
- `api/` — Adaptadores HTTP: schemas Pydantic y rutas FastAPI versionadas.

Cada módulo (`orders`, `inventory`, `payments`, `notifications`) respeta la misma estructura, lo que permite escalar el monolito modular hacia servicios independientes sin reestructurar código de dominio.

---

## Estructura por módulo

```
modules/{modulo}/
├── domain/
│   ├── entities/          # Objetos de negocio con identidad (ej. Order)
│   ├── events/            # Eventos de dominio inmutables (ej. OrderCreated)
│   ├── value_objects/     # Objetos sin identidad propia (ej. Money, StockQuantity)
│   ├── errors/            # Jerarquía de excepciones propias del dominio
│   ├── repositories/      # Protocolos (interfaces) de persistencia
│   └── services/          # Lógica pura de dominio, sin dependencias externas
├── application/
│   ├── create_order.py    # Caso de uso: crear orden
│   ├── get_order.py       # Caso de uso: consultar orden
│   └── ...                # Otros casos de uso nombrados por intención
├── infrastructure/
│   └── repositories/
│       └── sqlalchemy_repository.py   # Implementación concreta del repositorio
├── api/
│   ├── schemas/           # Modelos Pydantic para request/response
│   └── routes/
│       └── v1/            # Rutas versionadas (FastAPI routers)
│           └── router.py
└── tests/
    └── test_placeholder.py
```

---

## Decisiones de arquitectura

### 1. Screaming architecture en application/

Los archivos dentro de `application/` se nombran según el **comportamiento de negocio**, no según el patrón técnico (`use_case`, `handler`, etc.). Esto hace que el código exprese qué hace el sistema antes de cómo lo hace.

### 2. Domain services como funciones puras

La lógica de negocio sin estado vive en funciones puras dentro de `domain/services/`. No dependen de frameworks ni de bases de datos, por lo que son trivialmente testeables.

### 3. Repositorios como Protocolos

Se usa `typing.Protocol` en lugar de clases abstractas para definir contratos de persistencia. Esto permite que la infraestructura dependa del dominio (Dependency Inversion) sin forzar una herencia rígida.

### 4. Versionado en `api/routes/v1/`

Las rutas HTTP se versionan explícitamente bajo `api/routes/v1/`, manteniendo la posibilidad de convivir con `v2` sin afectar el dominio ni la aplicación. Los schemas en `api/schemas/` no se versionan en el path: evolucionan con Pydantic y se mantienen compatibles mientras sea posible.

### 5. Monolito modular

Todos los módulos viven en el mismo proceso, pero sus dominios están aislados. Si en el futuro se decide extraer `payments` a un microservicio, solo `api/` y `infrastructure/` cambian; `domain/` y `application/` se trasladan sin modificación.

---

## Flujo de dependencias

```
   api/  <--  application/  <--  domain/
      \           /
   infrastructure/
```

- `api/` solo puede importar de `application/` y `domain/` (para schemas de respuesta).
- `application/` solo puede importar de `domain/`.
- `infrastructure/` implementa contratos definidos en `domain/`.
- `domain/` no importa de ninguna otra capa.
