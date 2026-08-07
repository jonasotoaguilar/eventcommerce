# Proposal: Messaging Runtime Bootstrap

## Intent

Make the documented order choreography executable without breaking synchronous checkout. The smallest correct slice must carry reservable order data, publish durable outbox events, dispatch them idempotently, and complete terminal notifications while the API remains usable when RabbitMQ is unavailable.

## Scope

### In Scope
- Add `items` to `OrderCreated`; harden outbox claiming/indexing and persistent publishing.
- Bootstrap publisher, scheduler, and consumers through FastAPI lifespan with graceful shutdown and non-fatal broker retry.
- Dispatch durable queues with prefetch `1`, ack after commit, and nack/requeue after rollback.
- Wire inventory, order-result, and new idempotent notification handlers; skip terminal orders to preserve synchronous checkout coexistence.
- Add broker-free runtime/chain coverage, one gated broker integration in CI, RabbitMQ env examples, and same-change status documentation.

### Out of Scope
- Catalog, cart, IAM, frontend, real payments, or the five-state order lifecycle.
- Saga orchestration, DLQ/retry exhaustion, full event-envelope correlation, separate worker deployment, or arbitrary refactors.
- `checkout-end-to-end` changes or its archive blocker.

## Capabilities

### New Capabilities
- `messaging-runtime`: Durable outbox forwarding, lifecycle-managed AMQP dispatch, idempotent choreography handlers, delivery policy, and runtime verification.

### Modified Capabilities
- `project-foundation-docs`: Update Now/MVP Target claims and messaging evidence when the runtime ships.

## Approach

Use the current header-based wire format. Lifespan owns a retrying publisher, settings-driven outbox loop, and shared consumer registry. Claim pending rows with `FOR UPDATE SKIP LOCKED` and index `(status, created_at)`. Bind durable queues `inventory.order_created`, `orders.inventory_result`, and `notifications.order_terminal`. Handlers read order status through an application-facing orders query, record terminal skips as processed, and retain current `pending → confirmed/cancelled` semantics.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `backend/app/shared/messaging/`, `backend/app/app.py` | Modified/New | Delivery hardening, scheduler, consumer, lifespan |
| `backend/app/modules/{orders,inventory,notifications}/` | Modified/New | Payload, guards, handler wiring |
| `backend/alembic/versions/`, `backend/app/tests/` | New/Modified | Polling index and runtime coverage |
| `.github/workflows/api-ci.yml`, `backend/.env.example` | Modified | Gated broker and env coverage |
| `ARCHITECTURE.md`, `docs/GLOSSARY.md`, `docs/adr/0002-use-choreography.md`, `README.md` | Modified | Delivered-status alignment |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Duplicate or poison processing | Medium | Claims, idempotency, terminal guards, replay tests |
| Broker outage affects API | Medium | Non-fatal startup, background retry, graceful shutdown |
| Review exceeds 800 lines | High | `sdd-tasks` forecasts before selecting any chain strategy |

## Rollback Plan

Revert runtime wiring, handlers, configuration, docs, and polling-index migration together; pending outbox rows remain unpublished and synchronous checkout remains the active path.

## Dependencies

- Existing `aio-pika`, PostgreSQL, RabbitMQ compose service, outbox, and idempotency primitives; no new runtime package.

## Success Criteria

- [ ] The documented event chain completes idempotently through broker-free tests and the gated RabbitMQ integration.
- [ ] Duplicate/late events do not repeat inventory or terminal transitions; publisher messages are persistent.
- [ ] API startup/shutdown remains healthy with RabbitMQ unavailable, and CI/env/docs match delivered behavior.
