# API reference

Base URL: `http://web:8000/api/`, reachable only inside the Docker network (locally also `localhost:8000` with `docker-compose.dev.yml`). All requests/responses are JSON. Auth header: `Authorization: Token <key>`.

Legend: **user** = any authenticated user's token, **admin** = staff user's token (`ADMIN_TOKEN`).

## Obtaining a token

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/register-telegram/` | admin | `{"telegram_id": 123}` → `{"token"}`. `201` for a new user, `200` if it already exists, `400` if `telegram_id` is missing or not an integer. Limited to 10/minute per `telegram_id` |

## CRUD resources (user)

Standard DRF router: `GET` list, `POST` create, `GET/PUT/PATCH/DELETE` on `/<id>/`. Each user only sees and edits their own rows. Amounts must be positive.

| Path | Fields (writable) | Notes |
|------|-------------------|-------|
| `/api/expenses/` | `amount`, `category`, `description`, `date` | `date` is optional: defaults to today in the user's timezone, cannot be in the future. `currency` comes from the profile. `category` must be shared or owned, else `400 Invalid category` |
| `/api/income/` | `amount`, `description` | `date` and `currency` are set by the server |
| `/api/categories/` | `name` | list/retrieve include shared categories (`user: null`); create/update/delete only touch own ones; deleting a shared one → `403`. Deleting also removes the category's expenses and regular payments; retrieve reports them as `expense_count` and `payment_count` |
| `/api/user-profile/` | `currency`, `savings_goal`, `notification_status`, `timezone` | `GET` and `PATCH` only: profiles are created on registration |
| `/api/regular-payments/` | `name`, `amount`, `category`, `payment_day` (1–31) | read-only `category_name` is included in responses. A day that has already passed starts next month |

Currencies: `PLN`, `UAH`, `EUR`, `USD`.

## Helper endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/stats/` | user | Current month in the user's timezone: `month`, `categories` (per category and currency totals), `total` and `income` (per currency), `daily_limit` (negative when over budget), `currency`, `currency_mismatch` |
| GET | `/api/history/` | user | This month's expenses, newest first: `amount`, `category__name`, `date`, `description`, `currency` |
| GET | `/api/get-profile/` | user | Same body as the setters below |
| POST | `/api/set-currency/` | user | `{"currency": "EUR"}` → updated profile |
| POST | `/api/set-savings-goal/` | user | `{"savings_goal": 500}` → updated profile |
| POST | `/api/set-timezone/` | user | `{"timezone": "Europe/Kyiv"}` → updated profile |
| POST | `/api/notification-status/` | user | `{"notification_status": false}` → updated profile |
| GET | `/api/all-telegram-ids/` | admin | `[{"telegram_id", "notification_status", "timezone"}, …]` |
| POST | `/api/disable-notifications/` | admin | `{"telegram_id": 123}` → `200`; `400` bad id; `404` unknown id |
| POST | `/api/process-regular-payments/` | admin | Charges due regular payments, returns `{"created": N}`. Safe to repeat: charges once a month, by the user's local date |

## Errors

- `401` — missing/invalid token; `403` — authenticated but not allowed (e.g. non-admin on an admin endpoint, deleting a shared category); `400` — validation error with field messages; `429` — over the limit (120/minute per user, except the bot's own admin jobs), `Retry-After` holds the seconds to wait.

## Example

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/register-telegram/ \
  -H "Authorization: Token $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"telegram_id": 42}' | jq -r .token)

curl -X POST localhost:8000/api/expenses/ \
  -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" \
  -d '{"amount": "12.50", "category": 1}'

curl localhost:8000/api/stats/ -H "Authorization: Token $TOKEN"
```
