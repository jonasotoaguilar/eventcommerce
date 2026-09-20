# EventCommerce Storefront (U1 app shell)

Shopper-facing React + Vite + TypeScript app. U1 covers the foundation only:
app shell, `/api/v1` fetch client, auth session (login/register/me), public
routes (`/`, `/login`, `/register`), a `ProtectedRoute` ready for later
cart/checkout/order routes, shared layout, and DESIGN.md-aligned tokens.

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
- No operator screens and no order polling in this slice (shopper scope only).
- No `.env` file is needed: the API base defaults to same-origin `/api/v1`
  and the dev proxy forwards `/api` to `http://localhost:8000`.
