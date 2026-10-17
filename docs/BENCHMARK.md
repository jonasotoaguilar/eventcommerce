# Checkout p95 benchmark (S6)

Measures end-to-end checkout latency for the deterministic MVP path and checks
it against the 500 ms target from `PRD.md` ("Metrics").

## What is measured

The synchronous `POST /api/v1/checkout` request through the real ASGI app and
the real database: order creation, inventory reservation, deterministic
payment authorization, order confirmation/cancellation, and the notification
intent, including durable `Idempotency-Key` handling.

Per attempt the client times only the checkout request. The exact request
sequence per measured attempt is:

1. `POST /api/v1/iam/register` with a unique shopper email (once per run).
2. `POST /api/v1/iam/login` with the same credentials (once per run).
3. Seed product `BENCH-1` (price `10.00 USD`, active) with ample stock
   directly in the database, following the convention of the existing
   checkout E2E tests (once per run).
4. For each of the 50 attempts: reset the cart to exactly one `BENCH-1` line
   via `GET /api/v1/cart`, `DELETE /api/v1/cart/items/{product_id}` for any
   retained lines, and `POST /api/v1/cart/items`; then time
   `POST /api/v1/checkout` with body `{"cart_id": "<id>"}` and a fresh
   `Idempotency-Key` per attempt.

Every attempt must return `201`; the sample size is fixed at 50 and no
iteration is dropped. The deterministic policy approves `192/256` of order ids,
so a run contains both branches, and the two branches do not do the same work:
the confirmed branch additionally persists the authorization and the
confirmation, while a rejected payment cancels the order and compensates the
reservation. The benchmark therefore reports three scopes and asserts the
budget on two of them:

- **all attempts** — the mixed sample, reported for completeness;
- **confirmed only** — the deterministic path `PRD.md` names, asserted;
- **cancelled only** — the rejection branch, reported for completeness.

The PRD claim is judged on **confirmed only**; the mixed number alone would
understate it, because the rejection branch is cheaper per attempt.

## How to reproduce

From `backend/`, against an isolated database that does not collide with
other runs (create `eventcommerce_bench_test` first if it is missing):

```sh
EVENTCOMMERCE_POSTGRES_DB=eventcommerce_bench EVENTCOMMERCE_BENCHMARK=1 \
  uv run pytest app/tests/benchmark/test_checkout_p95.py -q -s
```

The benchmark test is skipped unless `EVENTCOMMERCE_BENCHMARK=1` is set, so
the default suite stays fast. Helpers (`percentile`, `summarize`,
`format_report`) have ordinary fast tests that always run.

## Recorded run

- Date (UTC): 2026-10-17.
- Machine: Linux 6.12.111+deb13-amd64 x86_64, 8 CPUs.
- Environment: local PostgreSQL 16.15 via `docker compose` (`postgres:16-alpine`),
  database `eventcommerce_bench_test`; Python 3.13.5, FastAPI 0.136.1,
  httpx 0.28.1 (in-process `ASGITransport`), SQLAlchemy 2.0.49.
- Command: the exact command above, run from `backend/`.

Observed output:

```text
checkout p95 benchmark
command: EVENTCOMMERCE_POSTGRES_DB=eventcommerce_bench EVENTCOMMERCE_BENCHMARK=1 uv run pytest app/tests/benchmark/test_checkout_p95.py -q -s
samples: 50
min: 49.05 ms
p50: 65.92 ms
p95: 93.62 ms
p99: 112.34 ms
max: 117.06 ms
budget: p95 < 500.00 ms
verdict: PASS
checkout p95 benchmark
command: EVENTCOMMERCE_POSTGRES_DB=eventcommerce_bench EVENTCOMMERCE_BENCHMARK=1 uv run pytest app/tests/benchmark/test_checkout_p95.py -q -s
scope: confirmed only (payment approved)
samples: 43
min: 49.05 ms
p50: 65.82 ms
p95: 96.70 ms
p99: 113.01 ms
max: 117.06 ms
budget: p95 < 500.00 ms
verdict: PASS
checkout p95 benchmark
command: EVENTCOMMERCE_POSTGRES_DB=eventcommerce_bench EVENTCOMMERCE_BENCHMARK=1 uv run pytest app/tests/benchmark/test_checkout_p95.py -q -s
scope: cancelled only (payment rejected)
samples: 7
min: 54.62 ms
p50: 66.04 ms
p95: 87.36 ms
p99: 88.33 ms
max: 88.58 ms
budget: p95 < 500.00 ms
verdict: PASS
outcomes: confirmed=43 cancelled=7 (approval threshold 192/256)
```

## Verdict

The deterministic path named by `PRD.md` measures **p95 96.70 ms** (43
confirmed samples) against a 500 ms target: PASS. The mixed sample measures
93.62 ms and the rejection branch 87.36 ms; both sit below the confirmed-only
number, which is why the claim is anchored on the confirmed scope.

## Limits

This number proves the deterministic checkout path is comfortably under
budget in local tests; it does not prove production latency. Specifically:

- In-process ASGI transport, not a real socket: no TCP/TLS or HTTP-server
  overhead is included.
- Local PostgreSQL on the same machine: no network or managed-database latency.
- Sequential single client: no concurrency, no contention, no load profile.
- One fixed shape (one line, `10.00 USD`): not a catalog-wide performance
  claim.
- Single recorded run per scope: an earlier recorded run measured p95 67.86 ms
  on its mixed sample before the scopes were split, so consecutive runs spread
  within a few tens of milliseconds — well inside the ~5x headroom under the
  budget.
- No production SLA is implied; RabbitMQ is not involved in the measured
  synchronous path.
