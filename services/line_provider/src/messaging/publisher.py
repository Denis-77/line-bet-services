from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone
from typing import Protocol

import aio_pika
from aio_pika.abc import AbstractRobustConnection, AbstractRobustExchange
from aio_pika.exceptions import AMQPException

from src.core.config import settings
from src.schemas.event import Event

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    async def publish_status_changed(self, event: Event) -> None: ...


def _create_message(event: Event) -> aio_pika.Message:
    payload = {
        "event_id": event.id,
        "status": event.status.value,
        "coefficient": str(event.coefficient),
        "deadline": event.deadline.astimezone(timezone.utc).isoformat(),
        "version": event.version,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload).encode("utf-8")

    message_id = f"{event.id}:{event.version}"

    return aio_pika.Message(
        body=body,
        message_id=message_id,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )


class RabbitMQPublisher:
    """Publishes event status changes to a durable RabbitMQ exchange.

    Buffers messages in-memory if RabbitMQ is unavailable and retries in the
    background so that producer-side hiccups don't lose status changes.
    """

    def __init__(
        self,
        url: str = settings.RABBITMQ_URL,
        exchange_name: str = settings.RABBITMQ_EXCHANGE,
        routing_key: str = settings.RABBITMQ_ROUTING_KEY,
        retry_interval_seconds: float = settings.PUBLISH_RETRY_INTERVAL_SECONDS,
    ) -> None:
        self._url = url
        self._exchange_name = exchange_name
        self._routing_key = routing_key
        self._retry_interval_seconds = retry_interval_seconds

        self._connection: AbstractRobustConnection | None = None
        self._exchange: AbstractRobustExchange | None = None
        self._pending: list[aio_pika.Message] = []
        self._pending_lock = asyncio.Lock()
        self._retry_task: asyncio.Task[None] | None = None
        self._closing = False

    async def start(self) -> None:
        self._closing = False
        try:
            await self._connect()
        except (AMQPException, ConnectionError, asyncio.TimeoutError) as exc:
            logger.error(
                "Failed to connect to RabbitMQ on startup: %s. Will retry in background.",
                type(exc).__name__,
            )

        self._retry_task = asyncio.create_task(
            self._retry_loop(), name="publisher-retry"
        )

    async def stop(self) -> None:
        self._closing = True
        if self._retry_task is not None:
            self._retry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retry_task
            self._retry_task = None

        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
        self._exchange = None

    async def _connect(self) -> AbstractRobustExchange:
        """
        Initializes a robust connection.
        aio_pika takes care of re-creating channels when they are lost.
        """
        if (
            self._exchange is not None
            and self._connection is not None
            and not self._connection.is_closed
        ):
            return self._exchange

        connection = await aio_pika.connect_robust(self._url)
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange(
            self._exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        self._connection = connection
        self._exchange = exchange
        return exchange

    async def publish_status_changed(self, event: Event) -> None:
        message = _create_message(event)

        try:
            exchange = await self._connect()
            await exchange.publish(
                message,
                routing_key=self._routing_key,
            )
            logger.info(
                "Published status change for event %s (version=%d)",
                event.id,
                event.version,
            )
        except (AMQPException, ConnectionError, asyncio.TimeoutError) as exc:
            logger.error(
                "Failed to publish event %s status change due to %s. Buffering for retry.",
                event.id,
                type(exc).__name__,
            )
            async with self._pending_lock:
                self._pending.append(message)

    async def _retry_loop(self) -> None:
        while not self._closing:
            try:
                await asyncio.sleep(self._retry_interval_seconds)

                async with self._pending_lock:
                    if not self._pending:
                        continue
                    buffered = list(self._pending)

                if not buffered:
                    continue

                try:
                    exchange = await self._connect()
                    for message in buffered:
                        await exchange.publish(
                            message,
                            routing_key=self._routing_key,
                        )

                    async with self._pending_lock:
                        self._pending = self._pending[len(buffered) :]
                    logger.info(
                        "Successfully replayed %d buffered messages to RabbitMQ",
                        len(buffered),
                    )

                except (AMQPException, ConnectionError, asyncio.TimeoutError) as exc:
                    logger.warning(
                        "Retry to RabbitMQ failed (%s), will try again later.",
                        type(exc).__name__,
                    )

            except asyncio.CancelledError:
                break


publisher = RabbitMQPublisher()
