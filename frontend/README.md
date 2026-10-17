# EventCommerce Storefront

React + Vite + TypeScript app serving two surfaces behind the same client:
the shopper journey and the operator console. The completed shopper slice
covers the full browse-to-track journey:

- Public catalog and product detail (`/`, `/catalog`, `/catalog/:id`).
- Register/login with a persisted auth session (`/login`, `/register`).
- Authenticated server-side cart (`/cart`, behind `ProtectedRoute`): add
  lines, set absolute quantities, remove lines, and proceed to checkout.
- Cart-backed checkout (`/checkout`, behind `ProtectedRoute`): submits
  `{cart_id}` only with one fresh `Idempotency-Key` per place-order
  attempt, suppresses duplicate submits while in flight, and redirects to
  the tracker on 201 with actionable UI for 404/409/422/500.
- Order tracking (`/orders/:id`, behind `ProtectedRoute`): exact
  five-state lifecycle (`pending`, `inventory_reserved`,
  `payment_authorized`, `confirmed`, `cancelled`) with status badge,
  cancellation reason, chronological timeline, polite `aria-live` status
  updates, and an honest manual refresh control.

The operator console (`/operator`, behind `OperatorRoute` and the `operator`
role) covers catalog browsing with stock editing (`/operator/catalog`), the
order queue with confirm/cancel (`/operator/orders`), and the deterministic
payment simulation panel (`/operator/payments`). The three screens read
`GET /api/v1/operator/*` and reuse the delivered catalog, inventory and
orders write routes instead of operator-only writes.

## Prerequisites

- Node + npm 11 (`npm --version` should report 11.x)
- Backend running at `http://localhost:8000` (Vite proxies `/api` there)

## Run

```sh
npm ci
npm run dev
```

Other checks:

```sh
npm run typecheck
npm run lint
npm run test
npm run build
```

## Notes

- Auth token persists in `localStorage` (`eventcommerce.auth.token`); expired
  tokens are dropped and 401 responses return the shopper to `/login`.
- No live transport (websockets/SSE) and no automatic polling: the tracker
  refreshes manually, and the operator screens reload when they open or after
  an action.
- No `.env` file is needed: the API base defaults to same-origin `/api/v1`
  and the dev proxy forwards `/api` to `http://localhost:8000`.
- Future work stays outside this slice: real payments, saga-DLQ handling,
  observability, and deployment.
