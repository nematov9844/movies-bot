# Movie Platform

Telegram orqali kino/anime/serial tarqatuvchi Media Platform: bot (Aiogram 3),
REST API (FastAPI) va Web Admin Panel (Next.js). Videolar serverda emas,
Telegram'ning yopiq (private) kanalida saqlanadi — bazada faqat kod va
Telegram `file_id` turadi.

## Funksionallik

### Foydalanuvchi uchun (bot)

- **Kino kodi orqali olish** — kodni yozish bilanoq video keladi.
- **Qidirish** — nom yoki kod bo'yicha (kino ham, serial ham chiqadi).
- **Top / Yangi / Mashhur** ro'yxatlari, kategoriyalar bo'yicha ko'rish.
- **Poster kartochka** — kino yoki serialni bosganda poster + nom + tavsif
  chiqadi, keyin "🎬 Kinoni olish" tugmasi bosilganda video yuboriladi
  (poster qo'yilmagan bo'lsa oddiy matn ko'rinishida).
- **Seriallar/fasllar/qismlar** — "Naruto" kabi ko'p qismli anime/seriallar
  alohida 200+ ta natija sifatida emas, bitta serial sifatida chiqadi;
  serialni bossa — fasllar (raqamli grid, 15 tadan sahifalab), faslni
  bossa — qismlar ro'yxati (xuddi shunday grid+pagination) chiqadi.
- **Premium** — premium reja sotib olish/ega bo'lish, premium kinolarga
  kirish huquqi, majburiy obunadan ozod bo'lish.
- **Majburiy obuna (force-subscribe)** — botdan foydalanish uchun
  belgilangan kanal(lar)ga obuna bo'lish talab qilinishi mumkin; obuna
  bo'lmasdan "✅ Tekshirish" bossa, aniq (o'zbek + rus tilida) ogohlantirish
  chiqadi. Vaqt oralig'i, boshlanish/tugash sanasi, join-limit kabi
  cheklovlar bilan sozlanadi.
- **Referral (taklif)** — do'stni taklif qilish havolasi, referal soni.
- **Profil** — ism, premium holati, ko'rilgan kinolar, takliflar soni.

### Admin uchun (bot, `/panel`)

- **Kino qo'shish/tahrirlash/o'chirish** (kategoriya, premium belgisi bilan,
  poster — botga rasm yuborish bilan, `file_id` qo'lda kiritish shart emas).
- **Seriallar** — yangi serial va fasl yaratish, so'ng videolarni birma-bir
  forward qilib qismlarni ommaviy qo'shish (kod/nom avtomatik generatsiya
  qilinadi, admin hech narsa yozmaydi); fasl/serial nomini, poster
  rasmini tahrirlash, o'chirish; qismlari to'liq bo'lmagan fasllar uchun
  "yetishmayotgan qismni to'ldirish" (aniq qism raqami so'raladi).
- **Kanaldan avtomatik qo'shish** (`SOURCE_CHANNELS`) — bot admin bo'lgan
  kanal(lar)ga yangi video tushishi bilanoq caption'dan nom/fasl/qism
  avtomatik o'qib, bazaga qo'shadi (regex + ixtiyoriy AI-fallback — Ollama
  yoki Anthropic). Caption'dan hech narsa aniq o'qilmasa (nom yo'q, qism
  raqami noaniq), hech narsani "taxmin qilib" saqlamaydi — video bilan
  birga owner'ga DM yuborib, bitta tugma bosish bilan qo'lda hal qilish
  imkonini beradi.
- **Kanallar (force-subscribe)** — kanal qo'shish/tahrirlash/o'chirish,
  yoqish-o'chirish, muddat/vaqt oynasi/join-limit sozlash.
- **Premium berish** — foydalanuvchiga qo'lda premium reja berish.
- **Broadcast** — barcha yoki filtrlangan foydalanuvchilarga xabar
  yuborish (rate-limited, natija hisobot bilan).
- **Statistika** — kunlik/umumiy foydalanuvchi, kino, premium ko'rsatkichlari.
- **Sozlamalar** — `majburiy obuna`, `premium`, `maintenance mode`
  yoqish/o'chirish, xush kelibsiz matni, support username'ni bot orqali
  o'zgartirish.
- **`/setpassword`** — web admin panelga kirish uchun parol o'rnatish
  (har bir admin/owner o'ziniki uchun).

### Web Admin Panel (Next.js, `admin-panel/`)

- **Dashboard** — umumiy statistika va kunlik grafik.
- **Kinolar** — to'liq CRUD, nom/kod bo'yicha qidirish, poster (`file_id`)
  qo'yish, premium/faollik belgilash.
- **Seriallar** — serial/fasl CRUD (nom, tavsif, poster), fasl raqamini
  tahrirlash, har bir faslning qismlar ro'yxatini ko'rish (qismlar
  qo'shish botdan forward qilish orqali — video yuklash panelda yo'q).
- **Foydalanuvchilar** — ro'yxat, qidirish, bloklash.
- **Premium** — rejalar va faol premium foydalanuvchilar ro'yxati.
- **Kanallar** — force-subscribe kanallarini to'liq boshqarish.
- **Broadcast** — xabar yuborish tarixi va holati.
- **Sozlamalar** — `settings` jadvalidagi barcha qatorlarni ko'rish/tahrirlash.
- **Adminlar** (faqat owner) — admin qo'shish/o'chirish, rol va parol
  belgilash.
- **Loglar** — audit log (kim, qachon, nima qildi).
- **Dark mode** — yorug'/qorong'i rejim almashtirgichi (standart: qorong'i).

### Backend / infratuzilma

- **REST API** (FastAPI) — JWT autentifikatsiya (access+refresh), rol
  asosidagi ruxsatlar (owner/admin/moderator), rate limiting (slowapi),
  IP whitelist (ixtiyoriy), audit log, Prometheus metrikalar (`/metrics`).
- **Monitoring** — Prometheus + Grafana (ixtiyoriy profil).
- **Xavfsizlik** — HTML-escaping (foydalanuvchi kiritgan matn xavfsiz
  chiqadi), parol hash (bcrypt), rate limiting, CORS sozlamalari.
- **Avtomatik backup** — bot ichidagi scheduler har kuni to'liq DB backup
  oladi (7 kunlik rotatsiya) va har hafta sozlamalarni JSON'ga eksport
  qiladi.
- **Testlar** — 90+ avtomatik test (pytest), CI uchun tayyor.

## Arxitektura

```
Handler → Service → Repository → Database
```

Uch asosiy komponent bitta Postgres/Redis'ni baham ko'radi:

- **bot** — Aiogram 3, foydalanuvchi va admin bilan Telegram orqali muloqot.
- **api** — FastAPI, web admin panel uchun REST API.
- **admin-panel** — Next.js 14, brauzerda ishlaydigan boshqaruv paneli.

Loyiha tuzilishi va modullar haqida to'liq ma'lumot uchun texnik
topshiriqqa (`docs/TZ.md`) qarang.

## Lokal ishga tushirish

### Talablar

- Docker + Docker Compose
- (Lokal ishlab chiqish uchun, konteynersiz) Python 3.12+, Node.js 20+

### O'rnatish

```bash
cp .env.example .env
# .env faylini to'ldiring: BOT_TOKEN, STORAGE_CHANNEL_ID, OWNER_ID,
# POSTGRES_PASSWORD, JWT_SECRET

docker compose up -d --build
```

`/health` endpoint tekshiruvi:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Botga `/start` yuboring — javob qaytishi kerak. Admin panelga kirish uchun
avval botga `/setpassword <parol>` yuboring (kamida 8 belgi), so'ng
http://localhost:3000/login sahifasida Telegram ID + shu parol bilan
kiring. Lokalda panelni sinash uchun `.env`ga qo'shing:

```
CORS_ORIGINS=http://localhost:3000
```

## Serverga tezkor joylashtirish (faqat bot)

Web admin panel/API/nginx/SSL kerak bo'lmagan, **faqat Telegram bot**ni
ishga tushirish uchun eng qisqa yo'l — domen, sertifikat, ochiq port kerak
emas (bot Telegram API'ga o'zi tashqariga ulanadi, hech narsa "kirish"ni
kutmaydi).

```bash
# 1) Serverga Docker o'rnatish (bo'sh server bo'lsa)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

# 2) Kodni olib kelish
git clone https://github.com/<username>/movie-platform.git
cd movie-platform

# 3) .env sozlash — kamida BOT_TOKEN, STORAGE_CHANNEL_ID, OWNER_ID,
#    POSTGRES_PASSWORD, JWT_SECRET to'ldirilishi shart (JWT_SECRET API
#    ishlamasa ham Settings modeli talab qiladi — bo'sh qoldirmang)
cp .env.example .env
nano .env

# 4) Faqat kerakli servicelarni ko'tarish (api/admin-panel/nginx'siz)
docker compose up -d --build postgres redis migrations bot
```

Mavjud ma'lumotlar bilan ishga tushirish uchun (eski serverdan/lokaldan
"huddi shu data" ko'chirilyapti bo'lsa), yuqoridagi 4-qadamdan **oldin**:

```bash
# Eski joydan (lokal/eski server, .env shu yerda ham to'ldirilgan bo'lishi
# kerak) — POSTGRES_HOST=localhost kerak, chunki bu hostning o'zidan
# ishga tushyapti, .env dagi "postgres" esa faqat compose tarmog'i ichida
# ishlaydi:
POSTGRES_HOST=localhost ./scripts/backup.sh   # backups/db_YYYY-MM-DD.dump.gz yaratadi

# Faylni yangi serverga ko'chiring (masalan scp bilan), so'ng u yerda:
docker compose up -d postgres redis   # avval faqat bazani ko'tarish
docker compose exec -T postgres pg_isready -U movie   # tayyor bo'lguncha kutish
POSTGRES_HOST=localhost ./scripts/restore.sh backups/db_2026-01-01.dump.gz -y
docker compose up -d --build migrations bot   # keyin qolganini ko'tarish
```

Tekshirish: Telegram'da botga `/start` yuboring — javob qaytishi kerak.

**Ollama (ixtiyoriy, AI-yordamchi caption-parser uchun, faqat lokal
ishlab chiqish uchun):** standart holatda `bot` servisi oddiy (bridge)
tarmoqda ishlaydi va Ollama sozlanmagan bo'lsa hech narsa buzilmaydi —
faqat AI-fallback bosqichi ishlamaydi (regex asosidagi parser barcha
holatda ishlayveradi). Agar shu mashinada Ollama ham ishlab tursa
(`ollama serve`, `127.0.0.1:11434`) va bot unga ulanishini xohlasangiz,
`docker-compose.yml`da `bot` servisiga qo'lda qo'shing:
```yaml
    network_mode: host
    environment:
      POSTGRES_HOST: localhost
      REDIS_HOST: localhost
      OLLAMA_BASE_URL: http://127.0.0.1:11434
```
**Diqqat:** bu holatda `POSTGRES_HOST`/`REDIS_HOST` endi compose tarmog'i
o'rniga host portlariga ishora qiladi — agar Postgres/Redis host-porti
standart (5432/6379)dan boshqacha bo'lsa (masalan port to'qnashuvi
tufayli o'zgartirilgan bo'lsa), yuqoridagi `environment:` blokiga
`POSTGRES_PORT`/`REDIS_PORT`ni ham to'g'ri qiymat bilan qo'shing — aks
holda bot bazaga ulana olmay qoladi. Bir nechta boshqa loyiha ishlab
turgan (umumiy) serverda buni yoqishdan oldin shuni hisobga oling.

Keyinchalik web panel/API kerak bo'lsa, pastdagi "Serverga to'liq
joylashtirish" bo'limiga o'ting — u yerdagi qadamlar shu bazani (allaqachon
ishga tushirilgan `postgres`ni) qayta ishlatadi, hech narsani qayta
boshlash shart emas.

## Serverga to'liq joylashtirish (GitHub orqali)

Bu bo'lim noldan (bo'sh server) boshlab ilovani ishga tushirishgacha
bo'lgan barcha qadamlarni o'z ichiga oladi.

### Server talablari

Videolar serverda emas, Telegram kanalida saqlanadi — shuning uchun disk
talabi kutilganidan kichik (asosan Postgres ma'lumotlari, loglar, backuplar).

| | Minimal | Tavsiya etiladi |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 40 GB SSD | 60-80 GB SSD |
| OS | Ubuntu 22.04/24.04 (yoki Docker qo'llab-quvvatlaydigan istalgan distro) | |

- **RAM:** Postgres+Redis ~1GB, bot+API (Python) ~300-500MB, admin panel
  (Next.js) ~200-300MB — bularning hammasi 4GB'ga sig'adi. Monitoring
  (Prometheus+Grafana) ham yoqilsa, qo'shimcha ~500MB-1GB kerak bo'ladi —
  shu holda 8GB qulayroq.
- **CPU:** Bot asosan Telegram API/DB so'rovlariga bog'liq (I/O-bound), 2
  vCPU kichik/o'rta traffik uchun yetarli; broadcast yuborish yoki bir
  nechta admin bir vaqtda ishlashi uchun 4 vCPU zaxira beradi.
- **Disk:** Postgres ma'lumotlari, Docker image'lar (~5-10GB), kunlik
  backup (7 kunlik rotatsiya), loglar (avtomatik rotatsiya qilinadi).
- Kerakli portlar tashqariga: faqat **80** va **443** (nginx) hamda **22**
  (SSH). Boshqa hamma narsa (Postgres, Redis, API, bot metrikalari) faqat
  `127.0.0.1`ga bog'langan yoki firewall bilan yopiladi (pastga qarang).
- Ikkita domen (yoki subdomen) kerak, masalan `api.domeningiz.uz` va
  `panel.domeningiz.uz` — ikkalasi ham server IP'siga A-record bilan
  yo'naltirilgan bo'lishi kerak.

### 0-qadam — Kodni GitHub'ga joylash

Agar loyiha hali GitHub'da bo'lmasa (mahalliy kompyuteringizda/shu yerda):

```bash
# GitHub'da bo'sh repo yarating (masalan "movie-platform"), so'ng:
git remote add origin https://github.com/<username>/movie-platform.git
git branch -M main
git push -u origin main
```

**Muhim:** `.env` fayli `.gitignore`da bo'lishi shart — u maxfiy
ma'lumotlarni (bot token, parollar) o'z ichiga oladi va hech qachon
repo'ga qo'shilmasligi kerak. Faqat `.env.example` (bo'sh qiymatlar bilan)
repo'da bo'ladi.

### 1-qadam — Serverni tayyorlash (Docker o'rnatish)

Bo'sh Ubuntu serverga SSH orqali kiring, so'ng:

```bash
sudo apt update && sudo apt upgrade -y

# Docker'ning rasmiy o'rnatish skripti
curl -fsSL https://get.docker.com | sudo sh

# Joriy foydalanuvchini docker guruhiga qo'shish (sudo'siz ishlatish uchun)
sudo usermod -aG docker $USER
newgrp docker

# Tekshiruv
docker --version
docker compose version
```

### 2-qadam — Kodni serverga olib kelish

```bash
git clone https://github.com/<username>/movie-platform.git
cd movie-platform
```

### 3-qadam — `.env` sozlash

```bash
cp .env.example .env
nano .env
```

To'ldirilishi shart bo'lgan qiymatlar:

- `BOT_TOKEN` — @BotFather'dan olingan token.
- `STORAGE_CHANNEL_ID` — videolar saqlanadigan **yopiq** Telegram kanal
  ID'si (bot shu kanalda admin bo'lishi shart); odatda `-100` bilan
  boshlanadi.
- `OWNER_ID` — sizning Telegram foydalanuvchi ID'ingiz (masalan
  @userinfobot orqali bilib olinadi) — bot ishga tushganda shu ID
  avtomatik "owner" admin sifatida ro'yxatdan o'tadi.
- `POSTGRES_PASSWORD` — kuchli, tasodifiy parol (`openssl rand -hex 24`).
- `JWT_SECRET` — kuchli, tasodifiy qator (`openssl rand -hex 32`).
- `CORS_ORIGINS` — `https://panel.domeningiz.uz` (web panelning ochiq
  manzili).
- `DEBUG=false`, `ENVIRONMENT=production` — productionda shunday qolishi kerak.
- `SENTRY_DSN` — ixtiyoriy, xatoliklarni kuzatish uchun (Sentry.io'dan).
- `GRAFANA_ADMIN_PASSWORD` — monitoring yoqadigan bo'lsangiz, standart
  `admin` parolni albatta almashtiring.

### 4-qadam — Domenlarni nginx konfiguratsiyasida almashtirish

```bash
sed -i 's/api\.domain\.uz/api.DOMENINGIZ.uz/g; s/panel\.domain\.uz/panel.DOMENINGIZ.uz/g' nginx/nginx.conf
```

### 5-qadam — Xavfsizlik devori (faqat 80/443/SSH ochiq)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 6-qadam — Birinchi marta ishga tushirish + SSL sertifikat

```bash
# 6.1: Asosiy servicelarni (nginx'siz) ko'tarish
docker compose up -d --build postgres redis migrations bot api admin-panel

# 6.2: Let's Encrypt sertifikatini olish (port 80 hali bo'sh bo'lishi kerak)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -p 80:80 --entrypoint certbot certbot certonly --standalone \
  -d api.DOMENINGIZ.uz -d panel.DOMENINGIZ.uz \
  --email siz@example.com --agree-tos --no-eff-email

# 6.3: Endi nginx bilan birga hammasini to'liq ko'tarish
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 7-qadam — Tekshiruv

```bash
curl https://api.DOMENINGIZ.uz/health
# {"status":"ok"}
```

- Botga Telegram'da `/start` yuboring.
- Botga `/setpassword <parolingiz>` yuboring (kamida 8 belgi).
- `https://panel.DOMENINGIZ.uz/login` sahifasida Telegram ID + shu parol
  bilan kiring.
- Botda `/panel` → "📢 Kanallar" orqali kamida bitta majburiy obuna kanali
  qo'shing (yoki `/panel` → "⚙️ Sozlamalar"dan "Majburiy obuna"ni vaqtincha
  o'chirib qo'ying).

### 8-qadam — Keyingi yangilanishlar

Kodga o'zgartirish kiritilgach (GitHub'ga push qilingandan keyin), serverda:

```bash
./scripts/deploy.sh
```

Bu skript avtomatik: `git pull` → rebuild → migratsiya → qayta ishga
tushirish → eski image'larni tozalash.

### Sertifikatni yangilash

Let's Encrypt sertifikatlari 90 kunda tugaydi. Serverning o'zida (host
crontab, masalan haftalik) ishga tushiriladigan buyruq:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Monitoring va portlar

```bash
docker compose --profile monitoring up -d
```

Grafana: http://localhost:3001 (login: `admin` / `.env`dagi
`GRAFANA_ADMIN_PASSWORD`) — internetdan emas, faqat serverning o'zidan
(yoki SSH tunnel orqali) ochiladi.
Prometheus: http://localhost:9090 (xuddi shunday, faqat lokal).

`docker-compose.prod.yml` postgres/redis/prometheus/grafana/bot metrikalari
portini o'zgartirmaydi — ular allaqachon `127.0.0.1`ga cheklangan (bot
`9100`-porti ham). `/metrics` esa nginx darajasida ham to'sib qo'yilgan
(`nginx/nginx.conf`dagi `location /metrics { deny all; }`). 5-qadamdagi
`ufw` qoidalari bilan birgalikda bu portlarning hech biri internetdan
to'g'ridan-to'g'ri ko'rinmaydi — faqat 80/443 (nginx) va 22 (SSH) ochiq.

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

Avtomatik: bot processi ichidagi scheduler har kuni soat 03:00 da to'liq
DB backup oladi (`pg_dump -Fc` + gzip, `backups/db_YYYY-MM-DD.dump.gz`,
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
