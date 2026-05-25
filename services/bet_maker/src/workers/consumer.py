from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import signal
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from src.core.config import settings
from src.core.logging import configure_logging
from src.db.session import dispose_engine, get_session_factory
from src.messaging.line_provider_client import (
    close_line_provider_client,
    get_line_provider_client,
)
from src.schemas.event import EventStatusMessage
from src.workers.handler import handle_status_message
from src.workers.reconcile import reconcile_events

logger = logging.getLogger(__name__)


async def _on_message(message: AbstractIncomingMessage) -> None:
    try:
        body: Any = json.loads(message.body.decode("utf-8"))
        payload = EventStatusMessage.model_validate(body)
    except Exception:
        logger.exception("Bad message format, rejecting to DLX: %r", message.body)
        await message.reject(requeue=False)
        return

    session_factory = get_session_factory()
    line_provider = get_line_provider_client()
    try:
        async with session_factory() as session:
            await handle_status_message(session, line_provider, payload)
        await message.ack()
        logger.info(
            "Processed status update for event %s (version=%d, status=%s)",
            payload.event_id,
            payload.version,
            payload.status,
        )
    except Exception:
        logger.exception(
            "Failed to process message for event %s, sending to DLX",
            payload.event_id,
        )
        await message.reject(requeue=False)


async def _setup_topology(
    channel: aio_pika.abc.AbstractRobustChannel,
) -> aio_pika.abc.AbstractRobustQueue:
    main_exchange = await channel.declare_exchange(
        settings.RABBITMQ_EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    dlx_exchange = await channel.declare_exchange(
        settings.RABBITMQ_DLX_EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )
    dlq = await channel.declare_queue(settings.RABBITMQ_DLQ, durable=True)
    await dlq.bind(dlx_exchange, routing_key="#")

    queue = await channel.declare_queue(
        settings.RABBITMQ_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": settings.RABBITMQ_DLX_EXCHANGE,
        },
    )
    await queue.bind(main_exchange, routing_key=settings.RABBITMQ_ROUTING_KEY)
    return queue


async def run() -> None:
    configure_logging()
    logger.info("Starting bet-maker consumer")

    line_provider = get_line_provider_client()
    session_factory = get_session_factory()

    try:
        await reconcile_events(session_factory, line_provider)
    except Exception:
        logger.exception("Initial reconcile crashed, continuing to consume")

    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=settings.RABBITMQ_PREFETCH_COUNT)

    queue = await _setup_topology(channel)

    stop_event = asyncio.Event()

    def _stop(*_: object) -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _stop)

    async def _periodic_reconcile() -> None:
        try:
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=settings.RECONCILE_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    await reconcile_events(session_factory, line_provider)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Periodic reconcile crashed")

    reconcile_task = asyncio.create_task(_periodic_reconcile(), name="periodic-reconcile")

    consumer_tag = await queue.consume(_on_message)
    logger.info("Listening for messages on %s", settings.RABBITMQ_QUEUE)

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutting down consumer")
        await queue.cancel(consumer_tag)
        reconcile_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reconcile_task
        await channel.close()
        await connection.close()
        await close_line_provider_client()
        await dispose_engine()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
