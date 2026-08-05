# ADR 0005: Use deterministic simulated payments

## Status

Accepted (current implementation)

## Context

`AuthorizePayment` previously used `random.choice([True, True, True, False])` as the approval policy. This was useful for manual exploration but is not a reproducible business behavior. The portfolio needs a real payment bounded context without real card processing.

## Decision

Replace the random stub with a deterministic simulated payment provider behind the existing `PaymentRepository` port. The adapter will return the same authorization result for the same `(order_id, amount, currency)` input. The bounded context remains real; only the provider is simulated.

## Options considered

| Option | Assessment |
|--------|------------|
| Keep random stub | Simple, but tests and demos are non-deterministic. |
| Deterministic simulated provider | Reproducible, no PCI, and proves the ports/adapters boundary. |
| Real payment provider | Out of scope for a portfolio MVP; requires PCI and contracts. |

## Consequences

- **Positive**: deterministic tests, reproducible operator demos, and a clear adapter boundary for future real providers.
- **Negative**: simulated behavior does not exercise fraud, network, or provider failure modes.
- **Neutral**: the provider can be swapped without changing the use-case or domain logic.

## References

- [PRD.md](../../PRD.md) — Business Rules / MVP Target
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Current Implementation Status matrix
- [GLOSSARY.md](../GLOSSARY.md) — deterministic simulated payment
- `backend/app/modules/payments/application/authorize_payment.py`
