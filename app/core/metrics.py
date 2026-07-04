"""Bot-side Prometheus counters (Phase 14), served on their own port (9100).

Kept separate from Phase 10's Redis-backed ``stats:today:*`` counters —
those feed the bot's business-facing Statistika screen and the daily
``statistics`` table, while these feed Prometheus/Grafana for ops
monitoring. Both get incremented at the same call sites; they just serve
different audiences (an admin reading the bot panel vs. a dashboard/alert).
"""

from prometheus_client import Counter

bot_updates_total = Counter("bot_updates_total", "Total Telegram updates processed by the bot")
bot_movies_sent_total = Counter("bot_movies_sent_total", "Total movies delivered to users")
bot_errors_total = Counter("bot_errors_total", "Total unhandled errors in the bot")
