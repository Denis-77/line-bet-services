# Bet Services

Two independent async FastAPI services that together accept and settle user bets.

- **line-provider** — keeps the list of events in memory and exposes a small CRUD API. On any status change it publishes a durable, persistent message to RabbitMQ.
- **bet-maker** — accepts bets, stores them in PostgreSQL, and updates their statuses based on events consumed from RabbitMQ. Exposes the public betting API.

## Architecture

```text
                +---------------------+
client/curl --> | line-provider :8001 |  (in-memory events, REST API)
                +----------+----------+
                           |
              durable, persistent messages
                  via RabbitMQ topic exchange "events"
                           |
                           v
                +---------------------+
                |  bet-maker-worker   |  reconcile + RabbitMQ consumer
                +----------+----------+
                           |
                           v
                +---------------------+      +-------------------+
                |   bet-maker :8002   | <--> | PostgreSQL bets   |
                +---------------------+      +-------------------+
                           ^
                           | REST: GET /events, POST /bet, GET /bets
                       client/curl
```

## Reliability and performance notes

- **Durable transport.** The `events` exchange and `bet-maker.events` queue in RabbitMQ are durable. Messages are sent with `delivery_mode=persistent` and consumed with manual ack.
- **Dead-letter queue.** Malformed or failing messages are rejected to `events.dlx` so they don't block live traffic.
- **Idempotency.** Each event carries a monotonic `version`. `events_cache` is updated only when the incoming version is strictly newer, so re-deliveries and out-of-order messages are safe.
- **No bets stuck in PENDING.** `bet_maker.workers.consumer` runs an initial reconcile against `GET /events` on the line-provider and re-applies terminal statuses to any PENDING bets. A periodic reconcile (default every 60s) re-runs in the background to recover from message loss or downtime.
- **Hot path.** `POST /bet` and `GET /events` work entirely against the local PostgreSQL snapshot (`events_cache`) — no synchronous calls to line-provider unless the cache misses (e.g. immediately after startup), and the snapshot is then populated in a single round-trip.
- **Async everywhere.** FastAPI, `asyncpg`+SQLAlchemy 2.0 async, `aio-pika`, `httpx.AsyncClient`.

## Run the whole stack

```bash
docker compose up --build
```

This brings up `postgres`, `rabbitmq` (with management UI on http://localhost:15672, guest/guest), `line-provider` (http://localhost:8001), `bet-maker` (http://localhost:8002), and a separate `bet-maker-worker` process consuming RabbitMQ.

Open API docs:

- line-provider: http://localhost:8001/docs
- bet-maker: http://localhost:8002/docs

## End-to-end flow with curl

Create an event in line-provider with a deadline 1 hour into the future:

```bash
curl -s -X POST http://localhost:8001/events \
  -H 'Content-Type: application/json' \
  -d "{\"id\":\"match-1\",\"coefficient\":\"1.80\",\"deadline\":\"$(date -u -v+1H '+%Y-%m-%dT%H:%M:%SZ')\"}"
```

List active events (either service works; bet-maker reads from its local cache):

```bash
curl -s http://localhost:8001/events?active=true
curl -s http://localhost:8002/events
```

Place a bet:

```bash
curl -s -X POST http://localhost:8002/bet \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"match-1","amount":"15.50"}'
```

List bets:

```bash
curl -s http://localhost:8002/bets
```

Mark the event finished — first team won:

```bash
curl -s -X PATCH http://localhost:8001/events/match-1 \
  -H 'Content-Type: application/json' \
  -d '{"status":"FIRST_TEAM_WON"}'
```

After the worker picks up the message (≤ 1s), the bet status is `WON`:

```bash
curl -s http://localhost:8002/bets
```

The valid event statuses are `NEW`, `FIRST_TEAM_WON`, `FIRST_TEAM_LOST`.
Bet statuses are `PENDING`, `WON`, `LOST`.

## Local development

Each service is an independent Python project under `services/`.

```bash
# line-provider
python3.10 -m venv .venv-lp
source .venv-lp/bin/activate
pip install -e "services/line_provider[dev]"
cd services/line_provider && pytest

# bet-maker
python3.10 -m venv .venv-bm
source .venv-bm/bin/activate
pip install -e "services/bet_maker[dev]"
cd services/bet_maker && pytest
```

Lint and format:

```bash
ruff check app tests
black --check app tests
mypy app
```

Run migrations against a running Postgres (the docker-compose service handles this automatically):

```bash
cd services/bet_maker
BM_DATABASE_URL=postgresql+asyncpg://bet_maker:bet_maker@localhost:5432/bet_maker \
  alembic upgrade head
```

## Configuration

Environment variables (prefixed `LP_` for line-provider, `BM_` for bet-maker):

| Variable | Default | Description |
|----------|---------|-------------|
| `LP_HOST` / `LP_PORT` | `0.0.0.0` / `8000` | Bind address |
| `LP_RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ DSN |
| `LP_RABBITMQ_EXCHANGE` | `events` | Exchange name |
| `BM_DATABASE_URL` | `postgresql+asyncpg://bet_maker:bet_maker@localhost:5432/bet_maker` | PostgreSQL DSN |
| `BM_RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ DSN |
| `BM_RABBITMQ_QUEUE` | `bet-maker.events` | Consumer queue |
| `BM_RABBITMQ_DLX_EXCHANGE` | `events.dlx` | Dead-letter exchange |
| `BM_LINE_PROVIDER_URL` | `http://localhost:8001` | line-provider base URL |
| `BM_RECONCILE_INTERVAL_SECONDS` | `60.0` | Periodic reconcile cadence |
| `BM_RABBITMQ_PREFETCH_COUNT` | `50` | Worker prefetch |

## Project layout

```
betting_software/
├── docker-compose.yml
├── README.md
└── services/
    ├── line_provider/
    │   ├── app/
    │   │   ├── api/events.py            # CRUD endpoints
    │   │   ├── core/                    # config, logging
    │   │   ├── models/event.py          # pydantic event model
    │   │   ├── storage/memory.py        # in-memory storage
    │   │   ├── messaging/publisher.py   # RabbitMQ publisher
    │   │   └── main.py
    │   └── tests/
    └── bet_maker/
        ├── alembic/
        ├── app/
        │   ├── api/                     # /events, /bet, /bets
        │   ├── core/                    # config, logging
        │   ├── db/                      # SQLAlchemy engine/session
        │   ├── messaging/               # line-provider HTTP client
        │   ├── models/                  # Bet, EventCache
        │   ├── repositories/            # data access
        │   ├── schemas/                 # pydantic DTOs
        │   ├── services/                # business logic
        │   ├── workers/                 # consumer + reconcile
        │   └── main.py
        └── tests/
```
