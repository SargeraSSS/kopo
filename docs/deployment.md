# Setup and deployment

## Configuration

Copy `.env.example` to `.env` and fill it in.

| Variable | Used by | Description |
|----------|---------|-------------|
| `SECRET_KEY` | web | Django secret key (required) |
| `DEBUG` | web | `True` only for local development; anything else is `False` |
| `ALLOWED_HOSTS` | web | Comma-separated; default `web,localhost,127.0.0.1` |
| `LOG_LEVEL` | web | Default `INFO` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | web, db | PostgreSQL connection (compose overrides `DB_HOST` with `db`) |
| `BOT_TOKEN` | bot | Token from @BotFather |
| `ADMIN_TOKEN` | bot | Token of a staff user (see below) |
| `API_URL` | bot | API base, e.g. `http://localhost:8000/api` (compose sets `http://web:8000/api`) |

## Run with Docker Compose

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser        # staff user for the bot
docker compose exec web python manage.py drf_create_token <username>
# put the printed key into .env as ADMIN_TOKEN, then:
docker compose up -d bot
docker compose logs -f bot
```

Notes:
- `web` runs `collectstatic` and then gunicorn on port 8000. Static files are served by WhiteNoise.
- PostgreSQL is published only on `127.0.0.1:5432`; data lives in the `postgres_data` volume.
- On boot the bot calls `process-regular-payments/` once. If `web` is not ready yet it logs `API unreachable` and retries at midnight.

## Local development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# start a local PostgreSQL and set DB_* in .env
python manage.py migrate
python manage.py runserver        # API on :8000
python bot.py                     # bot, in another terminal
```

Python 3.13 is used in Docker and CI.

## Tests and CI

```bash
pytest
```

Requires a reachable PostgreSQL with the `DB_*` variables set (CI uses a `postgres:16` service, database `fintrack_test`). GitHub Actions runs the suite on every push and pull request to `main`.

## Production checklist

- `DEBUG=False`, a strong `SECRET_KEY`, `ALLOWED_HOSTS` set to the real hostname.
- Put a TLS-terminating reverse proxy (Caddy/nginx) in front of gunicorn — Token auth is sent in clear text otherwise.
- Keep `ADMIN_TOKEN` secret: it can register users, list all Telegram ids and trigger charges.
- Reminders fire at 19:00 in the bot server's time zone; there is no per-user time zone yet.
- Back up the `postgres_data` volume.
