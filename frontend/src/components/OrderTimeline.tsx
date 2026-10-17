import { formatOccurredAt, sortTimelineEvents } from "../lib/order-status";
import type { TimelineEvent } from "../lib/orders";

/**
 * OrderTimeline (DESIGN.md): chronological event list using the
 * canonical event vocabulary. Oldest-first; an empty timeline says so
 * instead of rendering a blank area.
 */
export function OrderTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <p role="status">No events recorded for this order yet.</p>;
  }
  const ordered = sortTimelineEvents(events);
  return (
    <ol className="order-timeline">
      {ordered.map((event, index) => (
        <li key={`${event.event_type}-${event.occurred_at}-${index}`} className="timeline-event">
          <p className="timeline-event-type">
            <code>{event.event_type}</code>
          </p>
          <p className="timeline-event-time">
            <time dateTime={event.occurred_at}>{formatOccurredAt(event.occurred_at)}</time>
          </p>
          <PayloadDetail payload={event.payload} />
        </li>
      ))}
    </ol>
  );
}

function PayloadDetail({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload);
  if (entries.length === 0) return null;
  return (
    <dl className="timeline-payload">
      {entries.map(([key, value]) => (
        <div key={key} className="timeline-payload-row">
          <dt>{key}</dt>
          <dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
