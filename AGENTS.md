Before work: local [`project-map.md`](project-map.md) (key `my-study-bot-meta` → `../my-study-bot-meta`), then [`my-study-bot-meta/docs/projects-map.md`](../my-study-bot-meta/docs/projects-map.md) (+ optional `projects-map.local.yaml` in meta). Canonical doc links — `my-study-bot-meta/docs/...`.

Skills and OpenSpec live in **my-study-bot-meta**, not in this package. Before choosing a skill: [`my-study-bot-meta/.agents/skills/bot/`](../my-study-bot-meta/.agents/skills/bot/) (see [`my-study-bot-meta/.agents/AGENTS.md`](../my-study-bot-meta/.agents/AGENTS.md)). If meta path resolution fails, ask the user for the absolute path (or proceed from this `AGENTS.md` alone).

## What This Application Is
`my-study-bot` is a Telegram study bot built with **aiogram v3**. It long-polls Telegram, registers users in SQLite, and is the runtime package for study/subscription flows (product logic still early — see **Current vs intended product**).

This repository is the bot-only package. Shared specs, skills, and docs belong in the sibling [`../my-study-bot-meta`](../my-study-bot-meta).

## What It Is Used For
Main scenarios (target product; study **content** still stubby):

- `/start` — upsert Telegram user into SQLite; first visit grants one-time trial (`trial_used`, 3 min / «3 дня»); greet + inline topic menu.
- Persist user fields (Telegram id, username, `subscription_end`, `is_active`, `trial_used`, `is_admin`, `is_banned`).
- «Подписка» — tariffs catalog (grant without payment); one-time «Получить пробный период» when `trial_used` is False; Cars/Houses gated via `has_active_subscription` (`app/auth.py`).
- `/admin` + кнопка «Админ» — операторская панель (статистика, списки, поиск, ban/unban, роли, grant/revoke тарифов) для bootstrap `ADMIN_IDS` и `User.is_admin`.
- (Planned) real study lesson flows / FSM forms — extend `app/handlers.py`, `app/states.py`, `app/keyboards.py`.

## Who The Users Are
Direct users in Telegram:

- Learners interacting with the bot (registered on first `/start`).
- Operators (bootstrap `ADMIN_IDS` and/or `User.is_admin`) using `/admin` inside Telegram.

There is no separate admin HTTP API or web UI in this package — admin UX is Telegram-only.

## Important
This is a Telegram long-polling bot, not an HTTP API server. Authoritative user/subscription data lives in SQLite (`data/db.sqlite3` by default); handlers receive a DB session via middleware.

Local Windows `main.py` path disables SSL verify and forces IPv4 for VPN/debug only. Linux / Docker / VPS use the clean `Bot(token=…)` branch — do not copy the Windows SSL bypass into production images.

Deploy target: VPS under `/home/deploy/my-study-bot`, Docker Compose + image from GHCR (`ghcr.io/happy-tourist/my-study-bot:latest`), GitHub Actions on `main`.

### Current vs intended product
| Expectation | Today |
|-------------|--------|
| Register user on `/start` | Implemented (`User` upsert + greet + inline topic menu); first visit grants one-time trial (`trial_used`, 3 min / «3 дня») |
| Subscription / study features | Tariffs catalog in «Подписка» (grant without payment); Cars/Houses gated via `has_active_subscription`; study content still stubs |
| Background expiry | `app/scheduler.py` — **temporary** minute windows + cron `minute="*"` (restore day + 10:00 MSK with ЮKassa); reminds 3/2/1, deactivates on expire |
| FSM forms / keyboards | `app/keyboards.py` — topic menu, tariffs, gate CTA, admin panel builders; `app/states.py` — `AdminSearchForm` for admin search |
| Modular routers | Learner `app/handlers.py` + admin `app/handlers_admin.py`, both included from `main.py`; gate/admin helpers in `app/auth.py` |
| `.env.example` | Missing — document vars here; add example when convenient |
| Automated tests | `tests/` — pytest + pytest-asyncio (expiry, auth helper, trial/tariffs/gate handlers) |

When adding study/subscription behavior, prefer extending the existing `User` model and middleware session injection rather than inventing a parallel data path. Expiry side effects stay in `app/scheduler.py`.

## Core Stack
- `aiogram` 3.22 - Telegram bot framework (Router, Dispatcher, polling).
- `python-dotenv` - load `.env` in `main.py` / `app/database.py`.
- `SQLAlchemy` 2.0 + `aiosqlite` - async ORM and SQLite driver.
- `APScheduler` - `AsyncIOScheduler` for subscription expiry cron (`app/scheduler.py`).
- Python `3.13` in Docker (`python:3.13-slim`); local README still mentions 3.10+.

## Development Tools
- `python main.py` - run the bot (activate `.venv`, ensure `.env` has `TG_TOKEN`).
- `pip install -r requirements.txt` - dependencies (no lockfile yet).
- `pytest` - run the suite from this repo root (`tests/`).
- Docker: `Dockerfile` + `docker-compose.yml` for VPS runtime.
- Package manager: pip (`requirements.txt`).

Application entry: `main.py` → `asyncio.run(main())` → `dp.start_polling(bot)`. Prefer keeping Windows-only session hacks inside the `sys.platform == "win32"` branch.

## How Startup Is Organized
1. `load_dotenv()` in `main.py`.
2. Build `Bot` (Windows: custom `AiohttpSession` SSL/IPv4; else default session).
3. `Dispatcher` + `DbSessionMiddleware` on updates.
4. `await init_db()` — `create_all` + `_ensure_sqlite_user_columns` (missing columns from `_SQLITE_USER_COLUMN_DDL`; volume not wiped on deploy).
5. `dp.include_router(router)` from `app.handlers`.
6. Register `startup` / `shutdown` hooks — `start_scheduler(bot)` / `stop_scheduler()`.
7. `start_polling`.

## Config And Env
No committed `.env.example` yet. Relevant variables (see local `.env` / server `.env`):

| Variable | Role |
|----------|------|
| `TG_TOKEN` | Telegram Bot API token (required) |
| `DB_URL` | SQLAlchemy async URL (default `sqlite+aiosqlite:///data/db.sqlite3`) |
| `ADMIN_IDS` | CSV of bootstrap Telegram user ids that are always admins (e.g. `463353358`); OR with `User.is_admin` |

`data/` is gitignored and mounted as a volume in Compose (`./data:/app/data`) so SQLite survives container restarts and deploys. Schema column adds are applied at startup via `_SQLITE_USER_COLUMN_DDL` — push does not reset the DB.

Do not commit secrets (`.env`, `.env.server` are gitignored).

## Database And Middleware
- `app/database.py` — engine, `async_session`, `User` model, `init_db()`, `_SQLITE_USER_COLUMN_DDL` / `_ensure_sqlite_user_columns`.
- `app/middlewares.py` — `DbSessionMiddleware` injects `session: AsyncSession` into handler `data`.
- `app/auth.py` — `has_active_subscription`, `is_admin_user` / `is_banned_user`, `parse_admin_ids` (`ADMIN_IDS`).
- `User` columns: `id` (Telegram BigInteger PK), `username`, `subscription_end`, `is_active`, `trial_used`, `is_admin`, `is_banned`, `created_at`.

Handlers that need DB should declare `session: AsyncSession` and use the injected session (middleware opens/closes the session per update).

When adding a new `User` column: update the model **and** register DDL in `_SQLITE_USER_COLUMN_DDL`; cover with `tests/test_database_schema.py`-style ensure test.

## Handlers And UX Surface
From `app/handlers.py` today:

| Trigger | Behavior |
|---------|----------|
| `/start` | Create `User` if missing (one-time trial); greet; attach inline topic menu (Admin button when admin); banned → «Доступ закрыт.» |
| `menu:cars` / `menu:houses` | Ban check first; then gate via `has_active_subscription`; stub content or refuse + subscription CTA |
| `menu:subscription` | Tariffs list (ban → access closed; otherwise always open) |
| `tariff:*` / `trial:claim` | Ban check; grant tariff minutes / one-time trial onto `subscription_end` |
| `menu:back` | Edit message back to section-choice + main menu (Admin if admin) |
| `/admin` / `menu:admin` | Admin panel (`app/handlers_admin.py`); non-admin → «Доступ закрыт.» |

Builders / helpers:

- `app/keyboards.py` — `main_menu_kb(show_admin=…)`, `back_to_menu_kb()`, `tariffs_kb()`, `subscription_required_kb()`, admin builders (`admin:*`).
- `app/auth.py` — `has_active_subscription`, `is_admin_user` / `is_banned_user`, `extend_subscription`, promote/demote/ban guards.
- `app/states.py` — `AdminSearchForm` (admin user search).
- `app/handlers_admin.py` — admin panel Router (`/admin`, stats, lists, search, card mutations).
- `app/scheduler.py` — temporary minute expiry reminders + deactivation (restore day + 10:00 MSK with ЮKassa).

Keep Russian user-facing strings consistent with existing replies unless product copy is being redesigned.

## Combined Structure
- `main.py` - process entry (Bot, Dispatcher, polling, platform-specific session, scheduler hooks).
- `app/handlers.py` - learner routers / commands.
- `app/handlers_admin.py` - admin panel router.
- `app/auth.py` - subscription gate + admin/ban helpers.
- `app/database.py` - SQLAlchemy models + engine.
- `app/middlewares.py` - DB session injection.
- `app/keyboards.py` - inline topic-menu / tariffs / gate CTA / admin builders.
- `app/scheduler.py` - APScheduler subscription expiry job.
- `app/states.py` - FSM (`AdminSearchForm`).
- `tests/` - pytest suite (expiry, auth, trial/tariffs/gate, admin panel).
- `requirements.txt` - pinned runtime deps (incl. `apscheduler`).
- `Dockerfile` / `docker-compose.yml` - image and VPS run.
- `.github/workflows/deploy.yml` - build/push GHCR + SSH compose deploy.
- `data/` - local/runtime SQLite (not committed).

## Layering
Typical paths:

- Telegram update → Dispatcher middleware → handler (`session` injected) → optional `app/auth.py` gate.
- Persistence → SQLAlchemy `AsyncSession` → SQLite file under `data/`.
- Background → `AsyncIOScheduler` → `check_subscriptions` (own session) → `Bot.send_message` / `User.is_active`.

Prefer thin handlers: DB access via injected session; shared UI in `keyboards.py`; gate math in `auth.py`; multi-step dialogs in `states.py`; expiry in `scheduler.py`. Do not put business logic only inside `main.py`.

## Tests
Run `pytest` from this repo root. Coverage: subscription expiry (minute harness windows + delivery resilience), `has_active_subscription`, trial `/start`, tariffs grants, Cars/Houses gate. Assert **current** scheduler defaults (`EXPIRY_WINDOW_UNIT == "minute"`, minutely cron) until ЮKassa restores day + Moscow 10:00.

## Deploy
- CI: push to `main` (or `workflow_dispatch`) → build/push `ghcr.io/<github.repository>:latest` → SSH to VPS.
- Remote cwd: `/home/deploy/my-study-bot` — `docker login` GHCR → `docker compose pull` → `docker compose up -d` → `docker image prune -f`.
- Compose service `bot` uses `env_file: .env` and volume `./data:/app/data`.
- Do not commit production secrets; keep `.env` on the server only.

## OpenSpec / Skills

Canonical OpenSpec and bot skills live in **my-study-bot-meta**. Resolve meta via key `my-study-bot-meta` in [`project-map.md`](project-map.md).

| Path | Description |
|------|-------------|
| [`my-study-bot-meta/docs/projects-map.md`](../my-study-bot-meta/docs/projects-map.md) | Workspace / OpenSpec path map |
| [`my-study-bot-meta/openspec/`](../my-study-bot-meta/openspec/) | Spec-driven workflow: `specs/` source of truth, `changes/` active work |
| [`my-study-bot-meta/openspec/config.yaml`](../my-study-bot-meta/openspec/config.yaml) | Project context and rules |
| [`my-study-bot-meta/.agents/skills/bot/`](../my-study-bot-meta/.agents/skills/bot/) | Bot / aiogram skills |
| [`my-study-bot-meta/.agents/skills/`](../my-study-bot-meta/.agents/skills/) | OpenSpec skills |
| [`my-study-bot-meta/.agents/AGENTS.md`](../my-study-bot-meta/.agents/AGENTS.md) | Full docs/skills index in meta |
| [`my-study-bot-meta/AGENTS.md`](../my-study-bot-meta/AGENTS.md) | Meta always-on agent instructions |

There are **no** local `.agents/skills/` in this package. Runtime paths in skills (`app/…`, `main.py`) are relative to this bot repo root.

Typical Cursor chat workflow: `/opsx-explore` → `/opsx-propose` → artifact review → `/opsx-apply` → `/opsx-sync` → `/opsx-archive`. OpenSpec artifacts are created and archived in **my-study-bot-meta**, not in this repo.

Commands (`python main.py`, `pip install -r requirements.txt`, Docker build/compose) are run by the **agent** from this package root. Do not wait for user confirmation; fix failures before claiming done.

## Related Package
- [`../my-study-bot-meta`](../my-study-bot-meta) — docs, OpenSpec, and agent skills (sibling). Prefer changing product contracts in coordination with meta specs.
