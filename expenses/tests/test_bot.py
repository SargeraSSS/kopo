"""bot.py with the API replaced by httpx.MockTransport and Telegram by mocks."""

import asyncio
import json
from types import SimpleNamespace
from unittest import mock

import httpx
import pytest
from telegram.error import Forbidden, NetworkError, RetryAfter
from telegram.ext import ApplicationHandlerStop

import bot


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def api(monkeypatch):
    """Route API calls to api.handler and record them in api.calls."""
    state = SimpleNamespace(calls=[], handler=lambda request: httpx.Response(200))

    def transport(request):
        state.calls.append(request)
        return state.handler(request)

    monkeypatch.setattr(bot, "API_URL", "http://api")
    monkeypatch.setattr(
        bot, "api_client", httpx.AsyncClient(transport=httpx.MockTransport(transport))
    )
    return state


def unreachable(request):
    raise httpx.ConnectError("down")


def message_update(text, user_id=1):
    message = mock.AsyncMock()
    message.text = text
    return SimpleNamespace(
        message=message,
        callback_query=None,
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id),
    )


def button_update(data):
    query = mock.AsyncMock()
    query.data = data
    return SimpleNamespace(
        message=None,
        callback_query=query,
        effective_message=query.message,
        effective_user=SimpleNamespace(id=1),
    )


def context(**user_data):
    return SimpleNamespace(user_data={"token": "abc", **user_data})


@pytest.mark.parametrize(
    "text, expected",
    [("100", "100"), ("12.50", "12.50"), ("12,50", "12.50"), (" 7 ", "7")],
)
def test_parse_amount_accepts_numbers(text, expected):
    assert str(bot.parse_amount(text)) == expected


@pytest.mark.parametrize(
    "text", ["abc", "", "nan", "NaN", "inf", "-inf", "Infinity", "sNaN", "-5", "0"]
)
def test_parse_amount_rejects_everything_else(text):
    assert bot.parse_amount(text) is None


def test_split_text_keeps_every_piece_within_the_limit():
    lines = [f"2026-03-{i:04} — Food — 100.00 PLN\n" for i in range(500)]

    chunks = bot.split_text("".join(lines))

    assert len(chunks) > 1
    assert all(len(chunk) <= 4096 for chunk in chunks)
    assert "".join(chunks) == "".join(lines)


def test_error_text_shows_the_retry_time():
    response = httpx.Response(429, headers={"Retry-After": "30"})

    assert "30 seconds" in bot.error_text(response)


def test_error_text_shows_the_validation_message():
    response = httpx.Response(400, json={"amount": ["Too many digits."]})

    assert "Too many digits." in bot.error_text(response)


def test_error_text_when_the_api_is_down():
    assert bot.error_text(None) == bot.SERVICE_UNAVAILABLE


@pytest.fixture
def everyone_due(monkeypatch):
    monkeypatch.setattr(bot, "is_reminder_hour", lambda zone, now: True)


def ids_response(*telegram_ids):
    return httpx.Response(
        200,
        json=[
            {"telegram_id": tid, "notification_status": True, "timezone": "UTC"}
            for tid in telegram_ids
        ],
    )


def test_reminder_survives_an_api_error(api, everyone_due):
    api.handler = lambda request: httpx.Response(500)
    telegram = mock.AsyncMock()

    run(bot.send_daily_reminder(telegram))

    telegram.send_message.assert_not_called()


def test_reminder_survives_an_unreachable_api(api, everyone_due):
    api.handler = unreachable
    telegram = mock.AsyncMock()

    run(bot.send_daily_reminder(telegram))

    telegram.send_message.assert_not_called()


def test_blocked_user_does_not_stop_the_others(api, everyone_due):
    api.handler = lambda request: ids_response(1, 2, 3)
    telegram = mock.AsyncMock()
    telegram.send_message.side_effect = [None, Forbidden("blocked"), None]

    run(bot.send_daily_reminder(telegram))

    assert telegram.send_message.call_count == 3
    disabled = [r for r in api.calls if r.url.path == "/disable-notifications/"]
    assert [json.loads(r.content) for r in disabled] == [{"telegram_id": 2}]


def test_user_without_a_profile_is_skipped(api, everyone_due):
    api.handler = lambda request: httpx.Response(
        200,
        json=[{"telegram_id": 1, "notification_status": None, "timezone": None}],
    )
    telegram = mock.AsyncMock()

    run(bot.send_daily_reminder(telegram))

    telegram.send_message.assert_not_called()


def test_flood_limit_waits_and_retries_the_same_user(api, everyone_due, monkeypatch):
    api.handler = lambda request: ids_response(1)
    monkeypatch.setattr(bot.asyncio, "sleep", mock.AsyncMock())
    telegram = mock.AsyncMock()
    telegram.send_message.side_effect = [RetryAfter(3), None]

    run(bot.send_daily_reminder(telegram))

    assert telegram.send_message.call_count == 2
    assert bot.asyncio.sleep.await_args.args == (3,)


def test_token_is_restored_after_a_bot_restart(api):
    api.handler = lambda request: httpx.Response(200, json={"token": "fresh"})
    ctx = SimpleNamespace(user_data={})

    run(bot.ensure_registered(message_update("/stats"), ctx))

    assert ctx.user_data["token"] == "fresh"


def test_unreachable_api_tells_the_user_and_stops(api):
    api.handler = unreachable
    update = message_update("/stats")

    with pytest.raises(ApplicationHandlerStop):
        run(bot.ensure_registered(update, SimpleNamespace(user_data={})))

    update.message.reply_text.assert_awaited_once_with(bot.SERVICE_UNAVAILABLE)


def test_button_after_a_restart_is_answered_when_the_api_is_down(api):
    api.handler = unreachable
    update = button_update("settings_currency")

    with pytest.raises(ApplicationHandlerStop):
        run(bot.ensure_registered(update, SimpleNamespace(user_data={})))

    update.callback_query.answer.assert_awaited_once()


def test_start_is_left_to_its_own_handler(api):
    run(bot.ensure_registered(message_update("/start"), SimpleNamespace(user_data={})))

    assert api.calls == []


def test_edited_messages_are_dropped(api):
    update = SimpleNamespace(message=None, callback_query=None)

    with pytest.raises(ApplicationHandlerStop):
        run(bot.ensure_registered(update, context()))


def test_command_abandons_the_input_in_progress(api):
    ctx = context(state="adding_income")

    run(bot.ensure_registered(message_update("/stats"), ctx))

    assert ctx.user_data["state"] is None


def test_button_abandons_the_input_in_progress(api):
    ctx = context(state="adding_savings_goal")

    run(bot.handle_category(button_update("back_to_settings"), ctx))

    assert ctx.user_data["state"] is None


def test_savings_screen_still_waits_for_input(api):
    api.handler = lambda request: httpx.Response(
        200, json={"currency": "PLN", "savings_goal": None}
    )
    ctx = context()

    run(bot.handle_category(button_update("settings_savings"), ctx))

    assert ctx.user_data["state"] == "adding_savings_goal"


def category_request(name="Їжа" * 25):
    return httpx.Response(200, json=[{"id": 123456, "name": name, "user": 1}])


def test_long_cyrillic_category_fits_into_callback_data(api):
    api.handler = lambda request: category_request()
    update = message_update("100")

    run(bot.handle_message(update, context(currency="PLN")))

    markup = update.message.reply_text.await_args.kwargs["reply_markup"]
    data = markup.inline_keyboard[0][0].callback_data
    assert len(data.encode()) <= 64


def test_expense_is_saved_from_the_category_button(api):
    api.handler = lambda request: httpx.Response(
        201, json={"id": 9, "date": "2026-03-10"}
    )
    ctx = context(amount="12.50", category_names={5: "Food:out"}, currency="UAH")
    update = button_update("expcat_5")

    run(bot.handle_category(update, ctx))

    assert json.loads(api.calls[0].content) == {"amount": "12.50", "category": 5}
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "Food:out" in text and "UAH" in text


def test_second_tap_does_not_record_the_expense_twice(api):
    api.handler = lambda request: httpx.Response(
        201, json={"id": 9, "date": "2026-03-10"}
    )
    ctx = context(amount="10")

    run(bot.handle_category(button_update("expcat_5"), ctx))
    run(bot.handle_category(button_update("expcat_5"), ctx))

    assert len(api.calls) == 1


def test_outdated_button_format_does_not_crash(api):
    update = button_update("5:Food")

    run(bot.handle_category(update, context(amount="10")))

    assert api.calls == []
    update.callback_query.edit_message_text.assert_awaited_once()


def test_nan_never_reaches_the_api(api):
    update = message_update("nan")

    run(bot.handle_message(update, context(currency="PLN")))

    assert api.calls == []


def test_decimal_income_is_sent_as_a_string(api):
    api.handler = lambda request: httpx.Response(201, json={})

    run(
        bot.handle_message(
            message_update("49,99"), context(currency="PLN", state="adding_income")
        )
    )

    assert json.loads(api.calls[0].content) == {"amount": "49.99"}


def test_regular_payment_accepts_decimals(api):
    ctx = context(currency="PLN", state="adding_reg_amount")

    run(bot.handle_message(message_update("49.99"), ctx))

    assert ctx.user_data["reg_amount"] == "49.99"
    assert ctx.user_data["state"] == "adding_reg_day"


def test_shared_categories_are_not_offered_for_deletion(api):
    api.handler = lambda request: httpx.Response(
        200,
        json=[
            {"id": 1, "name": "Shared", "user": None},
            {"id": 2, "name": "Mine", "user": 7},
        ],
    )
    update = button_update("cat_delete")

    run(bot.handle_category(update, context()))

    markup = update.callback_query.edit_message_text.await_args.kwargs["reply_markup"]
    buttons = [row[0].callback_data for row in markup.inline_keyboard]
    assert buttons == ["delete_2", "settings_categories"]


def test_deleting_a_category_asks_first(api):
    api.handler = lambda request: httpx.Response(
        200, json={"name": "Food", "expense_count": 12, "payment_count": 1}
    )
    update = button_update("delete_5")

    run(bot.handle_category(update, context()))

    assert [request.method for request in api.calls] == ["GET"]
    text = update.callback_query.edit_message_text.await_args.args[0]
    assert "12 expense" in text and "1 regular payment" in text


def test_confirmation_deletes_the_category(api):
    api.handler = lambda request: httpx.Response(204)

    run(bot.handle_category(button_update("delcat_5"), context()))

    assert [(r.method, r.url.path) for r in api.calls] == [
        ("DELETE", "/categories/5/")
    ]


def test_long_history_is_sent_in_several_messages(api):
    expense = {
        "date": "2026-03-01",
        "category__name": "Food",
        "amount": "100.00",
        "currency": "PLN",
        "description": "x" * 50,
    }
    api.handler = lambda request: httpx.Response(200, json=[expense] * 200)
    update = message_update("/history")

    run(bot.history(update, context()))

    sent = update.message.reply_text.await_args_list
    assert len(sent) > 1
    assert all(len(call.args[0]) <= 4096 for call in sent)


def test_stats_warns_when_over_budget(api):
    api.handler = lambda request: httpx.Response(
        200,
        json={
            "month": "March 2026",
            "categories": [],
            "total": {},
            "income": {},
            "daily_limit": "-3.34",
            "currency": "PLN",
            "currency_mismatch": False,
        },
    )
    update = message_update("/stats")

    run(bot.stats(update, context()))

    assert "over budget" in update.message.reply_text.await_args.args[0]


def test_stats_answers_when_the_api_is_down(api):
    api.handler = unreachable
    update = message_update("/stats")

    run(bot.stats(update, context()))

    update.message.reply_text.assert_awaited_once_with(bot.SERVICE_UNAVAILABLE)


def test_error_handler_tells_the_user(api):
    update = message_update("100")
    update = mock.Mock(spec=bot.Update, effective_message=update.message)

    run(bot.on_error(update, SimpleNamespace(error=NetworkError("boom"))))

    update.effective_message.reply_text.assert_awaited_once_with(bot.SOMETHING_WRONG)


def test_error_handler_ignores_a_double_tap(api):
    update = message_update("100")
    update = mock.Mock(spec=bot.Update, effective_message=update.message)
    error = bot.BadRequest("Message is not modified")

    run(bot.on_error(update, SimpleNamespace(error=error)))

    update.effective_message.reply_text.assert_not_called()


def test_antiflood_lets_normal_use_through(api):
    ctx = context()

    for _ in range(bot.FLOOD_LIMIT):
        run(bot.antiflood(message_update("100"), ctx))


def test_antiflood_warns_once_and_stops_the_rest(api):
    ctx = context()
    for _ in range(bot.FLOOD_LIMIT):
        run(bot.antiflood(message_update("100"), ctx))

    first, second = message_update("100"), message_update("100")
    with pytest.raises(ApplicationHandlerStop):
        run(bot.antiflood(first, ctx))
    with pytest.raises(ApplicationHandlerStop):
        run(bot.antiflood(second, ctx))

    first.message.reply_text.assert_awaited_once()
    second.message.reply_text.assert_not_called()


def test_antiflood_forgets_old_messages(api, monkeypatch):
    ctx = context()
    for _ in range(bot.FLOOD_LIMIT):
        run(bot.antiflood(message_update("100"), ctx))

    later = bot.time.monotonic() + bot.FLOOD_WINDOW_SECONDS + 1
    monkeypatch.setattr(bot.time, "monotonic", lambda: later)

    run(bot.antiflood(message_update("100"), ctx))


def test_antiflood_counts_each_user_separately(api):
    busy = context()
    for _ in range(bot.FLOOD_LIMIT + 1):
        try:
            run(bot.antiflood(message_update("100"), busy))
        except ApplicationHandlerStop:
            pass

    run(bot.antiflood(message_update("100", user_id=2), context()))
