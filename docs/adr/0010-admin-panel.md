# ADR 0010. Админка этапа 9: catalog_imports, golden cases в БД, регенерация в черновик, экспорт

- Статус: принято
- Дата: 2026-11-05
- Затрагивает: `docs/architecture.md` §4.3, §6.1–6.4, §9, §10, §11, §16; код `backend/app/{models,repositories,services,api/v1/admin}`, `frontend/src/features/admin*`

## Контекст

Этап 9 строит админку поверх механизмов этапов 6–8 (БЗ в БД по [ADR 0006](0006-client-api.md), auth/RBAC по [ADR 0009](0009-auth-tokens-guest-sessions.md)). §10 и §11 описывают админ-эндпоинты и страницы, но не отвечают на шесть вопросов: откуда публикация берёт golden cases (знания — уже в БД, а эталоны лежат в `knowledge/golden/*.yaml`); как именно «Перегенерировать» пишет в черновик; что возвращает `POST /admin/kb/validate`; как устроен `POST /admin/rules/{code}/test`; куда пишется история импорта каталога (`catalog_imports` есть только в §9); каким должен быть экспорт, чтобы работал round-trip «seed → админка → export → seed».

## Решения

1. **`catalog_imports`.** Таблица и модель `CatalogImportRow` создаются миграцией: `id uuid, filename, status (completed|failed), dry_run bool, report jsonb, created_by uuid→users SET NULL, created_at`. Каждый вызов `POST /admin/catalog/import` (включая dry-run) пишет строку: отчёт содержит created/updated/unchanged, отклонённые строки с номерами, предупреждения, статусы, ревизию каталога. Это журнал аудита, влияния на логику нет.

2. **Golden cases живут в БД.** Список кейсов хранится в `reference_tables` под именем `golden` (JSON-список, формат `expert/golden.py` без изменений). `import_files` (seed) заливает `knowledge/golden/*.yaml` туда; публикация и `POST /admin/kb/validate` читают эталоны из БД на текущем каталоге (`SnapshotCache.catalog`); экспорт выгружает обратно в `golden/cases.yaml` (в репозитории golden и так один файл). В `kb_snapshots` кейсы **не входят**: на вывод они не влияют, снимок — это правила + справочники + анкета. Публикация через API не зависит от диска. Расширяет список имён `reference_tables` из [ADR 0006](0006-client-api.md) п.1.

3. **`POST /admin/kb/validate` — stateless.** Сервис собирает черновик (все enabled-правила + справочники + анкета из рабочей копии), компилирует, гоняет статические проверки §6.2 и golden cases, возвращает отчёт `{errors, warnings, golden: {passed, failed}, checksum, matches_latest}` и ничего не записывает. Хранимого состояния `Validated` нет: диаграмма §6.1 читается как «последний прогон чистый». `POST /admin/kb/publish` повторяет те же проверки и при любой ошибке бросает `KnowledgeValidationError` (409 `kb-invalid`, в `detail`/`findings` — список ошибок) — это критерий готовности этапа. Общая часть сборки черновика и проверок выносится в `knowledge_store`, validate и publish её делят.

4. **`POST /admin/rules/{code}/test` — изолированный прямой вывод.** Тело: `{facts: {path: value | {value, cf}}}` — входные факты (по умолчанию cf=1.0). Сервис берёт черновик правила, компилирует его единственным в наборе (`compile_rules([rule])`), запускает `run_forward` на рабочей памяти из заданных фактов и возвращает `{matched, premise_cf, actions: [{action, message…}], facts_after: [{path, value, cf}], failures}` (failures — ошибки вычисления `rule_failed`). Так тестируются kind inference/filter/compat/score/validate. Для `kind: goal` изолированный прогон неприменим (подцели требуют обратного вывода со сборкой) — ответ 422 с пояснением; goal-правила проверяются через «Потянет ли?» на сборке. Тестируется только сохранённый черновик; несохранённое правило сначала сохраняется.

5. **Регенерация в черновик.** `POST /admin/reference/regenerate?dry_run=` читает справочники из `reference_tables` (рабочая копия, не диск), прогоняет чистый генератор `expert/generation`, считает diff по кодам с правилами `origin: generated`: created / updated (body отличается) / removed (вышло из справочников). Сравнение идёт только с `origin: generated`; правила с `origin: manual` и `source` из `tables/…` (override, см. §6.4) не трогаются и перечисляются в отчёте отдельно. `dry_run=true` возвращает diff-отчёт без записи; `dry_run=false` применяет: новые — revision 1, изменённые — новая ревизия, removed — `enabled=false`; всё с `change_type: "regenerate"` (для removed — `"retire"`) и автором. Справочник→черновик→проверка→публикация (§16) не меняется.

6. **Экспорт БЗ — zip с деревом как в `knowledge/`.** `GET /admin/kb/export` отдаёт `application/zip`: `rules/manual/<PREFIX>.yaml` (префикс кода, `dump_rules`), `rules/generated/<GEN-XXX>.yaml` (маппинг `GENERATED_FILES`), `tables/<name>.yaml` (обёртка `{name: data}` для всех кроме `form_factors`, который пишется целиком — зеркально `load_tables`), `questionnaire.yaml`, `golden/cases.yaml`. Критерий стабильности — семантический round-trip: после замены файлов `knowledge/` содержимым архива повторный `scripts.seed` даёт `created=0, updated=0` и не создаёт новый снимок (побайтовое совпадение с ручными комментариями в файлах не гарантируем). `GET /admin/catalog/export` — zip с `<category>.csv` в формате §12 (колонки `csv_columns`, списки через `|`, bool `true/false`, `price_rub` целыми рублями).

7. **CRUD без физического удаления.** Правило «удаляется» через `POST /admin/rules/{code}/retire` (`enabled=false`, `change_type: "retire"`; коды не переиспользуются — PK это гарантирует, строку удалять нельзя: история `rule_revisions` ссылается каскадно). Компонент «удаляется» через статус `inactive` (§17). Полная замена правила — `PUT /admin/rules/{code}` (новая ревизия, `change_type: "update"`); ручная правка сгенерированного правила переводит его в `origin: manual` (override) с предупреждением в ответе. Справочники редактируются целиком (`PUT /admin/reference/{name}`, валидация Pydantic-схемами ядра: `KnowledgeTables` / `Questionnaire` / список `GoldenCase`); построчной истории правок справочников нет — опубликованные версии фиксируются снимками. `change_type` правил: `seed, import, create, update, retire, regenerate`.

8. **Каталог из админки.** `POST /admin/components` / `PUT /admin/components/{id}` принимают JSON фрейма категории (валидация Pydantic union, `source=manual`); статус пересчитывается `compute_status` со `known_slot_values` **последнего опубликованного снимка** (`SnapshotCache.knowledge`; если снимка нет — `known=None`, §17), ревизия каталога растёт при изменениях. `PATCH /admin/components/{id}` — служебные поля (`in_stock`, `status` для снятия/возврата к продаже; `inactive` не перезаписывается пересчётом). Импорт: multipart CSV + `?category=&dry_run=` (категория из query, не из имени файла), лимит 2 МБ, разбор переиспользует `services/catalog_csv`.

9. **RBAC-матрица.** `require_roles` из этапа 8, роль из `OwnerContext.user.role`:

   | Эндпоинты | catalog_admin | knowledge_engineer | superadmin |
   |---|---|---|---|
   | `/admin/components*`, `/admin/catalog/import`, `/admin/catalog/export` | ✅ | — | ✅ |
   | `/admin/catalog/issues` | ✅ | ✅ (чтение) | ✅ |
   | `/admin/rules*`, `/admin/reference*`, `/admin/kb/*` | — | ✅ | ✅ |
   | `/admin/users*` | — | — | ✅ |

   Смена роли/блокировка: 409, если цель — сам себя; 409, если блокировка или понижение последнего активного `superadmin`. Блокировка отзывает все refresh-токены пользователя.

10. **Frontend.** Маршруты под `AdminLayout` с guard `RequireRole` (роль из `useMe`): `/admin` (редирект на первый доступный раздел по роли), `/admin/catalog` (+ `/new`, `/:id`, `/import`, `/issues`), `/admin/kb` (правила: список, редактор, тест; `/validate`, `/snapshots`, `/reference`), `/admin/users`. Редактор правила: вкладки «Конструктор» (дерево all/any/not, листы `{fact, op, value|ref}` и `{expr}`, факты из нового `GET /admin/kb/vocabulary` — публичная `all_specs()` в `expert/vocabulary.py`) и «YAML» на Monaco; зависимости `@monaco-editor/react` + `monaco-editor`, загрузка монако из node_modules (без CDN). Справочники на этапе 9 — YAML-режим (Monaco + серверная валидация схемой); табличные формы игр/приложений — при необходимости позже.

## Альтернативы

- **Golden cases в отдельной таблице** `golden_cases`: чище семантически, но отдельная миграция, репозиторий и CRUD ради одного JSON-списка, который на этапе 9 всё равно редактируется только экспортом/seed. Выбрано расширение `reference_tables` — ноль схемных изменений, единый механизм экспорта.
- **Публикация читает `knowledge/golden/` с диска** (как seed): серверу пришлось бы знать путь к репозиторию, публикация из админки зависела бы от рабочей копии на диске — противоречит ADR 0006 («главная копия — в БД»).
- **Хранимый статус `Validated`**: требует колонки/таблицы состояния и инвалидации при каждой правке; stateless-прогон дешевле и не может «устареть».
- **XLSX-импорт** (упомянут в §4.3/§11): отложен — CSV покрывает сценарий «выгрузил → поправил в Excel → загрузил» (Excel сохраняет в CSV), новая зависимость (openpyxl) не нужна. Возможен позже без изменения контракта.
- **Физическое удаление правил**: сломало бы историю (FK `rule_revisions` ON DELETE CASCADE) и проверку «коды не переиспользуются» пришлось бы дублировать в реестре.

## Последствия

- Backend: одна миграция (`catalog_imports`), сервисы `catalog_admin` / `knowledge_admin` / `users_admin`, пакет роутеров `api/v1/admin/`, расширение `knowledge_store` (общий сбор черновика и проверок, golden из БД), writer'ы в `knowledge_files`, `vocabulary.all_specs()`.
- Frontend: зависимости `@monaco-editor/react`, `monaco-editor`; фичи `admin*`.
- Тесты: round-trip «export → повторный seed = unchanged» — обязательный; публикация блокируется при ошибке валидации и при падении golden — интеграционные; матрица RBAC (403 для чужих ролей) — параметризованный тест.
- Вики: `docs/wiki/07-updates.md` (§7.2–7.6 снять пометки «появится на этапе 9»), при необходимости `02-knowledge.md` — в той же задаче реализации.
