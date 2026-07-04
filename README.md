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

Testlar `docker compose`'dagi Postgres/Redis'ga, lekin ilovaning haqiqiy
bazasidan mutlaqo alohida `movie_platform_test` bazasiga ishlaydi — har bir
test o'z tranzaksiyasida ishlaydi va oxirida (test kodning o'zi
`session.commit()` chaqirgan bo'lsa ham) rollback qilinadi, shuning uchun
testlar hech qachon haqiqiy ma'lumotlarga ta'sir qilmaydi.

```bash
pip install -e ".[dev]"

# Bir martalik: test bazasini yaratish (jadvallarni conftest.py o'zi quradi)
PGPASSWORD=<parol> psql -h localhost -U movie -d postgres -c "CREATE DATABASE movie_platform_test;"

# docker-compose tashqarisidan (hostdan) ishga tushirish uchun POSTGRES_HOST/
# REDIS_HOST'ni localhost'ga almashtiring — .env dagi "postgres"/"redis"
# faqat compose tarmog'i ichida ishlaydi:
POSTGRES_HOST=localhost REDIS_HOST=localhost pytest

# Yoki konteyner ichidan (docker-compose'dagi nomlar to'g'ridan-to'g'ri ishlaydi):
docker compose exec api pytest

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

### Server talablari

- Minimal: 2 CPU, 4GB RAM, 40GB disk (SSD tavsiya etiladi)
- Ubuntu/Debian (yoki Docker qo'llab-quvvatlaydigan istalgan distro)
- Docker + Docker Compose plugin
- `api.domain.uz` va `panel.domain.uz` (yoki o'z domeningiz) — ikkalasi ham
  server IP'siga A-record bilan yo'naltirilgan bo'lishi kerak

### Birinchi marta o'rnatish

```bash
# 1. Repo va .env
git clone <repo-url> movie-platform && cd movie-platform
cp .env.example .env
# BOT_TOKEN, STORAGE_CHANNEL_ID, OWNER_ID, POSTGRES_PASSWORD, JWT_SECRET'ni
# to'ldiring; CORS_ORIGINS'ga https://panel.domain.uz'ni qo'shing.

# 2. Domenlarni nginx/nginx.conf'da almashtiring
sed -i 's/api\.domain\.uz/api.YOURDOMAIN.uz/g; s/panel\.domain\.uz/panel.YOURDOMAIN.uz/g' nginx/nginx.conf

# 3. Xavfsizlik devori — faqat 80/443 (va SSH) tashqariga ochiq
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 4. Ilovani (nginx'siz) birinchi bor ko'tarish — sertifikat olish uchun
#    port 80 kerak, lekin HTTPS konfiguratsiyasi hali sertifikatsiz ishga
#    tushmaydi, shuning uchun avval faqat kerakli servicelarni ko'taramiz:
docker compose up -d --build postgres redis migrations bot api admin-panel

# 5. nginx'ni sertifikatsiz, faqat HTTP (80) bilan vaqtincha ko'tarish...
#    ...yoki to'g'ridan-to'g'ri certbot'ning standalone rejimidan
#    foydalaning. Eng sodda yo'l — birinchi marta shu buyruq bilan
#    sertifikat oling (nginx hali ishlamayotgan bo'lsa ham port 80 bo'sh):
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -p 80:80 --entrypoint certbot certbot certonly --standalone \
  -d api.YOURDOMAIN.uz -d panel.YOURDOMAIN.uz \
  --email you@example.com --agree-tos --no-eff-email

# 6. Endi nginx'ni ham qo'shib, hammasini ko'taring
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 7. Tekshiruv
curl https://api.YOURDOMAIN.uz/health
```

### Keyingi deploylar

```bash
./scripts/deploy.sh   # git pull -> build -> migrate -> restart -> eski image'larni tozalash
```

### Sertifikatni yangilash

Let's Encrypt sertifikatlari 90 kunda tugaydi. Serverning o'zida (host
crontab) haftalik ishga tushiriladigan buyruq:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Monitoring va portlar

`docker-compose.prod.yml` postgres/redis/prometheus/grafana/bot's metrics
portini o'zgartirmaydi — ular allaqachon `127.0.0.1` bilan cheklangan (bot
`9100`-porti ham). `/metrics` esa nginx darajasida ham to'sib qo'yilgan
(`nginx/nginx.conf`dagi `location /metrics { deny all; }`). 3-bosqichdagi
`ufw` qoidalari bilan birgalikda bu portlarning hech biri internetdan
to'g'ridan-to'g'ri ko'rinmaydi — faqat 80/443 (nginx) va 22 (SSH) ochiq.

## Arxitektura

```
Handler → Service → Repository → Database
```

Loyiha tuzilishi va modullar haqida to'liq ma'lumot uchun texnik topshiriqqa (TZ) qarang.
