# API reference

Base URL: `<host>/api/`. All requests/responses are JSON. Auth header: `Authorization: Token <key>`.

Legend: **user** = any authenticated user's token, **admin** = staff user's token (`ADMIN_TOKEN`).

## Obtaining a token

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/token/` | none | DRF `obtain_auth_token`: `{"username", "password"}` → `{"token"}` |
| POST | `/api/register-telegram/` | admin | `{"telegram_id": 123}` → `{"token"}`. `201` for a new user, `200` if it already exists, `400` if `telegram_id` is missing or not an integer |

## CRUD resources (user)

Standard DRF router: `GET` list, `POST` create, `GET/PUT/PATCH/DELETE` on `/<id>/`. Each user only sees and edits their own rows.

| Path | Fields (writable) | Notes |
|------|-------------------|-------|
| `/api/expenses/` | `amount`, `category`, `description` | `date` and `currency` are set by the server (currency from profile). `category` must be shared or owned, else `400 Invalid category` |
| `/api/income/` | `amount`, `description` | same server-set `date`/`currency` |
| `/api/categories/` | `name` | list/retrieve include shared categories (`user: null`); create/update/delete only touch own ones; deleting a shared one → `403` |
| `/api/user-profile/` | `currency`, `savings_goal`, `notification_status` | |
| `/api/regular-payments/` | `name`, `amount`, `category`, `payment_day` (1–31) | read-only `category_name` is included in responses |

Currencies: `PLN`, `UAH`, `EUR`, `USD`.

## Helper endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/stats/` | user | Current month: `month`, `categories` (per category and currency totals), `total` and `income` (per currency), `daily_limit`, `currency`, `currency_mismatch` |
| GET | `/api/history/` | user | This month's expenses, newest first: `amount`, `category__name`, `date`, `description`, `currency` |
| GET | `/api/get-profile/` | user | `currency`, `savings_goal`, `notification_status` |
| POST | `/api/set-currency/` | user | `{"currency": "EUR"}` → updated profile |
| POST | `/api/set-savings-goal/` | user | `{"savings_goal": 500}` → updated profile |
| POST | `/api/notification-status/` | user | `{"notification_status": false}` → updated profile |
| GET | `/api/all-telegram-ids/` | admin | `[{"telegram_id", "notification_status"}, …]` |
| POST | `/api/disable-notifications/` | admin | `{"telegram_id": 123}` → `200`; `400` bad id; `404` unknown id |
| POST | `/api/process-regular-payments/` | admin | Charges due regular payments, returns `{"created": N}`. Idempotent per month |

## Errors

- `401` — missing/invalid token; `403` — authenticated but not allowed (e.g. non-admin on an admin endpoint, deleting a shared category); `400` — validation error with field messages.

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
