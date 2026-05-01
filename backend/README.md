# EventCommerce Backend

Base inicial del backend con:

- uv
- FastAPI
- Pydantic Settings
- SQLAlchemy
- Pyrefly

## Ejecutar

```bash
uv sync
cp .env.example .env
uv run eventcommerce-backend
```

Base de datos por defecto esperada:

```env
EVENTCOMMERCE_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/eventcommerce
```

## Estructura

```text
app/
  modules/
    orders/
      api/v1/
      application/
      domain/
      infrastructure/
    inventory/
      api/v1/
      application/
      domain/
      infrastructure/
    payments/
      api/v1/
      application/
      domain/
      infrastructure/
    notifications/
      api/v1/
      application/
      domain/
      infrastructure/
  shared/
    config/
    db/
```
