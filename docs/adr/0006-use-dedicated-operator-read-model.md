# ADR 0006: Use a dedicated operator read model

## Status

Accepted (current implementation)

## Context

The operator console needs three reads the delivered APIs do not cover: an order queue with payment-derived totals, a catalog listing that includes inactive products with stock, and a panel evaluating the deterministic payment policy for given inputs. The public `GET /api/v1/catalog` browse contract is active-only, `orders` stores no amount or currency, and the payment policy is pure. The repository already composes contexts in application layers (`cart → catalog`, `checkout → orders/catalog/inventory/payments`).

## Decision

D1 — Serve the console from a dedicated read-only module, `backend/app/modules/operator/` (`GET /api/v1/operator/*`, `operator` role required), that composes the delivered contexts: `orders` (new `list_queue`), `payments` (new `list_by_order_ids`), `catalog` (new `list_all`), `inventory` (new `list_by_product_ids`), and `payments.domain.policy` (already pure). Existing methods are untouched; the operator container shares one request session, so `orders` never imports `payments`.

D2 — Project each queue row's money from the latest payment per order by `(created_at, id)` and never copy it into the order table. `orders` keeps no amount or currency (`OrderModel`) while `PaymentModel` does; when an order has no payment row, `total` and `currency` stay `null` rather than defaulting to zero, and `item_count` is the sum of line quantities.

D3 — Reuse the delivered routes for every operator write: product edit stays `PATCH /api/v1/catalog/{product_id}`, stock stays `POST /api/v1/inventory/{product_id}/adjust`, and order actions stay `POST /api/v1/orders/{order_id}/confirm|cancel`. The console adds no write endpoint.

## Options considered

| Option | Assessment |
|--------|------------|
| Add `include_inactive` to the public `GET /api/v1/catalog` | Rejected: branches the delivered public browse contract on caller identity and needs a new optional-auth dependency. |
| Put the queue in `orders` while reading `payments` amounts | Rejected: creates an `orders → payments` dependency on top of the delivered `payments → orders` one. |
| Duplicate money into the order table | Rejected: a second source of truth for amounts the payments context already owns. |
| New console write endpoints | Rejected: the delivered catalog/inventory/orders routes already cover every operator write. |

## Consequences

- **Positive**: public contracts stay caller-agnostic, the `payments → orders` dependency direction is preserved, queue totals always reflect the latest payment row, and operator writes exercise the same routes (and validations) as any other caller.
- **Negative**: the operator module owns a read model that must track the contexts it composes; new order or payment fields need an explicit projection update.
- **Neutral**: the simulation endpoint evaluates `payments.domain.policy` without touching storage, so policy changes surface in the panel with no console change.

## References

- [PRD.md](../../PRD.md) — Now / MVP Target
- [GLOSSARY.md](../GLOSSARY.md) — operator, deterministic simulated payment
- `backend/app/modules/operator/api/routes.py` — the three reads and their bounds
- `backend/app/modules/operator/application/list_order_queue.py` — latest-payment projection
- `backend/app/modules/operator/application/list_catalog_with_stock.py` — inactive-inclusive listing with joined stock
