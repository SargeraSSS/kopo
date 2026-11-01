from rest_framework.throttling import SimpleRateThrottle


class TelegramIdThrottle(SimpleRateThrottle):
    """Limit /register-telegram/ per Telegram user.

    Every request comes from the bot under one admin token, so the usual keys
    (IP, user) would put all people into one bucket.
    """

    scope = "registration"

    def get_cache_key(self, request, view):
        try:
            ident = int(request.data.get("telegram_id"))
        except (TypeError, ValueError):
            # None would mean "no limit": bad ids share one bucket instead
            ident = "invalid"
        return self.cache_format % {"scope": self.scope, "ident": ident}
