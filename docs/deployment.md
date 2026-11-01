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
| `REDIS_URL` | web | Cache for rate-limit counters (compose sets it); without it each process counts on its own |
| `COMPOSE_FILE` | compose | Local only, see below |

## Run with Docker Compose

`docker-compose.yml` is the production setup and publishes no ports: the bot polls Telegram and reaches the API over the internal Docker network. Locally, add this line to `.env` to get the ports and live code from `docker-compose.dev.yml`:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml
```

First start:

```bash
docker compose up -d --build web
docker compose exec web python manage.py shell -c \
  "from django.contrib.auth.models import User; User.objects.create_user('bot', is_staff=True)"
docker compose exec web python manage.py drf_create_token bot
# put the printed key into .env as ADMIN_TOKEN, then:
docker compose up -d
docker compose logs -f bot
```

Notes:
- `web` runs `migrate`, `collectstatic` and then gunicorn with 2 workers. Static files are served by WhiteNoise.
- The bot's user is staff, not a superuser, and has no password: it needs nothing more.
- Data lives in the `postgres_data` volume. Redis holds only rate-limit counters and keeps nothing on disk.
- On boot the bot calls `process-regular-payments/` once. Compose starts `bot` only after `web` passes its healthcheck; a failed call logs `API unreachable` and the job retries within the hour.
- Containers restart by themselves after a crash or a server reboot; logs are rotated at 3 × 10 MB.

## Deploy and roll back

```bash
./deploy.sh            # back up, then run the latest origin/main
./deploy.sh v1.2       # back up, then run a tag or commit
./backup.sh            # dump the database into backups/, last 14 days are kept
```

Restore:

```bash
gunzip -c backups/<file>.sql.gz | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

Daily backups, in the deploy user's crontab: `0 3 * * * /path/to/tg_fintrack/backup.sh`.

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

- `DEBUG=False`, a new strong `SECRET_KEY` (50+ characters), new `DB_PASSWORD` and `ADMIN_TOKEN`.
- `BOT_TOKEN` of the production bot. A token can be polled from one place only, otherwise Telegram answers `Conflict`.
- No `COMPOSE_FILE` in the server's `.env`.
- Check from another machine that 5432, 6379 and 8000 are closed. Docker bypasses ufw, so the only reliable protection is not publishing ports at all.
- `check --deploy` warnings about HTTPS, HSTS and secure cookies do not apply: the API has no public TLS endpoint. Reach `/admin/` through an SSH tunnel to the container.
- Keep `ADMIN_TOKEN` secret: it can register users, list all Telegram ids and trigger charges.
