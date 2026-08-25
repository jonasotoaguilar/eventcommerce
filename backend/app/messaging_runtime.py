import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
_CAP = 30.0
_BASE = 1.0


def _jittered_backoff(
    attempt: int,
    base: float = _BASE,
    cap: float = _CAP,
    jitter: Callable[[float, float], float] = random.uniform,
) -> float:
    return jitter(0, min(cap, base * (2**attempt)))


def _inventory_handler_factory(session: AsyncSession):  # type: ignore[no-untyped-def]
    from app.modules.inventory.api.container import InventoryContainer
    from app.modules.orders.api.container import OrdersContainer

    orders_c = OrdersContainer()
    inventory_c = InventoryContainer()
    orders_c.session.override(session)
    inventory_c.session.override(session)
    get_status = orders_c.get_order_status()
    inventory_c.order_status_query.override(get_status)
    handler = inventory_c.process_inventory_reservation()

    async def _handle(  # type: ignore[no-untyped-def]
        *, payload: dict, event_id: str, event_type: str, aggregate_id: str
    ) -> None:
        if event_type != "OrderCreated":
            raise ValueError(f"unsupported event_type: {event_type}")
        UUID(str(aggregate_id))
        UUID(str(event_id))
        items = payload["items"]
        if not isinstance(items, list):
            raise ValueError("items must be list")
        await handler.execute(event_id=event_id, order_id=aggregate_id, items=items)

    return _handle


def _orders_handler_factory(session: AsyncSession):  # type: ignore[no-untyped-def]
    from app.modules.orders.api.container import OrdersContainer

    orders_c = OrdersContainer()
    orders_c.session.override(session)
    handler = orders_c.process_order_inventory_result()

    async def _handle(  # type: ignore[no-untyped-def]
        *, payload: dict, event_id: str, event_type: str, aggregate_id: str
    ) -> None:
        if event_type == "InventoryReserved":
            result = "reserved"
        elif event_type == "InventoryRejected":
            result = "rejected"
        else:
            raise ValueError(f"unsupported event_type: {event_type}")
        order_id = UUID(str(aggregate_id))
        UUID(str(event_id))
        _ = payload  # payload not used beyond validation, keep exact contract
        await handler.execute(event_id=event_id, order_id=order_id, result=result)

    return _handle


def _notifications_handler_factory(session: AsyncSession):  # type: ignore[no-untyped-def]
    from app.modules.notifications.api.container import NotificationsContainer

    notifications_c = NotificationsContainer()
    notifications_c.session.override(session)
    handler = notifications_c.process_order_notification()

    async def _handle(  # type: ignore[no-untyped-def]
        *, payload: dict, event_id: str, event_type: str, aggregate_id: str
    ) -> None:
        await handler.execute(
            payload=payload,
            event_id=event_id,
            event_type=event_type,
            aggregate_id=aggregate_id,
        )

    return _handle


def _create_wired_consumer(session_factory, settings):  # type: ignore[no-untyped-def]
    from app.shared.messaging.consumer import ConsumerBinding, MessageConsumer

    bindings = [
        ConsumerBinding(
            queue="inventory.order_created",
            event_types=("OrderCreated",),
            consumer_name="ProcessInventoryReservation",
            handler_factory=_inventory_handler_factory,
        ),
        ConsumerBinding(
            queue="orders.inventory_result",
            event_types=("InventoryReserved", "InventoryRejected"),
            consumer_name="ProcessOrderInventoryResult",
            handler_factory=_orders_handler_factory,
        ),
        ConsumerBinding(
            queue="notifications.order_terminal",
            event_types=("OrderConfirmed", "OrderCancelled"),
            consumer_name="ProcessOrderNotification",
            handler_factory=_notifications_handler_factory,
        ),
    ]
    return MessageConsumer(settings.rabbitmq_url, bindings, session_factory)


class MessagingRuntime:
    def __init__(
        self,
        publisher,
        consumer,
        outbox_worker,
        poll_interval: float,
        batch_size: int,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._publisher = publisher
        self._consumer = consumer
        self._worker = outbox_worker
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._sleep = sleep
        self._jitter = jitter
        self._scheduler_task: asyncio.Task | None = None
        self._publisher_task: asyncio.Task | None = None
        self._consumer_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._stopped = False

    async def start(self) -> None:
        self._stop.clear()
        self._stopped = False
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        if self._publisher is not None:
            self._publisher_task = asyncio.create_task(
                self._retry_loop(self._publisher.connect, "publisher")
            )
        if self._consumer is not None:

            async def _cons() -> None:
                await self._consumer.connect()  # type: ignore[union-attr]
                await self._consumer.start()  # type: ignore[union-attr]

            self._consumer_task = asyncio.create_task(
                self._retry_loop(_cons, "consumer")
            )
        logger.info(
            "messaging_runtime_started poll_interval=%s batch_size=%s",
            self._poll_interval,
            self._batch_size,
        )

    async def _retry_loop(self, fn: Callable[[], Awaitable[None]], name: str) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                await fn()
                logger.info("messaging_%s_connected", name)
                return
            except Exception:
                delay = _jittered_backoff(attempt, jitter=self._jitter)
                logger.warning(
                    "messaging_%s_connect_retry attempt=%s delay=%.2f",
                    name,
                    attempt,
                    delay,
                )
                attempt += 1
                try:
                    await self._sleep(delay)
                except asyncio.CancelledError:
                    return

    async def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._worker.run_once(batch_size=self._batch_size)
            except Exception:
                logger.exception("messaging_outbox_scheduler_failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stop.set()
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await asyncio.wait_for(self._scheduler_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                logger.exception("messaging_scheduler_stop_failed")
        for t in (self._publisher_task, self._consumer_task):
            if t is not None:
                t.cancel()
                try:
                    await asyncio.wait_for(t, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        async def _close() -> None:
            if self._publisher is not None:
                try:
                    await self._publisher.close()  # type: ignore[union-attr]
                except Exception:
                    logger.exception("messaging_publisher_close_failed")
            if self._consumer is not None:
                try:
                    await self._consumer.close()  # type: ignore[union-attr]
                except Exception:
                    logger.exception("messaging_consumer_close_failed")

        try:
            await asyncio.wait_for(_close(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("messaging_runtime_shutdown_timeout")
        self._stopped = True
        logger.info("messaging_runtime_stopped")


def create_messaging_runtime(
    settings,
    session_factory,
    *,
    publisher=None,
    consumer=None,
    outbox_worker=None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> MessagingRuntime:
    poll = settings.rabbitmq_outbox_poll_interval
    batch = settings.rabbitmq_outbox_batch_size
    if outbox_worker is None:
        from app.shared.messaging.outbox_worker import OutboxWorker
        from app.shared.messaging.rabbitmq_publisher import RabbitMQPublisher

        pub = publisher or RabbitMQPublisher(settings.rabbitmq_url)
        worker = OutboxWorker(session_factory, pub)
        cons = (
            consumer
            if consumer is not None
            else _create_wired_consumer(session_factory, settings)
        )
        return MessagingRuntime(
            pub, cons, worker, poll, batch, sleep=sleep, jitter=jitter
        )
    cons = (
        consumer
        if consumer is not None
        else _create_wired_consumer(session_factory, settings)
    )
    return MessagingRuntime(
        publisher, cons, outbox_worker, poll, batch, sleep=sleep, jitter=jitter
    )
