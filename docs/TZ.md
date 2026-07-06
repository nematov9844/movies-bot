# 📋 TEXNIK TOPSHIRIQ (TZ) — Telegram Media Platform

> **Bu hujjat AI agent (Claude Code) uchun yozilgan to'liq texnik topshiriq.**
> Agent bu hujjatni boshidan oxirigacha o'qib, loyihani **to'liq, avtonom ravishda** qurishi kerak.
> Foydalanuvchidan FAQAT quyidagilarni so'rash mumkin: `BOT_TOKEN`, `STORAGE_CHANNEL_ID`, `OWNER_ID`, `POSTGRES_PASSWORD`, `JWT_SECRET`. Qolgan barcha qarorlarni shu TZ asosida mustaqil qabul qil.

---

## 🤖 AGENT UCHUN ISH TARTIBI (MUHIM!)

1. **Bosqichlarni tartib bilan bajar** (1 → 18). Bosqichni tugatmasdan keyingisiga o'tma.
2. Har bosqich oxirida: `pytest` ishga tushir, xatolar bo'lsa tuzat, keyin **git commit** qil (`feat(phase-N): ...` formatida).
3. Kod yozishdan oldin `.env` mavjudligini tekshir. Yo'q bo'lsa — foydalanuvchidan yuqoridagi 5 ta qiymatni so'ra, `.env.example` dan `.env` yarat va to'ldir.
4. Har bir yangi jadval uchun Alembic migration yarat: `alembic revision --autogenerate -m "..."`.
5. Docker mavjud bo'lsa `docker compose up -d postgres redis` bilan test muhitini ko'tar. Docker yo'q bo'lsa foydalanuvchiga ayt va lokal PostgreSQL/Redis so'ra.
6. Hech qachon placeholder/TODO kod qoldirma — har bir funksiya to'liq ishlashi shart.
7. Barcha user-facing matnlar **o'zbek tilida** (Latin). Kod, kommentlar, log xabarlari — inglizcha.
8. Savol tug'ilsa — bu TZ dagi eng yaqin qoidaga tayangan holda o'zing hal qil. Foydalanuvchini faqat kredensiallar uchun bezovta qil.

---

## 🎯 LOYIHA MAQSADI

Telegram orqali kino tarqatadigan, lekin kelajakda seriallar/kitoblar/kurslar qo'shiladigan **Media Platform**:

- User kino **kodini** yuboradi → bot private kanaldan `file_id` orqali videoni yuboradi.
- **Force Subscribe**: video olishdan oldin user majburiy kanallarga obuna bo'lishi shart (moslashuvchan boshqariladi).
- **Premium**: pullik obuna — reklamasiz, force subscribe'siz, premium kontent.
- **Web Admin Panel**: hamma narsani brauzerdan boshqarish.
- Videolar **private Telegram kanalda** saqlanadi (server diskida EMAS) — faqat `file_id` bazada turadi.

```
Telegram Users → Bot → Business Logic → PostgreSQL + Redis
                              ↓
                Private Channel (video storage)
                              ↓
                       Web Admin Panel
```

---

## 🛠 TEXNOLOGIYALAR (qat'iy)

| Qatlam | Texnologiya |
|---|---|
| Til | Python 3.12+ |
| Bot | Aiogram 3.x (polling; webhook'ga o'tish oson bo'lsin) |
| API | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2 (async, `asyncpg`) |
| Migration | Alembic (async env) |
| Validation | Pydantic v2 + pydantic-settings |
| DB | PostgreSQL 16 |
| Cache/Queue/FSM | Redis 7 |
| Scheduler | APScheduler |
| Log | structlog (prod: JSON, debug: console) |
| Test | pytest + pytest-asyncio |
| Deploy | Docker + Docker Compose + Nginx |
| Admin Panel | Next.js 14+ (App Router) + React + Tailwind + shadcn/ui |
| Monitoring | Prometheus + Grafana, Sentry (DSN bo'lsa) |

---

## 🏗 ARXITEKTURA QOIDALARI (buzish TAQIQLANADI)

```
Handler → Service → Repository → Database
```

1. **Handler** hech qachon to'g'ridan-to'g'ri DB/Repository ga murojaat qilmaydi — faqat Service chaqiradi.
2. **Service** — biznes logika. Repository'lardan foydalanadi, boshqa Service chaqirishi mumkin.
3. **Repository** — faqat DB so'rovlar. Biznes logika yo'q.
4. Har bir modul o'z papkasida: `services/movie/`, `services/force_subscribe/` va h.k.
5. Barcha config `.env` + `settings` jadvali orqali. Kodda hardcode qiymat bo'lmasin.
6. Barcha vaqtlar UTC'da saqlanadi (`DateTime(timezone=True)`), userga ko'rsatishda `Asia/Tashkent`.
7. Type hints hamma joyda majburiy. `ruff` xatosiz o'tishi kerak.

### Loyiha tuzilishi

```text
movie-platform/
├── app/
│   ├── bot/
│   │   ├── handlers/          # user/, admin/ papkalarga bo'lingan
│   │   ├── middlewares/       # db, throttling, force_subscribe, user_upsert, i18n
│   │   ├── filters/           # IsAdmin, IsOwner, IsPremium
│   │   ├── keyboards/         # inline/reply builder'lar
│   │   ├── states/            # FSM state'lar
│   │   └── routers.py
│   ├── api/
│   │   ├── routes/            # auth, movies, users, channels, premium, broadcast, stats, settings, logs
│   │   ├── dependencies/      # get_current_admin, pagination
│   │   └── schemas/           # Pydantic request/response modellari
│   ├── core/
│   │   ├── config.py
│   │   ├── logger.py
│   │   ├── security.py        # JWT, password hash (bcrypt)
│   │   ├── constants.py
│   │   └── permissions.py     # Role enum + tekshiruvlar
│   ├── database/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── session.py
│   │   └── base.py
│   ├── services/
│   ├── scheduler/             # APScheduler joblar
│   ├── utils/
│   ├── tests/
│   ├── bot_main.py
│   └── api_main.py
├── admin-panel/               # Next.js loyiha
├── alembic/
├── docker/
├── nginx/
├── scripts/                   # backup.sh, restore.sh
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

> **Eslatma:** Agar loyiha ildizida 1-bosqich skeleti allaqachon mavjud bo'lsa — uni o'chirib tashlama, ustiga davom et.

---

## 📌 1-BOSQICH — Infrastructure

**Qilinadi:** git init, `pyproject.toml`, Docker + docker-compose (postgres, redis, migrations, bot, api servicelari), pydantic-settings config, structlog, Alembic async env, `.env.example`, `.gitignore`, README.

**`.env.example` majburiy kalitlar:**

```
BOT_TOKEN=
STORAGE_CHANNEL_ID=
OWNER_ID=
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=movie
POSTGRES_PASSWORD=
POSTGRES_DB=movie_platform
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
API_HOST=0.0.0.0
API_PORT=8000
JWT_SECRET=
DEBUG=false
ENVIRONMENT=production
SENTRY_DSN=
```

**Qabul mezoni:** `docker compose up -d` dan keyin `/health` endpoint `{"status":"ok"}` qaytaradi, bot `/start` ga javob beradi.

---

## 📌 2-BOSQICH — Database Design

Barcha jadvallar bitta migration to'plamida yaratiladi. **Aniq sxema:**

### `users`
| ustun | tur | izoh |
|---|---|---|
| id | BIGINT PK | Telegram user ID (autoincrement EMAS) |
| username | VARCHAR(64) NULL | |
| first_name | VARCHAR(128) NULL | |
| last_name | VARCHAR(128) NULL | |
| language | VARCHAR(8) DEFAULT 'uz' | uz / ru / en |
| is_active | BOOL DEFAULT true | botni bloklamagan |
| is_blocked | BOOL DEFAULT false | admin tomonidan ban |
| referrer_id | BIGINT NULL FK→users.id | kim taklif qilgan |
| last_seen_at | TIMESTAMPTZ NULL | |
| created_at, updated_at | TIMESTAMPTZ | |

### `movies`
| ustun | tur | izoh |
|---|---|---|
| id | BIGSERIAL PK | |
| code | VARCHAR(32) UNIQUE NOT NULL, INDEX | user yuboradigan kod (masalan `123`) |
| title | VARCHAR(255) NOT NULL | |
| description | TEXT NULL | |
| file_id | VARCHAR(255) NOT NULL | Telegram video file_id |
| file_unique_id | VARCHAR(64) NULL | |
| storage_message_id | BIGINT NULL | private kanaldagi message id |
| duration | INT NULL | soniyada |
| file_size | BIGINT NULL | baytda |
| quality | VARCHAR(16) NULL | 480p/720p/1080p |
| is_premium | BOOL DEFAULT false | faqat premium userlar uchun |
| is_active | BOOL DEFAULT true | |
| view_count | BIGINT DEFAULT 0 | |
| year | INT NULL | |
| created_by | BIGINT NULL FK→admins.id | |
| created_at, updated_at | | |

### `categories`
`id BIGSERIAL PK`, `name VARCHAR(64) UNIQUE`, `slug VARCHAR(64) UNIQUE`, `is_active BOOL`, timestamps.

### `movie_categories`
`movie_id FK→movies.id ON DELETE CASCADE`, `category_id FK→categories.id ON DELETE CASCADE`, композит PK (movie_id, category_id).

### `admins`
| ustun | tur | izoh |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT UNIQUE FK→users.id | Telegram ID |
| role | VARCHAR(16) | `owner` / `admin` / `moderator` |
| password_hash | VARCHAR(255) NULL | web panel login uchun (bcrypt) |
| is_active | BOOL DEFAULT true | |
| created_at, updated_at | | |

### `channels` (Force Subscribe)
| ustun | tur | izoh |
|---|---|---|
| id | BIGSERIAL PK | |
| channel_id | BIGINT UNIQUE NOT NULL | Telegram kanal ID (-100...) |
| username | VARCHAR(64) NULL | @siz |
| title | VARCHAR(255) | |
| invite_link | VARCHAR(255) NULL | private kanal uchun |
| priority | INT DEFAULT 0 | kichigi birinchi ko'rsatiladi |
| is_active | BOOL DEFAULT true | ON/OFF |
| is_required | BOOL DEFAULT true | majburiymi |
| start_date | TIMESTAMPTZ NULL | shu sanadan boshlab ishlaydi |
| expire_date | TIMESTAMPTZ NULL | shu sanadan keyin o'chadi |
| daily_start_time | TIME NULL | masalan 08:00 |
| daily_end_time | TIME NULL | masalan 22:00 |
| join_limit | INT NULL | masalan 200 |
| current_joins | INT DEFAULT 0 | shu bot orqali qo'shilganlar |
| created_at, updated_at | | |

### `premium_plans`
`id BIGSERIAL PK`, `name VARCHAR(64)`, `days INT` (7/30/90/365), `price INT` (so'mda), `is_active BOOL`, timestamps. Seed: 4 ta plan.

### `premium_users`
`id BIGSERIAL PK`, `user_id FK→users.id INDEX`, `plan_id FK→premium_plans.id`, `starts_at TIMESTAMPTZ`, `expires_at TIMESTAMPTZ INDEX`, `is_active BOOL`, `payment_method VARCHAR(32) NULL`, `granted_by BIGINT NULL FK→admins.id` (admin qo'lda bergan bo'lsa), timestamps.

### `settings`
`key VARCHAR(64) PK`, `value TEXT`, `type VARCHAR(16)` (`str`/`int`/`bool`/`json`), `description VARCHAR(255)`, `updated_at`. Seed qiymatlar: `bot_name`, `maintenance_mode=false`, `welcome_text`, `support_username`, `force_subscribe_enabled=true`, `premium_enabled=true`, `ads_enabled=true`, `movie_not_found_text`.

### `broadcasts`
`id BIGSERIAL PK`, `admin_id FK→admins.id`, `message_chat_id BIGINT`, `message_id BIGINT` (copy_message uchun manba), `target VARCHAR(16)` (`all`/`premium`/`free`), `status VARCHAR(16)` (`pending`/`running`/`done`/`cancelled`), `total INT`, `sent INT DEFAULT 0`, `failed INT DEFAULT 0`, `blocked INT DEFAULT 0`, `started_at`, `finished_at`, timestamps.

### `statistics`
`id BIGSERIAL PK`, `date DATE UNIQUE`, `new_users INT`, `active_users INT`, `movies_sent INT`, `errors INT`, `api_requests INT`, timestamps. (Kunlik agregat — scheduler yozadi.)

### `movie_views`
`id BIGSERIAL PK`, `movie_id FK INDEX`, `user_id FK INDEX`, `created_at`. (Top movies / top users hisoblash uchun xom ma'lumot.)

### `referrals`
`id BIGSERIAL PK`, `referrer_id FK→users.id INDEX`, `referred_id FK→users.id UNIQUE`, `created_at`.

### `audit_logs`
`id BIGSERIAL PK`, `admin_id FK NULL`, `action VARCHAR(64)`, `entity VARCHAR(32)`, `entity_id VARCHAR(64)`, `payload JSONB NULL`, `ip VARCHAR(45) NULL`, `created_at`.

**Qabul mezoni:** `alembic upgrade head` xatosiz o'tadi, barcha FK'lar mavjud, seed data script (`scripts/seed.py`) ishlaydi.

---

## 📌 3-BOSQICH — Core Architecture

- `Base`, `TimestampMixin`, umumiy `BaseRepository[T]` (get, get_many, create, update, delete, count) generic klass.
- Har model uchun Repository, har modul uchun Service.
- Bot middleware'lari: `DbSessionMiddleware`, `UserUpsertMiddleware` (har update'da userni upsert qiladi), `ThrottlingMiddleware` (Redis, 1 user = sekundiga max 1 og'ir so'rov), `MaintenanceMiddleware` (settings'dagi `maintenance_mode=true` bo'lsa oddiy userlarga "Texnik ishlar" deb javob beradi, adminlar ishlashda davom etadi).
- `UnitOfWork` pattern shart emas — session-per-update yetarli.

---

## 📌 4-BOSQICH — Authentication & Roles

Rollar ierarxiyasi: `owner > admin > moderator > user`.

| Amal | owner | admin | moderator |
|---|---|---|---|
| Admin qo'shish/o'chirish | ✅ | ❌ | ❌ |
| Settings o'zgartirish | ✅ | ✅ | ❌ |
| Kino qo'shish/o'chirish | ✅ | ✅ | ✅ |
| Broadcast | ✅ | ✅ | ❌ |
| Kanal (force sub) boshqarish | ✅ | ✅ | ❌ |
| Premium berish | ✅ | ✅ | ❌ |
| Statistika ko'rish | ✅ | ✅ | ✅ |

- Bot tarafda: `IsAdmin`/`IsOwner` filterlar + `permissions.py` da `require_permission(role, action)`.
- API tarafda: JWT (access 30 min + refresh 7 kun), `POST /api/auth/login` (user_id + password), bcrypt.
- `.env` dagi `OWNER_ID` birinchi ishga tushishda avtomatik `admins` jadvaliga `owner` sifatida seed qilinadi.
- Muhim admin amallar `audit_logs` ga yoziladi.

---

## 📌 5-BOSQICH — User Module (bot)

Komandalar/tugmalar (reply keyboard, o'zbekcha):

- `/start` — salomlashish + referral parametrni qayta ishlash (`/start ref_<user_id>`), asosiy menyu: 🔍 Kino qidirish, 👤 Profil, ⭐ Premium, ⚙️ Sozlamalar, 📊 Statistika (o'z statistikasi), 🎁 Do'stlarni taklif qilish.
- **Profil** — ID, ism, premium holati (muddati bilan), nechta kino ko'rgani, referral soni.
- **Sozlamalar** — til tanlash (uz/ru; matnlar `app/core/i18n.py` yoki oddiy dict orqali; kamida uz to'liq, ru skeleton).
- **Taklif** — `https://t.me/<bot>?start=ref_<id>` link + nechta odam kelgani.

---

## 📌 6-BOSQICH — Movie Module

### Admin oqimi (FSM bilan)
1. Admin `/panel` → "🎬 Kino qo'shish".
2. Video yuboradi → bot videoni **STORAGE_CHANNEL** ga `copy_message`/`send_video` qiladi → `file_id`, `storage_message_id` oladi.
3. Bot ketma-ket so'raydi: kod (unique tekshiriladi), nomi, tavsif (skip mumkin), kategoriya (inline tanlov), premiummi (ha/yo'q).
4. Tasdiqlash → DB ga yoziladi → "✅ Kino qo'shildi. Kod: `123`".

Admin shuningdek: kino tahrirlash, o'chirish (soft — `is_active=false`), kod bo'yicha topish.

### User oqimi
1. User raqam/kod yuboradi.
2. `MovieService.get_by_code()` — Redis cache (TTL 1 soat) → DB.
3. Topilsa: force subscribe tekshiruvi (7-bosqich) → premium tekshiruvi (`is_premium` kino bo'lsa) → video `send_video(file_id)` bilan yuboriladi, caption: nomi + tavsif + bot username. `view_count += 1`, `movie_views` ga yoziladi.
4. Topilmasa: `movie_not_found_text` (settings'dan).

### Qidiruv va ro'yxatlar
- 🔍 Qidiruv: nom bo'yicha `ILIKE` qidiruv, inline natijalar (pagination, 10 tadan).
- Top kinolar (view_count bo'yicha), Yangi qo'shilganlar (oxirgi 10), Mashhur (oxirgi 7 kunda eng ko'p ko'rilgan — `movie_views` dan).
- Kategoriyalar bo'yicha ko'rish.

---

## 📌 7-BOSQICH — Force Subscribe System (eng muhim modul!)

`ForceSubscribeService.check(user_id) -> list[Channel]` — user obuna bo'lmagan **aktiv** kanallar ro'yxatini qaytaradi.

Kanal "aktiv" hisoblanadi, agar **hammasi** to'g'ri bo'lsa:
1. `is_active = true`
2. `start_date` NULL yoki o'tgan
3. `expire_date` NULL yoki kelmagan
4. `daily_start_time/daily_end_time` NULL yoki hozirgi Tashkent vaqti oraliqda (masalan 08:00–22:00; agar start > end bo'lsa — tun oralig'i deb hisobla)
5. `join_limit` NULL yoki `current_joins < join_limit`

Qoidalar:
- Settings'da `force_subscribe_enabled=false` bo'lsa — butun tizim o'chadi.
- **Premium user uchun tekshiruv umuman o'tkazilmaydi.**
- Adminlar ham tekshirilmaydi.
- Obuna holati `bot.get_chat_member()` bilan tekshiriladi, natija Redis'da 60 soniya cache'lanadi (`fs:{user_id}:{channel_id}`).
- Obuna bo'lmagan kanallar bo'lsa: inline keyboard — har kanalga "➕ Obuna bo'lish" (url/invite_link) + pastda "✅ Tekshirish" callback. Tekshirishda cache tozalanadi va qayta tekshiriladi; hammasi ok bo'lsa asl so'rov davom etadi (kino kodi FSM/Redis'da saqlab turiladi).
- User obuna bo'lgani aniqlanganda mos kanal `current_joins += 1` (bir user bir kanal uchun faqat bir marta — Redis set bilan).
- Tekshiruv **middleware** sifatida amalga oshiriladi va faqat kontent so'rovlariga qo'llanadi (kino kodi, qidiruv) — `/start`, sozlamalar, premium sahifalariga emas.

### Admin oqimi — kanal qo'shish (FSM bilan, video qo'shishga o'xshash)

1. Admin `/panel` → "📢 Kanallar" → "➕ Kanal qo'shish".
2. Bot so'raydi: **kanaldan istalgan postni forward qiling** yoki **@username / -100... ID yuboring**.
3. Bot tekshiradi: kanal mavjudmi (`get_chat`), **bot u kanalda adminmi** (`get_chat_member` — bo'lmasa xato: "Avval botni kanalga admin qiling"). Public bo'lsa username, private bo'lsa `export_chat_invite_link` bilan invite_link olinadi.
4. Bot ketma-ket so'raydi (har birini ⏭ Skip qilish mumkin, default qiymatlar bilan):
   - **Priority** (default 0)
   - **Join limit** (default cheksiz)
   - **Boshlanish/tugash sanasi** (default darhol / muddatsiz)
   - **Kunlik vaqt oralig'i** (masalan `08:00-22:00`, default doim)
5. Tasdiqlash kartasi (barcha parametrlar ko'rsatiladi) → "✅ Kanal qo'shildi va yoqildi".

Kanal ro'yxatida har kanal uchun inline tugmalar: 🔛 ON/OFF, ✏️ Tahrirlash (istalgan parametrni alohida), 📊 Statistika (`current_joins`/limit), 🗑 O'chirish (tasdiqlash bilan).

Bularning barchasi web paneldagi Channels sahifasida ham mavjud (13-bosqich).

---

## 📌 8-BOSQICH — Premium

- Planlar: 7/30/90/365 kun (seed, narxlar settings orqali o'zgartiriladi).
- **Bu bosqichda to'lov integratsiyasi YO'Q** — faqat: user "⭐ Premium" bosadi → planlar ro'yxati → tanlaganda "To'lov uchun @support ga yozing" (settings'dagi `support_username`) + admin'ga notifikatsiya boradi.
- Admin `/panel` yoki web orqali userga premium beradi: user_id + plan → `premium_users` yoziladi. User allaqachon premiumda bo'lsa — muddat **ustiga qo'shiladi** (extend).
- Premium tugashidan 24 soat oldin userga ogohlantirish, tugaganda xabar (scheduler).
- Premium imkoniyatlari kodda tekshiriladigan yagona joy: `PremiumService.is_premium(user_id)` (Redis cache 5 min).
- Interfeys: to'lov provayderlari (Click/Payme/Uzum/Telegram Stars) keyin ulanadigan qilib `PaymentProvider` abstract class tayyorlab qo'y, lekin implementatsiya qilma.

---

## 📌 9-BOSQICH — Broadcast

- Admin `/panel` → "📣 Broadcast" → xabar yuboradi (har qanday tur: matn/foto/video) → target tanlaydi (hamma/premium/free) → tasdiqlaydi.
- Xabar `copy_message` bilan yuboriladi (forward emas — "forwarded from" chiqmasin).
- Navbat: user ID'lar Redis list'ga yoziladi, alohida **asyncio worker** sekundiga max **25 xabar** yuboradi (Telegram limit 30/s, zaxira bilan).
- `RetryAfter` (flood wait) kelsa — kutadi. `Forbidden` (bot bloklangan) → `users.is_active=false`, `blocked += 1`.
- Progress har 10 soniyada admin xabarida edit qilinadi: `Yuborildi: 1200/5000 | Xato: 12 | Blok: 34`.
- "⏹ To'xtatish" tugmasi — status `cancelled`.
- Bir vaqtda faqat bitta broadcast (Redis lock).

---

## 📌 10-BOSQICH — Statistics

- Bot `/panel` → "📊 Statistika": bugun/hafta/oy — yangi userlar, aktiv userlar, yuborilgan kinolar, top 10 kino, top 10 user, xatolar soni.
- Web panelda grafiklar (recharts): kunlik yangi userlar (30 kun), kunlik ko'rishlar, premium konversiya.
- Kunlik agregat scheduler tomonidan `statistics` jadvaliga yoziladi.
- Real-time hisoblagichlar Redis'da (`stats:today:new_users` va h.k.), kun oxirida DB ga flush.

---

## 📌 11-BOSQICH — Scheduler (APScheduler)

Bot process ichida ishga tushadi:

| Interval | Job |
|---|---|
| 5 min | expired kanallarni deaktivatsiya (`expire_date` o'tgan → `is_active=false`), join_limit to'lganlarni o'chirish |
| 30 min | premium muddati tugaganlarni `is_active=false` + userga xabar; 24h qolganlarga ogohlantirish |
| kuniga 1 (00:05) | kecha uchun statistics agregati |
| kuniga 1 (03:00) | DB backup (`scripts/backup.sh` → `pg_dump` → `backups/`, 7 kundan eskisi o'chiriladi) |
| 1 soat | Redis'dagi eskirgan keylar tozalash (application-level keylar) |

Har job xatoni yutib log qiladi — bitta job yiqilsa boshqalari ishlashda davom etadi.

---

## 📌 12-BOSQICH — Settings Module

- `SettingsService.get(key)` — Redis cache (TTL 60s), o'zgartirilganda cache invalidatsiya.
- Bot `/panel` → "⚙️ Sozlamalar": maintenance ON/OFF, welcome text, support username, force subscribe ON/OFF, premium ON/OFF.
- Restart TALAB QILINMAYDI — hamma joy settings'ni service orqali o'qiydi.

---

## 📌 13-BOSQICH — Web Admin Panel

`admin-panel/` — Next.js 14+ (App Router) + Tailwind + shadcn/ui, FastAPI'ga so'rov yuboradi.

Sahifalar:
1. **Login** — user_id + parol → JWT (httpOnly cookie yoki localStorage — httpOnly afzal, refresh flow bilan).
2. **Dashboard** — karta ko'rsatkichlar (jami user, bugun yangi, jami kino, aktiv premium) + 30 kunlik grafik.
3. **Movies** — jadval (qidiruv, pagination, sort), qo'shish/tahrirlash modal (file_id qo'lda yoki bot orqali), soft delete.
4. **Users** — qidiruv (ID/username), ban/unban, premium berish tugmasi, user detali.
5. **Premium** — aktiv obunalar ro'yxati, planlar CRUD.
6. **Channels** — force subscribe kanallar CRUD, ON/OFF switch, limit/sana/vaqt formalari, joins statistikasi.
7. **Broadcast** — tarix + status/progress (polling har 3s), yangi broadcast faqat bot orqali (web'dan xabar tuzish shart emas, lekin to'xtatish tugmasi bo'lsin).
8. **Settings** — barcha settings formada.
9. **Logs** — audit_logs jadvali (filter: admin, action, sana).
10. **Admins** — faqat owner ko'radi: qo'shish (user_id + rol + parol), o'chirish.

FastAPI'da mos REST endpointlar: `/api/auth/*`, `/api/movies`, `/api/users`, `/api/channels`, `/api/premium`, `/api/broadcasts`, `/api/settings`, `/api/stats`, `/api/audit-logs`, `/api/admins`. Hammasi JWT bilan himoyalangan, rol tekshiruvi bilan. Pagination: `?page=1&size=20`, javob `{items, total, page, size}`.

---

## 📌 14-BOSQICH — Monitoring

- FastAPI'ga `prometheus-fastapi-instrumentator` → `/metrics`.
- Bot uchun custom metrikalar: `bot_updates_total`, `bot_movies_sent_total`, `bot_errors_total` (prometheus_client, alohida 9100 portda).
- docker-compose'ga `prometheus` + `grafana` servicelari (profil `monitoring` — `docker compose --profile monitoring up`), tayyor datasource + bitta asosiy dashboard JSON provisioning bilan.
- `SENTRY_DSN` berilgan bo'lsa — sentry-sdk (bot + api).

---

## 📌 15-BOSQICH — Security

- Rate limit: bot — ThrottlingMiddleware (yuqorida); API — `slowapi` (login: 5/min per IP, qolganlari 60/min).
- SQL Injection — faqat ORM/parametrlangan so'rovlar (raw SQL taqiqlanadi).
- XSS — userdan kelgan matnlar botga qaytarilganda `html.escape`.
- CSRF — API token-based (JWT header) bo'lgani uchun CSRF xavfi minimal; cookie ishlatilsa `SameSite=Strict`.
- Nginx: faqat 80/443 ochiq, API va panel reverse proxy orqali, `/metrics` va DB portlari tashqariga yopiq.
- Secrets faqat `.env` da, git'ga kirmaydi.
- Admin API'ga IP whitelist (settings'da `admin_ip_whitelist`, bo'sh bo'lsa o'chirilgan).
- Barcha login urinishlari va admin amallar audit_logs'da.

---

## 📌 16-BOSQICH — Backup

- `scripts/backup.sh` — `pg_dump -Fc` → `backups/db_YYYY-MM-DD.dump`, gzip, 7 kunlik rotatsiya. Scheduler chaqiradi.
- `scripts/restore.sh <fayl>` — tiklash.
- Haftalik: settings jadvali JSON export.
- README'da tiklash bo'yicha qo'llanma.

---

## 📌 17-BOSQICH — Testing

- pytest + pytest-asyncio, test DB — docker'dagi postgres'da alohida `movie_platform_test` baza (har testda transaction rollback).
- Majburiy qamrov:
  - Repository testlar (users, movies, channels CRUD)
  - Service testlar: `ForceSubscribeService` aktiv-kanal logikasi (5 shart har biri alohida test!), `PremiumService.is_premium` + extend, `MovieService.get_by_code` + cache
  - API testlar (httpx AsyncClient): auth flow, movies CRUD, permission tekshiruvlari (moderator settings o'zgartira olmasligi)
  - Bot handler testlar: aiogram uchun mock bot bilan `/start`, kino kodi oqimi
- Minimal 40 ta test, hammasi yashil.

---

## 📌 18-BOSQICH — Deploy

- `nginx/nginx.conf`: 80→443 redirect, `api.domain.uz` → FastAPI:8000, `panel.domain.uz` → Next.js:3000. Certbot uchun izohlar.
- Production `docker-compose.prod.yml`: restart policy, log rotation (`max-size: 10m`), healthcheck'lar.
- `scripts/deploy.sh`: git pull → build → migrate → restart.
- README'da to'liq deploy qo'llanma: server talablari (2 CPU / 4GB RAM minimal), qadam-baqadam.

---

## ✅ YAKUNIY QABUL MEZONLARI (agent o'zini tekshiradi)

1. `docker compose up -d --build` bir urinishda ko'tariladi.
2. Bot: `/start` → menyu → kino kodi → force subscribe → obuna → video keladi.
3. Admin: `/panel` dan kino qo'shadi, kanal qo'shadi, broadcast yuboradi, premium beradi.
4. Web panel: login → dashboard → barcha 10 sahifa ishlaydi.
5. `pytest` — 40+ test yashil.
6. `ruff check .` — xatosiz.
7. Har bosqich alohida commit'da.
8. README'da o'rnatish + deploy + backup/restore qo'llanmalari to'liq.

---

## ❓ FOYDALANUVCHIDAN SO'RALADIGAN YAGONA NARSALAR

Ish boshida bir marta so'ra (agar `.env` da bo'lmasa):

1. `BOT_TOKEN` — @BotFather'dan
2. `STORAGE_CHANNEL_ID` — videolar saqlanadigan private kanal ID (bot u yerda admin bo'lishi kerak)
3. `OWNER_ID` — egasining Telegram ID'si
4. `POSTGRES_PASSWORD` — istalgan kuchli parol (o'zing generatsiya qilishni taklif qil)
5. `JWT_SECRET` — o'zing generatsiya qil (`openssl rand -hex 32`) va ayt

Force subscribe kanallari, kinolar, planlar — bularning hammasi keyin bot/panel orqali qo'shiladi, hozir so'rama.
