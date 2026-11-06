"""Админка базы знаний: CRUD правил, изолированный тест правила, справочники, регенерация."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.expert.golden import cases_to_json
from app.models import RuleRevisionRow, UserRow
from app.services.knowledge_files import load_golden
from scripts.seed import KNOWLEDGE_DIR
from tests.integration.admin.conftest import auth

pytestmark = pytest.mark.integration

NEW_RULE = {
    "code": "REQ-900",
    "name": "Тестовое требование админки: нужен Wi-Fi",
    "kind": "inference",
    "group": "requirements",
    "priority": 100,
    "cf": 0.6,
    "when": {"fact": "user.wifi", "op": "eq", "value": True},
    "then": [{"action": "assert", "fact": "req.wifi", "value": True}],
    "explain": "Тестовое правило этапа 9: клиенту нужен Wi-Fi.",
}


async def test_list_rules_with_filters(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.get(
        "/api/v1/admin/rules", params={"group": "budget", "limit": 10}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    assert all(item["group"] == "budget" for item in body["items"])

    generated = await client.get(
        "/api/v1/admin/rules", params={"origin": "generated", "limit": 5}, headers=headers
    )
    assert generated.status_code == 200
    assert all(item["origin"] == "generated" for item in generated.json()["items"])

    search = await client.get("/api/v1/admin/rules", params={"q": "REQ-024"}, headers=headers)
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["code"] == "REQ-024"


async def test_rule_detail_with_revision_history(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.get("/api/v1/admin/rules/REQ-024", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["rule"]["code"] == "REQ-024"
    assert body["rule"]["body"]["when"]
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["change_type"] == "seed"

    missing = await client.get("/api/v1/admin/rules/REQ-999", headers=headers)
    assert missing.status_code == 404


async def test_create_rule_uniqueness_and_prefixes(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.post("/api/v1/admin/rules", json=NEW_RULE, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["revision"] == 1
    assert body["origin"] == "manual"
    assert body["updated_by"] is not None

    # коды не переиспользуются
    again = await client.post("/api/v1/admin/rules", json=NEW_RULE, headers=headers)
    assert again.status_code == 409

    # неизвестный префикс
    bad_prefix = {**NEW_RULE, "code": "XXX-901"}
    response = await client.post("/api/v1/admin/rules", json=bad_prefix, headers=headers)
    assert response.status_code == 422
    assert response.json()["type"].endswith("/rule-code-invalid")

    # коды GEN-* создаёт только генератор
    gen_code = {
        **NEW_RULE,
        "code": "GEN-SKT-TEST-1",
        "origin": "generated",
        "source": "tables/sockets.yaml#test",
    }
    response = await client.post("/api/v1/admin/rules", json=gen_code, headers=headers)
    assert response.status_code == 422


async def test_replace_rule_and_generated_override(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    changed = {**NEW_RULE, "cf": 0.8, "name": "Тестовое требование (правка)"}
    response = await client.put("/api/v1/admin/rules/REQ-900", json=changed, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 2
    assert body["cf"] == 0.8
    assert body["warning"] is None

    # код в теле должен совпадать с путём
    mismatch = await client.put(
        "/api/v1/admin/rules/REQ-900",
        json={**NEW_RULE, "code": "REQ-901"},
        headers=headers,
    )
    assert mismatch.status_code == 422

    # ручная правка сгенерированного правила — override с предупреждением
    generated = (
        await client.get(
            "/api/v1/admin/rules",
            params={"origin": "generated", "kind": "compat", "limit": 1},
            headers=headers,
        )
    ).json()["items"][0]
    overridden = {
        **generated["body"],
        "name": f"{generated['name']} (правка инженера)",
    }
    response = await client.put(
        f"/api/v1/admin/rules/{generated['code']}", json=overridden, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["origin"] == "manual"
    assert "override" in body["warning"]


async def test_rule_isolated_forward_run(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.post(
        "/api/v1/admin/rules/REQ-900/test",
        json={"facts": {"user.wifi": True}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] is True
    assert body["premise_cf"] == 1.0
    assert body["failures"] == []
    assert body["actions"][0]["action"] == "assert"
    assert body["actions"][0]["fact"] == "req.wifi"
    facts = {fact["path"]: fact for fact in body["facts_after"]}
    assert facts["req.wifi"]["value"] is True
    assert facts["req.wifi"]["cf"] == pytest.approx(0.8)

    # cf посылки учитывается
    weighted = await client.post(
        "/api/v1/admin/rules/REQ-900/test",
        json={"facts": {"user.wifi": {"value": True, "cf": 0.5}}},
        headers=headers,
    )
    body = weighted.json()
    assert body["matched"] is True
    assert body["premise_cf"] == 0.5
    facts = {fact["path"]: fact for fact in body["facts_after"]}
    assert facts["req.wifi"]["cf"] == pytest.approx(0.4)

    # факт не задан — правило не сработало
    empty = await client.post(
        "/api/v1/admin/rules/REQ-900/test", json={"facts": {}}, headers=headers
    )
    body = empty.json()
    assert body["matched"] is False
    assert body["premise_cf"] is None
    assert body["actions"] == []

    # некорректный путь факта — 422
    bad = await client.post(
        "/api/v1/admin/rules/REQ-900/test",
        json={"facts": {"nope.path": True}},
        headers=headers,
    )
    assert bad.status_code == 422


async def test_goal_rule_test_is_not_supported(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    goal = (
        await client.get(
            "/api/v1/admin/rules", params={"kind": "goal", "limit": 1}, headers=headers
        )
    ).json()["items"][0]
    response = await client.post(
        f"/api/v1/admin/rules/{goal['code']}/test",
        json={"facts": {"build.ram.capacity_gb": 32}},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("/goal-rule-test-unsupported")


async def test_rule_test_expr_failure_is_reported_not_raised(
    client: httpx.AsyncClient, accounts: dict[str, UserRow]
) -> None:
    """Ошибки условия-формулы не роняют прогон 500: некомпилируемое условие — 409
    rule-broken, ошибка вычисления — 200 с matched=False и описанием в failures."""
    headers = auth(accounts["knowledge_engineer"])
    broken = await client.post(
        "/api/v1/admin/rules",
        json={**NEW_RULE, "code": "REQ-903", "when": {"expr": "unknown_fact + 1"}},
        headers=headers,
    )
    assert broken.status_code == 201, broken.text
    # правило с ошибкой типов в момент вычисления: число < строки
    runtime = await client.post(
        "/api/v1/admin/rules",
        json={
            **NEW_RULE,
            "code": "REQ-904",
            "when": {"expr": "user.budget < user.resolution"},
        },
        headers=headers,
    )
    assert runtime.status_code == 201, runtime.text
    try:
        response = await client.post(
            "/api/v1/admin/rules/REQ-903/test",
            json={"facts": {"user.wifi": True}},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["type"].endswith("/rule-broken")

        response = await client.post(
            "/api/v1/admin/rules/REQ-904/test",
            json={"facts": {"user.budget": 90000, "user.resolution": "1080p"}},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matched"] is False
        assert body["premise_cf"] is None
        assert body["actions"] == []
        assert len(body["failures"]) == 1
        assert "условие" in body["failures"][0]
    finally:
        for code in ("REQ-903", "REQ-904"):
            retired = await client.post(f"/api/v1/admin/rules/{code}/retire", headers=headers)
            assert retired.status_code == 200


async def test_retire_rule(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    response = await client.post("/api/v1/admin/rules/REQ-900/retire", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["body"]["enabled"] is False
    assert body["revision"] == 3

    # повторный вызов идемпотентен: ревизия не растёт
    again = await client.post("/api/v1/admin/rules/REQ-900/retire", headers=headers)
    assert again.json()["revision"] == 3

    async with app.state.database.session_factory() as session:
        history = await session.scalar(
            select(func.count()).where(
                RuleRevisionRow.rule_code == "REQ-900",
                RuleRevisionRow.change_type == "retire",
            )
        )
    assert history == 1


async def test_reference_read_and_replace(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    all_data = await client.get("/api/v1/admin/reference", headers=headers)
    assert all_data.status_code == 200
    names = set(all_data.json())
    assert {"sockets", "chipsets", "form_factors", "games", "applications"} <= names
    assert {"questionnaire", "golden"} <= names

    one = await client.get("/api/v1/admin/reference/sockets", headers=headers)
    assert one.status_code == 200
    assert isinstance(one.json()["data"], list)

    missing = await client.get("/api/v1/admin/reference/nope", headers=headers)
    assert missing.status_code == 404

    # битые данные отклоняются схемой ядра
    bad = await client.put("/api/v1/admin/reference/sockets", json=[{"id": "AM5"}], headers=headers)
    assert bad.status_code == 422
    assert bad.json()["type"].endswith("/reference-invalid")

    # golden: корректная замена и восстановление
    cases = load_golden(KNOWLEDGE_DIR / "golden")
    payload = cases_to_json(cases[:1])
    replaced = await client.put("/api/v1/admin/reference/golden", json=payload, headers=headers)
    assert replaced.status_code == 200
    restored = await client.put(
        "/api/v1/admin/reference/golden", json=cases_to_json(cases), headers=headers
    )
    assert restored.status_code == 200
    golden = await client.get("/api/v1/admin/reference/golden", headers=headers)
    assert len(golden.json()["data"]) == len(cases)


async def test_regenerate_dry_run_and_apply(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    headers = auth(accounts["knowledge_engineer"])
    clean = await client.post("/api/v1/admin/reference/regenerate?dry_run=true", headers=headers)
    assert clean.status_code == 200, clean.text
    body = clean.json()
    assert body["dry_run"] is True
    # после seed справочники и сгенерированные правила согласованы
    assert body["created"] == body["updated"] == body["removed"] == []
    # override с прошлого теста перечислен, но не тронут
    assert len(body["overrides"]) == 1

    # применение без изменений не пишет историю
    applied = await client.post("/api/v1/admin/reference/regenerate?dry_run=false", headers=headers)
    assert applied.status_code == 200
    assert applied.json()["created"] == []

    database = app.state.database
    async with database.session_factory() as session:
        regenerated = await session.scalar(
            select(func.count()).where(RuleRevisionRow.change_type == "regenerate")
        )
    assert regenerated == 0


async def test_regenerate_restores_modified_generated_rule(
    client: httpx.AsyncClient,
    accounts: dict[str, UserRow],
    app: FastAPI,
) -> None:
    """Регенерация приводит сгенерированные правила в соответствие справочникам."""
    headers = auth(accounts["knowledge_engineer"])
    database = app.state.database
    # согласованное сгенерированное правило (кроме override из теста выше)
    listing = (
        await client.get(
            "/api/v1/admin/rules",
            params={"origin": "generated", "kind": "score", "limit": 1},
            headers=headers,
        )
    ).json()
    code = listing["items"][0]["code"]
    retired = await client.post(f"/api/v1/admin/rules/{code}/retire", headers=headers)
    assert retired.status_code == 200

    preview = await client.post("/api/v1/admin/reference/regenerate?dry_run=true", headers=headers)
    assert preview.json()["updated"] == [code]

    applied = await client.post("/api/v1/admin/reference/regenerate?dry_run=false", headers=headers)
    assert applied.status_code == 200
    assert applied.json()["updated"] == [code]

    rule = await client.get(f"/api/v1/admin/rules/{code}", headers=headers)
    body = rule.json()
    assert body["rule"]["enabled"] is True
    assert body["rule"]["revision"] == 3
    change_types = [item["change_type"] for item in body["revisions"]]
    assert change_types == ["regenerate", "retire", "seed"]

    async with database.session_factory() as session:
        history = await session.scalar(
            select(func.count()).where(
                RuleRevisionRow.rule_code == code,
                RuleRevisionRow.change_type == "regenerate",
            )
        )
    assert history == 1
