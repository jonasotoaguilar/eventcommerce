import { useState } from "react";
import { useAuth } from "../auth/session";
import type { ApiClient } from "../lib/api-client";
import {
  createOperatorApi,
  validateSimulationInput,
  type PaymentSimulation,
  type SimulatePaymentInput,
  type SimulationInputErrors,
} from "../lib/operator";

/** Thrown when the submit path rejects raw inputs before any request. */
export class SimulationInputError extends Error {
  readonly errors: SimulationInputErrors;

  constructor(errors: SimulationInputErrors) {
    super("Invalid simulation input.");
    this.name = "SimulationInputError";
    this.errors = errors;
  }
}

/**
 * Page submit path: validate locally, then call the delivered simulation
 * read as the only transport. Normalized values build the endpoint's
 * `order_id`/`amount`/`currency` query; `ApiError` propagates to the caller.
 */
export async function runPaymentSimulation(
  api: ApiClient,
  raw: SimulatePaymentInput,
): Promise<PaymentSimulation> {
  const validated = validateSimulationInput(raw);
  if (!validated.ok) throw new SimulationInputError(validated.errors);
  return createOperatorApi(api).simulatePayment({
    orderId: validated.value.orderId,
    amount: validated.value.amount,
    currency: validated.value.currency,
  });
}

type PaymentsScreenState =
  | { kind: "idle" }
  | { kind: "invalid"; errors: SimulationInputErrors }
  | { kind: "submitting" }
  | { kind: "failed"; message: string }
  | { kind: "success"; result: PaymentSimulation };

/**
 * Deterministic payment simulation panel. The endpoint is a pure read:
 * nothing here authorizes or stores a payment, so its result is never a
 * real decision for a live order. Inputs start empty; the hints only show
 * the expected formats.
 */
export function OperatorPaymentsPage() {
  const { api } = useAuth();
  const [orderId, setOrderId] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("");
  const [state, setState] = useState<PaymentsScreenState>({ kind: "idle" });

  const submitting = state.kind === "submitting";
  const fieldErrors =
    state.kind === "invalid" ? state.errors : ({} as SimulationInputErrors);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setState({ kind: "submitting" });
    try {
      const result = await runPaymentSimulation(api, {
        orderId,
        amount,
        currency,
      });
      setState({ kind: "success", result });
    } catch (err) {
      if (err instanceof SimulationInputError)
        setState({ kind: "invalid", errors: err.errors });
      else
        setState({
          kind: "failed",
          message:
            err instanceof Error
              ? err.message
              : "Could not run the simulation.",
        });
    }
  }

  const result = state.kind === "success" ? state.result : null;

  return (
    <section aria-labelledby="operator-payments-title">
      <h1 id="operator-payments-title">Payment simulation</h1>
      <p className="hint">
        This panel only simulates a decision: no payment is authorized or
        stored by it. The simulation endpoint is a pure read, so its result
        is never a real payment decision for a live order.
      </p>

      <form
        className="operator-edit-form"
        aria-label="Payment simulation inputs"
        aria-busy={submitting}
        onSubmit={(event) => void handleSubmit(event)}
      >
        <div className="field">
          <label htmlFor="operator-simulation-order-id">Order id</label>
          <input
            id="operator-simulation-order-id"
            name="operator-simulation-order-id"
            type="text"
            autoComplete="off"
            value={orderId}
            aria-invalid={fieldErrors.orderId !== undefined}
            aria-describedby={
              fieldErrors.orderId !== undefined
                ? "operator-simulation-order-id-error"
                : "operator-simulation-order-id-hint"
            }
            onChange={(event) => setOrderId(event.target.value)}
          />
          <p className="hint" id="operator-simulation-order-id-hint">
            A UUID, for example 123e4567-e89b-12d3-a456-426614174000.
          </p>
          {fieldErrors.orderId !== undefined && (
            <p
              className="alert alert-error"
              id="operator-simulation-order-id-error"
              role="alert"
            >
              {fieldErrors.orderId}
            </p>
          )}
        </div>
        <div className="field">
          <label htmlFor="operator-simulation-amount">Amount</label>
          <input
            id="operator-simulation-amount"
            name="operator-simulation-amount"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={amount}
            aria-invalid={fieldErrors.amount !== undefined}
            aria-describedby={
              fieldErrors.amount !== undefined
                ? "operator-simulation-amount-error"
                : "operator-simulation-amount-hint"
            }
            onChange={(event) => setAmount(event.target.value)}
          />
          <p className="hint" id="operator-simulation-amount-hint">
            A positive amount with up to two decimals, for example 12.50.
          </p>
          {fieldErrors.amount !== undefined && (
            <p
              className="alert alert-error"
              id="operator-simulation-amount-error"
              role="alert"
            >
              {fieldErrors.amount}
            </p>
          )}
        </div>
        <div className="field">
          <label htmlFor="operator-simulation-currency">Currency</label>
          <input
            id="operator-simulation-currency"
            name="operator-simulation-currency"
            type="text"
            autoComplete="off"
            value={currency}
            aria-invalid={fieldErrors.currency !== undefined}
            aria-describedby={
              fieldErrors.currency !== undefined
                ? "operator-simulation-currency-error"
                : "operator-simulation-currency-hint"
            }
            onChange={(event) => setCurrency(event.target.value)}
          />
          <p className="hint" id="operator-simulation-currency-hint">
            Three letters, for example USD.
          </p>
          {fieldErrors.currency !== undefined && (
            <p
              className="alert alert-error"
              id="operator-simulation-currency-error"
              role="alert"
            >
              {fieldErrors.currency}
            </p>
          )}
        </div>
        <p className="cta-row">
          <button
            type="submit"
            className="button button-primary"
            disabled={submitting}
          >
            {submitting ? "Simulating\u2026" : "Simulate payment"}
          </button>
        </p>
      </form>

      <div aria-live="polite">
        {state.kind === "idle" && (
          <p className="hint" role="status">
            No simulation to show yet. Enter inputs to inspect a decision.
          </p>
        )}
        {state.kind === "failed" && (
          <div role="alert">
            <p className="alert alert-error">
              Simulation failed: {state.message}
            </p>
          </div>
        )}
        {result !== null && (
          <div className="checkout-summary">
            <h2>
              Simulated decision:{" "}
              <span
                className={
                  result.approved
                    ? "badge badge-status-confirmed"
                    : "badge badge-status-cancelled"
                }
              >
                {result.approved ? "Approved" : "Rejected"}
              </span>
            </h2>
            <dl className="timeline-payload">
              <div className="timeline-payload-row">
                <dt>Order id</dt>
                <dd>{result.order_id}</dd>
              </div>
              <div className="timeline-payload-row">
                <dt>Amount</dt>
                <dd>
                  {result.amount} {result.currency}
                </dd>
              </div>
              <div className="timeline-payload-row">
                <dt>Digest byte</dt>
                <dd>{result.digest_byte}</dd>
              </div>
              <div className="timeline-payload-row">
                <dt>Approval threshold</dt>
                <dd>{result.approval_threshold}</dd>
              </div>
            </dl>
            <p className="hint">
              Simulated only: this decision authorizes and stores nothing.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
