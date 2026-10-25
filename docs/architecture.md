# Architecture

```
Telegram user ⇄ Telegram ⇄ bot.py (polling) ──HTTP, Token auth──▶ Django REST API ──▶ PostgreSQL
                              │
                              └─ APScheduler: daily reminder (19:00), regular payments (00:00 + on startup)
```

The project is two processes sharing one codebase:

| Process | Entry point | Role |
|---------|-------------|------|
| `web`   | `gunicorn fintrack.wsgi` | Django + DRF API, owns all data and business logic |
| `bot`   | `python bot.py` | Telegram front-end; holds no data, only calls the API |

## Repository layout

| Path | Purpose |
|------|---------|
| `bot.py` | Telegram bot: handlers, inline keyboards, scheduler jobs |
| `fintrack/` | Django project (settings, root URLs, WSGI/ASGI) |
| `expenses/models.py` | Data models |
| `expenses/serializers.py` | DRF serializers, category ownership validation |
| `expenses/views.py` | ViewSets and function-based API views |
| `expenses/urls.py` | Router + extra endpoints (mounted under `/api/`) |
| `expenses/tests/` | pytest suite (see [Testing](#testing)) |
| `docker-compose.yml`, `dockerfile` | `db`, `web`, `bot` services |
| `.github/workflows/tests.yml` | CI: pytest against PostgreSQL 16 |

## Data model

- **User** (Django built-in) — one per Telegram account, username `tg_<telegram_id>`, no password.
- **TelegramUser** — `telegram_id` (unique) ↔ User, one-to-one.
- **UserProfile** — per user: `currency` (PLN/UAH/EUR/USD), `savings_goal` (nullable, ≥ 0), `notification_status` (default on). Created lazily via `get_or_create`.
- **Category** — `name`, nullable `user`. `user IS NULL` means a shared category visible to everyone; read-only for regular users.
- **Expense** — `amount`, `category`, `date` (auto, set on creation), `description`, `user`, `currency` (copied from the profile at creation time).
- **Income** — like Expense without a category.
- **RegularPayments** — `name`, `amount`, `category`, `payment_day` (1–31), `user`, `last_charged` (date of the last auto-charge).

## Authentication and authorization

- Two token kinds, both DRF `TokenAuthentication`:
  - **Admin token** (`ADMIN_TOKEN`, the token of a staff user) — held only by the bot. Used for `IsAdminUser` endpoints: registration, listing Telegram ids, processing regular payments, disabling notifications.
  - **Per-user token** — returned by `register-telegram/`; the bot caches it in `context.user_data` and sends it for everything user-scoped.
- Default permission is `IsAuthenticated`. Every ViewSet filters its queryset by `request.user`, so users only see their own rows.
- Foreign categories are rejected in `ExpenseSerializer` / `RegularPaymentsSerializer` (`validate_category` → 400 `Invalid category`).

## Bot behaviour

- Commands: `/start`, `/stats`, `/history`, `/income`, `/settings`, `/help`.
- Sending a plain number starts an expense: the bot stores the amount and shows category buttons; the chosen category posts the expense, with a 🗑 Cancel button to delete it.
- Multi-step input (new category, savings goal, income, regular payment name → amount → day) is a small state machine in `context.user_data["state"]`.
- Inline-button callbacks are routed by `callback_data` prefix (`settings_`, `cat_`, `currency_`, `reg_`, `delexp_`, …) into `handle_settings_callback`.
- `user_data` lives in process memory: after a bot restart the token is re-fetched on the next message and any half-finished input is lost.

## Scheduled jobs (APScheduler, in the bot process)

| Job | When | What |
|-----|------|------|
| `send_daily_reminder` | daily 19:00 (server time) | `GET all-telegram-ids/`, message everyone with notifications on. A `Forbidden` (user blocked the bot) turns that user's notifications off via `disable-notifications/`; other errors are logged and the loop continues |
| `process_regular_payments` | daily 00:00 and once on bot startup | `POST process-regular-payments/` |

### Regular payments logic

A payment is charged when it has not been charged this month (`last_charged` is null or before the 1st) **and** `payment_day <= today`. On the last day of a month, payments with `payment_day` 29–31 are also due. Charging creates an `Expense` and sets `last_charged`, all in one transaction. Because it is idempotent, repeated or catch-up calls are safe.

### Daily limit (`/api/stats/`)

```
daily_limit = (income − savings_goal − expenses) // remaining_days_in_month
```

Only amounts in the profile currency are counted; `currency_mismatch` is `true` if there are records in other currencies. Remaining days include today.

## Testing

```
pytest
```

Needs PostgreSQL (see `docs/deployment.md`). Suites: expenses API, user profile, registration, category isolation, API defaults (auth/permission settings), disable-notifications, regular payments processing.
