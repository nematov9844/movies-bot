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

Avtomatik: bot processi ichidagi scheduler (Phase 11) har kuni soat 03:00 da
to'liq DB backup oladi (`pg_dump -Fc` + gzip, `backups/db_YYYY-MM-DD.dump.gz`,
7 kundan eskisi avtomatik o'chiriladi) va har dushanba 04:00 da `settings`
jadvalini o'qilishi oson JSON faylga eksport qiladi
(`backups/settings_YYYY-MM-DD.json`) — bazaning to'liq nusxasidan tashqari,
faqat runtime sozlamalarni tezda ko'rish/solishtirish uchun.

Qo'lda ishga tushirish (host'dan, `.env` mavjud bo'lgan loyiha ildizidan):

```bash
./scripts/backup.sh                      # backups/db_YYYY-MM-DD.dump.gz yaratadi
./scripts/restore.sh backups/db_2026-01-01.dump.gz   # tasdiqlashni so'raydi
./scripts/restore.sh <fayl> -y                        # tasdiqlovsiz (skriptlar uchun)
```

Yoki konteyner ichidan:

```bash
docker compose exec bot bash scripts/backup.sh
docker compose exec bot bash scripts/restore.sh backups/db_2026-01-01.dump.gz -y
```

**Muhim:** `restore.sh` **halokatli** amal — `pg_restore --clean --if-exists`
tiklashdan oldin bazadagi barcha mavjud obyektlarni o'chiradi. `pg_dump`/
`pg_restore` klient versiyasi bazaning `postgres:16` versiyasidan **eski**
bo'lishi tavsiya etiladi (klient serverdan yangiroq bo'lsa, u tushunmaydigan
direktivalar chiqarishi mumkin) — Docker image ichida bu allaqachon to'g'ri
sozlangan, lekin hostdan qo'lda ishga tushirsangiz o'z `pg_dump`/`psql`
versiyangizni tekshiring (`pg_dump --version`).

## Deploy

Production uchun `docker-compose.prod.yml` va `nginx/nginx.conf` fayllariga qarang. Batafsil qo'llanma pastda (Deploy bo'limi to'liq to'ldiriladi — Phase 18).

## Arxitektura

```
Handler → Service → Repository → Database
```

Loyiha tuzilishi va modullar haqida to'liq ma'lumot uchun texnik topshiriqqa (TZ) qarang.
