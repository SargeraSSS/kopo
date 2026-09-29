import os
from functools import partial

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
API_URL = os.getenv("API_URL")


start_message = """
Welcome to Kopo Bot!
I help you track your daily expenses easily right here in Telegram.
Here's what I can do:
💸 Record your expenses by simply sending a number
📊 Show your monthly spending stats
📋 Keep your expense history
🔄 Manage regular monthly payments
💰 Set a daily spending limit

For more info just type /help
"""


def get_settings_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("💱 Currency", callback_data="settings_currency"),
            InlineKeyboardButton("🎯 Savings goal", callback_data="settings_savings"),
        ],
        [
            InlineKeyboardButton("📂 Categories", callback_data="settings_categories"),
            InlineKeyboardButton(
                "🔄 Regular payments", callback_data="settings_regular"
            ),
        ],
        [InlineKeyboardButton("🔔 Notifications", callback_data="toggle_notification")],
        [InlineKeyboardButton("❌ Close", callback_data="settings_close")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    status = await register_user(telegram_id, context)
    if status == 201:
        await update.message.reply_text(f"{start_message}")
    elif status == 200:
        await update.message.reply_text("👋 Welcome back!")
    else:
        await update.message.reply_text(
            "⚠️ Service is unavailable. Please try again later."
        )


async def on_startup(app):
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Register and get started"),
            BotCommand("stats", "View this month's statistics"),
            BotCommand("history", "View this month's expense history"),
            BotCommand("settings", "Manage currency, categories, limits"),
            BotCommand("income", "Add income"),
            BotCommand("help", "How to use this bot"),
        ]
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(partial(send_daily_reminder, app.bot), "cron", hour=19, minute=0)
    scheduler.add_job(process_monthly_payments, "cron", day=1, hour=0, minute=0)
    scheduler.start()


async def register_user(telegram_id: int, context):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/register-telegram/",
                json={"telegram_id": telegram_id},
                headers={"Authorization": f"Token {ADMIN_TOKEN}"},
            )
    except httpx.HTTPError:
        # API unreachable - the caller shows the "try again later" branch
        return None
    if response.status_code in (200, 201):
        context.user_data["token"] = response.json()["token"]
    return response.status_code


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not context.user_data.get("token"):
        telegram_id = update.effective_user.id
        await register_user(telegram_id, context)

    if not context.user_data.get("currency"):
        profile = await get_user_profile(context.user_data.get("token"))
        context.user_data["currency"] = profile["currency"]

    if context.user_data.get("state") == "adding_category":
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/categories/",
                json={"name": text},
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        context.user_data["state"] = None
        if response.status_code == 201:
            await update.message.reply_text(f"✅ Category '{text}' added!")
        else:
            await update.message.reply_text("❌ Something went wrong")
        return
    elif context.user_data.get("state") == "adding_savings_goal":
        try:
            amount = int(text)
        except ValueError:
            await update.message.reply_text("Please send a number 💸. Try again")
            return
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/set-savings-goal/",
                json={"savings_goal": amount},
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        context.user_data["state"] = None
        if response.status_code == 200:
            await update.message.reply_text("Saving goal added!")
        else:
            await update.message.reply_text("❌ Something went wrong")
        return
    elif context.user_data.get("state") == "adding_income":
        try:
            amount = float(text)
        except ValueError:
            context.user_data["state"] = None
            await update.message.reply_text(
                "Please send a number 💸. Try again /income"
            )
            return
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/income/",
                json={"amount": amount},
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        context.user_data["state"] = None
        if response.status_code == 201:
            await update.message.reply_text("💸Income added!")
        else:
            await update.message.reply_text("❌ Something went wrong")
        return
    elif context.user_data.get("state") == "adding_reg_name":
        context.user_data["reg_name"] = text
        context.user_data["state"] = "adding_reg_amount"
        await update.message.reply_text("💰 Enter payment amount:")
        return
    elif context.user_data.get("state") == "adding_reg_amount":
        try:
            amount = int(text)
        except ValueError:
            context.user_data["state"] = None
            await update.message.reply_text(
                "Please send a number 💸. Try again /settings"
            )
            return
        context.user_data["reg_amount"] = amount
        context.user_data["state"] = "adding_reg_day"
        await update.message.reply_text("📅 Enter day of a mounth (1 - 31)")
        return

    elif context.user_data.get("state") == "adding_reg_day":
        try:
            day = int(text)
        except ValueError:
            context.user_data["state"] = None
            await update.message.reply_text("Please enter a number between 1 and 31")
            return

        if 1 <= day <= 31:
            context.user_data["reg_day"] = day
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_URL}/regular-payments/",
                    json={
                        "payment_day": context.user_data["reg_day"],
                        "amount": context.user_data["reg_amount"],
                        "name": context.user_data["reg_name"],
                        "category": context.user_data["reg_category_id"],
                    },
                    headers={"Authorization": f"Token {context.user_data['token']}"},
                )
            context.user_data["state"] = None
            if response.status_code == 201:
                await update.message.reply_text("✅ Regular payment added!")
            else:
                await update.message.reply_text("❌ Something went wrong")
        else:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Please enter a number between 1 and 31")
        return
    try:
        amount = float(text)
        context.user_data["amount"] = amount
        categories = await get_categories(context.user_data["token"])
        keyboard = [
            [
                InlineKeyboardButton(
                    cat["name"], callback_data=f"{cat['id']}:{cat['name']}"
                )
            ]
            for cat in categories
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select category:", reply_markup=reply_markup)
    except ValueError:
        await update.message.reply_text("Please send a number 💸")


async def process_monthly_payments():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/process-regular-payments/",
            headers={"Authorization": f"Token {ADMIN_TOKEN}"},
        )


async def send_daily_reminder(bot):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/all-telegram-ids/",
            headers={"Authorization": f"Token {ADMIN_TOKEN}"},
        )
        ids = response.json()

    for item in ids:
        telegram_id = item["telegram_id"]
        status = item["notification_status"]
        if not status:
            continue
        else:
            await bot.send_message(
                chat_id=telegram_id,
                text="""
        🕗 The day is coming to an end, time to track your day's expenses!
        Disable reminder or set time zone in 
        /settings""",
            )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Kopo Bot — Guide*\n\n"
        "💸 *Adding an expense*\n"
        "Just send a number (e.g. `100`) and pick a category.\n\n"
        "💰 *Adding income*\n"
        "/income — then send the amount.\n\n"
        "📊 *Statistics*\n"
        "/stats — this month's expenses by category, totals, income, and today's spending limit.\n\n"
        "📋 *History*\n"
        "/history — all expenses recorded this month.\n\n"
        "⚙️ *Settings*\n"
        "/settings — change currency, set a savings goal, manage categories, "
        "regular payments, and notifications.\n\n"
        "🔄 *Regular payments*\n"
        "Set up recurring expenses (like rent or internet) in Settings — "
        "they'll be added automatically each month.\n\n"
        "🔔 *Notifications*\n"
        "Get a daily reminder at 19:00 to log your expenses (toggle in Settings)."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_settings_keyboard()
    await update.message.reply_text("⚙️ Settings", reply_markup=reply_markup)


async def get_user_profile(token):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/get-profile/", headers={"Authorization": f"Token {token}"}
        )
        if response.status_code == 200:
            return response.json()
    return {"currency": "PLN", "savings_goal": None}


# CURRENCY_CHOICES = [
#     ("PLN", "PLN zł"),
#     ("UAH", "UAH ₴"),
#     ("EUR", "EUR €"),
#     ("USD", "USD $"),
# ]


async def handle_settings_callback(query, context):
    if query.data == "settings_currency":
        keyboard = [
            [
                InlineKeyboardButton("PLN zł", callback_data="currency_PLN"),
                InlineKeyboardButton("UAH ₴", callback_data="currency_UAH"),
            ],
            [
                InlineKeyboardButton("EUR €", callback_data="currency_EUR"),
                InlineKeyboardButton("USD $", callback_data="currency_USD"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("💱 Choose currency:", reply_markup=reply_markup)
    elif query.data.startswith("currency_"):
        currency = query.data.split("_")[1]
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/set-currency/",
                json={"currency": currency},
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        if response.status_code == 200:
            context.user_data["currency"] = currency
            await query.edit_message_text(f"✅ Currency set to {currency}!")
        else:
            await query.edit_message_text("❌ Something went wrong")
    elif query.data == "settings_savings":
        profile = await get_user_profile(context.user_data["token"])
        current = profile.get("savings_goal")
        keyboard = []
        if current is not None:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "🗑 Remove goal", callback_data="settings_savings_clear"
                    )
                ]
            )
        keyboard.append(
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings")]
        )
        if current is None:
            text = "🎯 No savings goal set.\nEnter your savings goal for this month:"
        else:
            text = (
                f"🎯 Current goal: {float(current):.2f} "
                f"{profile.get('currency', 'PLN')}\n"
                "Enter a new savings goal for this month:"
            )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data["state"] = "adding_savings_goal"
    elif query.data == "settings_savings_clear":
        context.user_data["state"] = None
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/set-savings-goal/",
                json={"savings_goal": None},
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        if response.status_code == 200:
            await query.edit_message_text("🗑 Savings goal removed!")
        else:
            await query.edit_message_text("❌ Something went wrong")
    elif query.data == "settings_categories":
        keyboard = [
            [
                InlineKeyboardButton("➕ Add category", callback_data="cat_add"),
                InlineKeyboardButton("🗑 Delete category", callback_data="cat_delete"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📂 Categories:", reply_markup=reply_markup)
    elif query.data == "cat_add":
        context.user_data["state"] = "adding_category"
        await query.edit_message_text("✏️ Enter category name:")
    elif query.data == "cat_delete":
        categories = await get_categories(context.user_data["token"])
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🗑 {cat['name']}", callback_data=f"delete_{cat['id']}"
                )
            ]
            for cat in categories
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Select category to delete:", reply_markup=reply_markup
        )
    elif query.data.startswith("delete_"):
        category_id = query.data.split("_")[1]
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{API_URL}/categories/{category_id}/",
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        if response.status_code == 204:
            await query.edit_message_text("✅ Category deleted!")
        else:
            await query.edit_message_text("❌ Something went wrong")
    elif query.data == "settings_close":
        await query.message.delete()
    elif query.data == "settings_regular":
        keyboard = [
            [
                InlineKeyboardButton("➕ Add payment", callback_data="reg_add"),
                InlineKeyboardButton("📋 View payments", callback_data="reg_view"),
            ],
            [InlineKeyboardButton("🗑 Delete payment", callback_data="reg_delete")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🔄 Regular payments:", reply_markup=reply_markup)
    elif query.data == "reg_add":
        categories = await get_categories(context.user_data["token"])
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{cat['name']}", callback_data=f"regcat_{cat['id']}"
                )
            ]
            for cat in categories
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Select category for regular payment:", reply_markup=reply_markup
        )
    elif query.data.startswith("regcat_"):
        context.user_data["reg_category_id"] = query.data.split("_")[1]
        context.user_data["state"] = "adding_reg_name"
        await query.edit_message_text("✏️ Enter payment name (e.g. Internet):")
    elif query.data == "back_to_settings":
        reply_markup = get_settings_keyboard()
        await query.edit_message_text("⚙️ Settings", reply_markup=reply_markup)
    elif query.data == "reg_view":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/regular-payments/",
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
            payments = response.json()
            currency = context.user_data.get("currency", "PLN")
            text = "📋 Your's regular expenses\n\n"
            for expense in payments:
                text += f"{expense['name']} — {expense['amount']} {currency} — day {expense['payment_day']} — {expense['category_name']}\n"
            await query.edit_message_text(text)
    elif query.data.startswith("delreg_"):
        payment_id = query.data.split("_")[1]
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{API_URL}/regular-payments/{payment_id}/",
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        if response.status_code == 204:
            await query.edit_message_text("✅ Regular payment deleted!")
        else:
            await query.edit_message_text("❌ Something went wrong")
    elif query.data == "reg_delete":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/regular-payments/",
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
            reg_payments = response.json()

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"🗑 {payment['name']}", callback_data=f"delreg_{payment['id']}"
                    )
                ]
                for payment in reg_payments
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Select regular payment to delete:", reply_markup=reply_markup
            )
    elif query.data == "toggle_notification":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/get-profile/",
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
            status = response.json()["notification_status"]
            status = not status
            response = await client.post(
                f"{API_URL}/notification-status/",
                json={"notification_status": status},
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
            if response.status_code == 200:
                if status == False:
                    await query.edit_message_text("🔕 Notifications turned off!")
                elif status == True:
                    await query.edit_message_text("🔔 Notifications turned on!")
            else:
                await query.edit_message_text("❌ Something went wrong, try again")
    elif query.data.startswith("delexp_"):
        expense_id = query.data.split("_")[1]
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{API_URL}/expenses/{expense_id}/",
                headers={"Authorization": f"Token {context.user_data['token']}"},
            )
        if response.status_code == 204:
            await query.edit_message_text("🗑 Expense cancelled!")
        else:
            await query.edit_message_text("❌ Something went wrong")


async def get_categories(token):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/categories/", headers={"Authorization": f"Token {token}"}
        )
        return response.json()


async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "adding_income"
    await update.message.reply_text("💰 Enter income amount:")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/stats/",
            headers={"Authorization": f"Token {context.user_data['token']}"},
        )
        data = response.json()
        if response.status_code == 200:
            text = f"📊 {data['month']}\n\n"
            for cat in data["categories"]:
                text += f"{cat['category__name']} — {cat['total']} {cat['currency']}\n"
            text += "\n💰 Totals:\n"
            for currency, amount in data["total"].items():
                text += f"{currency}: {amount}\n"
            text += "\n💸 Income:\n"
            for currency, amount in data["income"].items():
                text += f"{currency}: {amount}\n"
            text += f"\n💰 Daily limit: {data['daily_limit']} {data['currency']}\n"
            if data.get("currency_mismatch"):
                text += "⚠️ Some income/expenses are in a different currency — daily limit may be inaccurate.\n"
            await update.message.reply_text(text)


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/history/",
            headers={"Authorization": f"Token {context.user_data['token']}"},
        )
        data = response.json()
        text = "📋 History\n\n"
        for expense in data:
            desc = f" — {expense['description']}" if expense["description"] else ""
            text += f"{expense['date']} — {expense['category__name']} — {expense['amount']} {expense['currency']} {desc}\n"
        await update.message.reply_text(text)


async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if (
        query.data.startswith("settings_")
        or query.data.startswith("toggle_notification")
        or query.data.startswith("cat_")
        or query.data.startswith("delete_")
        or query.data.startswith("currency_")
        or query.data.startswith("reg_")
        or query.data.startswith("regcat_")
        or query.data.startswith("back_to_settings")
        or query.data.startswith("delreg_")
        or query.data.startswith("delexp_")
    ):
        await handle_settings_callback(query, context)
        return
    amount = context.user_data.get("amount")
    token = context.user_data.get("token")
    data = query.data.split(":")
    category_id = int(data[0])
    category_name = data[1]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/expenses/",
            json={"amount": amount, "category": category_id},
            headers={"Authorization": f"Token {token}"},
        )
    currency = context.user_data.get("currency", "PLN")
    if response.status_code == 201:
        expense_id = response.json()["id"]
        keyboard = [
            [InlineKeyboardButton("🗑 Cancel", callback_data=f"delexp_{expense_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"✅ Expense saved!\n"
            f"💰 Amount: {amount} {currency} \n"
            f"📂 Category: {category_name}\n"
            f"📅 Date: {response.json()['date']}",
            reply_markup=reply_markup,
        )
    else:
        await query.edit_message_text(
            "💡 To record an expense, just send a number. Example: 100"
        )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_category))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("income", income))
    app.add_handler(CommandHandler("help", help_command))
    app.run_polling()


if __name__ == "__main__":
    main()
