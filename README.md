# Сборщик — подбор комплектующих для ПК

Экспертная система подбора конфигурации ПК для вымышленного магазина «Сборщик».
Курсовой проект по дисциплине «Интеллектуальные информационные системы» (АлтГУ).

- Архитектура: [`docs/architecture.md`](docs/architecture.md)
- Как работает программа (вики): [`docs/wiki/README.md`](docs/wiki/README.md)
- Правила работы с проектом: [`CLAUDE.md`](CLAUDE.md)

## Стек

| Часть | Технологии |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + asyncpg, Alembic, structlog |
| БД | PostgreSQL 16 |
| Frontend | React 19, TypeScript (strict), Vite, Mantine 7, TanStack Query, React Router |
| Качество | ruff, mypy, pytest; eslint, prettier, Vitest; pre-commit |

## Требования

- Python 3.12, [uv](https://docs.astral.sh/uv/)
- Node.js 22 LTS (через nvm: `export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"`)
- PostgreSQL 16, запущенный локально

## Первый запуск

### 1. База данных (один раз)

```bash
sudo -u postgres createuser -P pcapp          # запомните пароль
sudo -u postgres createdb -O pcapp pcapp
sudo -u postgres createdb -O pcapp pcapp_test # для интеграционных тестов
```

### 2. Backend

```bash
cd backend
cp .env.example .env      # заполнить DATABASE_URL, TEST_DATABASE_URL, JWT_SECRET
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed        # каталог + база знаний + первая публикация (повторный запуск безопасен)
uv run uvicorn app.main:create_app --factory --reload --port 8000
```

`uv run python -m scripts.seed --dry-run` только проверяет файлы знаний, не трогая БД. Публикация прогоняет эталонные кейсы (~40 с); `--skip-golden` — быстрая публикация без них.
Формат CSV каталога описан в [`knowledge/catalog/README.md`](knowledge/catalog/README.md).

- Swagger UI: http://localhost:8000/docs
- Проверки: http://localhost:8000/api/v1/healthz (процесс жив), http://localhost:8000/api/v1/readyz (БД доступна)
- Каталог: http://localhost:8000/api/v1/components?category=cpu, схемы фреймов: http://localhost:8000/api/v1/frames

### Попробовать подбор через Swagger

1. `GET /api/v1/questionnaire` — вопросы визарда и допустимые ответы.
2. `POST /api/v1/consultations` с телом, например:
   ```json
   {"answers": {"tasks": {"main": "aaa_gaming", "extra": ["video_editing"]}, "budget": 170000,
                "monitor": "qhd_144", "color": "white", "storage_gb": 1000}}
   ```
3. `POST /api/v1/consultations/{id}/builds` — три варианта сборки.
4. Для сборки: `GET /api/v1/builds/{id}` (прогноз FPS), `…/explanation`, `…/why-not?component_id=`,
   `…/alternatives?category=gpu`, `POST …/hypotheses` с
   `{"predicate": "runs_game", "args": {"game": "cyberpunk_2077", "preset": "ultra"}, "bindings": {"target_fps": 60}}`,
   `POST …/modifications` с `{"kind": "cheaper", "category": "gpu"}`, `GET …/pdf`.

Сгенерировать `JWT_SECRET`: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 3. Frontend

```bash
cd frontend
npm install
npm run gen:api   # схема OpenAPI выгружается из кода backend, сервер запускать не нужно
npm run dev       # http://localhost:5173, запросы /api проксируются на :8000
```

Backend должен быть запущен (шаг 2). Сквозной сценарий в браузере:

1. http://localhost:5173 → «Подобрать ПК».
2. Визард: веса задач (например, «Современные игры» 100%), бюджет, монитор, игры, внешний вид, «Что уже есть» → «Подобрать сборки».
3. Результаты: карточки «Эконом / Оптимум / Максимум» (совпавшие объединяются), «Сравнить варианты», «Изменить ответы».
4. Сборка: меню «⋯» у детали (дешевле, дороже, замена, закрепить, исключить), «Почему не этот товар?», перенос бюджета, вкладки «Производительность», «Почему так» (+ «Экспертный режим»), «Потянет ли?», «Сохранить», «PDF».
5. Невыполнимый запрос (например, игры в 4K за 50 000 ₽): что мешает, ослабления с кнопкой «Подобрать с этим», лучшее возможное.

## Проверки

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests && uv run pytest --cov
cd frontend && npm run lint && npm run typecheck && npm run test -- --run
```

База знаний (правила, справочники, golden cases в `knowledge/`):

```bash
cd backend
uv run python -m scripts.generate_rules     # после правки knowledge/tables/*.yaml
uv run python -m scripts.validate_kb        # статические проверки; --strict — и предупреждения
uv run pytest tests/kb                      # проверки базы знаний и golden cases
```

Интеграционные тесты (`backend/tests/integration`) работают только с базой `pcapp_test`.
Если `TEST_DATABASE_URL` не задан ни в окружении, ни в `backend/.env`, они пропускаются.

### pre-commit

Проект пока не под git. После `git init`:

```bash
cd backend && uv run pre-commit install --config ../.pre-commit-config.yaml
```

## Структура

```
backend/     FastAPI-приложение, миграции, скрипты, тесты
frontend/    SPA на React + Mantine
knowledge/   база знаний: каталог (CSV), справочники и правила (YAML), golden cases
docs/        архитектура, ADR, вики
```

## Миграции

```bash
cd backend
uv run alembic revision --autogenerate -m "осмысленное_имя"
uv run alembic upgrade head
```
