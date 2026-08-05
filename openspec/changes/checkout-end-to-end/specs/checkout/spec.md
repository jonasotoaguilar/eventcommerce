# Checkout Specification

## Purpose

Synchronous end-to-end checkout connecting the orders, inventory, payments, and notifications modules into one `POST /api/v1/checkout` flow: reserve inventory, authorize a deterministic simulated payment, move the order to exactly one terminal state, and emit a notification intent. It operates on the existing **3-state** order model (`pending`/`confirmed`/`cancelled`) and requires no catalog, cart, IAM, 5-state order machine, or AMQP readiness.

## Requirements

### Requirement: Checkout Request Validation

The system MUST validate `POST /api/v1/checkout` against a `CheckoutRequest` before any side effect. The request MUST carry `customer_id` (string), a non-empty `items` array, a request-level `amount` (non-negative), and `currency` (ISO 4217). Each item MUST have a non-empty `product_id` (string) and `quantity` (positive integer). No catalog exists, so `amount`/`currency` are caller-supplied; per-product pricing arrives with the catalog follow-up and is a flagged design gap (see Deterministic Payment Authorization).

#### Scenario: Valid request proceeds
- GIVEN a request with `{product_id: "P1", quantity: 2}`, `amount: 19.99`, `currency: "USD"`, and an `Idempotency-Key`
- WHEN POSTed to `/api/v1/checkout`
- THEN orchestration proceeds

#### Scenario: Invalid quantity or empty items rejected
- GIVEN a request with `quantity: 0` or `items: []`
- WHEN POSTed
- THEN the system responds `422 Unprocessable Entity`
- AND no order is created, no inventory is reserved, and no payment is authorized

### Requirement: Synchronous Orchestration and AMQP Independence

The orchestrator MUST run checkout synchronously in one HTTP request: create order (`pending`), reserve inventory, authorize payment, then exactly one terminal transition plus a notification intent. It MUST write outbox rows for the events it produces and MUST NOT require a running RabbitMQ broker, an AMQP consumer, or an outbox scheduler.

#### Scenario: Happy path confirms the order
- GIVEN sufficient inventory and a payment input the policy approves
- WHEN the request is processed
- THEN the order moves `pending → confirmed`, an `approved` Payment is persisted, inventory is reserved, a confirmation notification intent is emitted, outbox rows exist, and the response is `201 Created`

### Requirement: Single Terminal Transition Ownership

The orchestrator MUST own exactly one terminal order transition per request. `ReserveInventory`, `ReleaseInventory`, `AuthorizePayment`, and `ProcessPaymentFailure` MUST NOT confirm or cancel the order. `ProcessOrderInventoryResult` MUST NOT be invoked synchronously (it stays the AMQP-path owner). `cancel_reason` MUST be set once and only by the orchestrator.

#### Scenario: Exactly one terminal transition
- GIVEN any checkout reaching a terminal state
- WHEN it completes
- THEN the order is `confirmed` or `cancelled`, never both, via exactly one terminal status mutation

### Requirement: Compensation Paths

Insufficient stock MUST cancel the order with `cancel_reason="insufficient_stock"`, authorize no payment, persist no `approved` payment, and emit a cancellation notification. A declined payment after reservation MUST release the reserved inventory, cancel with `cancel_reason="payment_declined"`, persist `PaymentFailed` via `ProcessPaymentFailure` (which MUST persist failure and MUST NOT cancel), and emit a cancellation notification. Each compensation is the single terminal transition.

#### Scenario: Insufficient stock cancels
- GIVEN requested quantity exceeds available stock
- WHEN processed
- THEN the order is `cancelled` (`insufficient_stock`), no payment is authorized, and nothing remains reserved for the order

#### Scenario: Payment declined releases inventory and cancels
- GIVEN inventory reserved and a payment input the policy declines
- WHEN processed
- THEN inventory is released, the order is `cancelled` (`payment_declined`), and `PaymentFailed` is persisted

### Requirement: Deterministic Payment Authorization and Payment Record

A request is approved if and only if the first byte of `sha256("{order_id}|{amount}|{currency}")` is below a fixed threshold; identical input MUST always yield the same result. `AuthorizePayment` MUST create and persist the `Payment` record (`approved`/`declined`) to the payments table; the orchestrator MUST NOT create payment records. Because no catalog exists, `amount`/`currency` originate from the request — a caller-trust assumption the fixed threshold and any pricing reconciliation MUST resolve in design. The spec does not invent prices.

#### Scenario: Determinism across evaluations
- GIVEN a fixed `(order_id, amount, currency)`
- WHEN evaluated any number of times
- THEN every evaluation returns the identical result

### Requirement: Idempotency-Key Contract and Concurrency Isolation

A present `Idempotency-Key` MUST dedupe via `ProcessedEventStore` keyed `(key, "Checkout")`. A missing key is non-idempotent (always execute, creating a new order). A replay with identical payload MUST return the cached terminal response (original status code and body) with no re-execution, double-charge, or double-reserve. The same key with a differing payload MUST respond `409 Conflict`, execute nothing, and leave the first execution's state and response intact. Concurrent duplicates with identical payload MUST execute exactly once; a differing-payload request under an in-use key MUST NOT observe or mutate the first execution.

#### Scenario: Missing key executes per request
- GIVEN two identical requests without the key
- WHEN sent
- THEN two distinct orders are created

#### Scenario: Replay returns cached response
- GIVEN a completed checkout stored under key `K` with payload `P`
- WHEN `K` + identical `P` is replayed
- THEN the cached terminal response returns with no re-execution and no additional reservation or charge

#### Scenario: Key reused with differing payload conflicts
- GIVEN a completed checkout under `K` with payload `P`
- WHEN `K` is reused with payload `P'` ≠ `P`
- THEN the response is `409 Conflict` and nothing executes

#### Scenario: Concurrent duplicates isolate
- GIVEN two concurrent requests with the same `K` + identical `P`
- WHEN they race
- THEN exactly one executes and both clients receive the same terminal response, with no partial observation and no cross-mutation of the first execution

### Requirement: Checkout Response, Notification, and Status Mapping

Success MUST return `201 Created` with a `CheckoutResponse` body; an identical replay MUST return the exact original status code and body (so a replay of a successful checkout returns `201`). Validation failures map to `422`; idempotency conflicts to `409`. The orchestrator MUST emit a notification intent at every terminal state (confirmation or cancellation); a notification failure MUST NOT roll back the terminal transition. The response MUST NOT depend on AMQP availability.

#### Scenario: Status and notification mapping
- GIVEN the success, replay, validation-error, and conflict outcomes
- WHEN each occurs
- THEN responses are `201`, original-status+body, `422`, and `409` respectively, and each terminal state emitted exactly one notification intent
