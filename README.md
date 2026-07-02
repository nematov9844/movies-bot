# Movie Platform

Telegram orqali kino tarqatuvchi Media Platform: bot (Aiogram 3), REST API (FastAPI), Web Admin Panel (Next.js).

## Talablar

- Docker + Docker Compose
- (Lokal ishlab chiqish uchun) Python 3.12+, Node.js 20+

## O'rnatish

```bash
cp .env.example .env
# .env faylini to'ldiring: BOT_TOKEN, STORAGE_CHANNEL_ID, OWNER_ID, POSTGRES_PASSWORD, JWT_SECRET

docker compose up -d --build
```

`/health` endpoint tekshiruvi:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Botga `/start` yuboring — javob qaytishi kerak.

## Monitoring (ixtiyoriy)

```bash
docker compose --profile monitoring up -d
```

Grafana: http://localhost:3001 (admin / `.env` dagi `GRAFANA_ADMIN_PASSWORD`)
Prometheus: http://localhost:9090

## Testlar

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Backup / Restore

```bash
./scripts/backup.sh          # backups/db_YYYY-MM-DD.dump.gz yaratadi
./scripts/restore.sh <fayl>  # bazani tiklaydi
```

## Deploy

Production uchun `docker-compose.prod.yml` va `nginx/nginx.conf` fayllariga qarang. Batafsil qo'llanma pastda (Deploy bo'limi to'liq to'ldiriladi — Phase 18).

## Arxitektura

```
Handler → Service → Repository → Database
```

Loyiha tuzilishi va modullar haqida to'liq ma'lumot uchun texnik topshiriqqa (TZ) qarang.
