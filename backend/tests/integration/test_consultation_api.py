"""Сквозной сценарий клиента через API на реальном каталоге и опубликованной базе знаний."""

from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration

WALKTHROUGH = {
    "tasks": {"main": "aaa_gaming", "extra": ["video_editing"]},
    "budget": 170000,
    "monitor": "qhd_144",
    "games": ["cyberpunk_2077", "baldurs_gate_3"],
    "color": "white",
    "storage_gb": 1000,
    "archive": "no",
    "future_proof": "yes",
}


async def component_id(api: httpx.AsyncClient, sku: str) -> str:
    response = await api.get("/api/v1/components", params={"q": sku})
    [item] = [i for i in response.json()["items"] if i["sku"] == sku]
    return str(item["id"])


@pytest.fixture(scope="module")
async def consultation(api: httpx.AsyncClient) -> dict[str, Any]:
    created = await api.post("/api/v1/consultations", json={"answers": WALKTHROUGH})
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "created"
    run = await api.post(f"/api/v1/consultations/{created.json()['id']}/builds")
    assert run.status_code == 201, run.text
    body: dict[str, Any] = run.json()
    return body


def by_tier(consultation: dict[str, Any], tier: str) -> dict[str, Any]:
    build: dict[str, Any] = next(b for b in consultation["builds"] if b["tier"] == tier)
    return build


async def test_questionnaire_and_goals(api: httpx.AsyncClient) -> None:
    questionnaire = (await api.get("/api/v1/questionnaire")).json()
    assert questionnaire["kb_version"] == "v1"
    questions = {q["id"]: q for s in questionnaire["steps"] for q in s["questions"]}
    assert len(questions["games"]["options"]) == 50
    assert questions["rgb"]["allow_unknown"] is True
    assert questions["tasks"]["type"] == "tasks"
    assert questions["tasks"]["extra_title"] == "Чем ещё будете заниматься иногда?"
    goals = (await api.get("/api/v1/goals")).json()
    cyberpunk = next(g for g in goals if g["args"] == {"game": "cyberpunk_2077", "preset": "ultra"})
    assert cyberpunk["needs"] == ["resolution", "target_fps"]
    assert any(g["predicate"] == "ready_for_4k" for g in goals)


async def test_consultation_builds_three_tiers(
    api: httpx.AsyncClient, consultation: dict[str, Any]
) -> None:
    assert consultation["status"] == "completed"
    assert consultation["kb_version"] == "v1"
    assert consultation["profile"]["profile.main"] == "aaa_gaming"
    assert {b["tier"] for b in consultation["builds"]} == {"economy", "optimum", "maximum"}
    for build in consultation["builds"]:
        assert build["total_price_kop"] <= 170000 * 100
        assert sum(i["price_kop"] for i in build["items"]) == build["total_price_kop"]
    again = await api.get(f"/api/v1/consultations/{consultation['id']}")
    assert [b["id"] for b in again.json()["builds"]] == [b["id"] for b in consultation["builds"]]
    rerun = await api.post(f"/api/v1/consultations/{consultation['id']}/builds")
    assert rerun.status_code == 409


async def test_build_detail_and_performance(
    api: httpx.AsyncClient, consultation: dict[str, Any]
) -> None:
    build = by_tier(consultation, "maximum")
    detail = (await api.get(f"/api/v1/builds/{build['id']}")).json()
    assert detail["kb_version"] == "v1"
    games = {(g["game"], g["preset"]): g for g in detail["performance"]["games"]}
    assert games[("cyberpunk_2077", "high")]["fps"] >= 90
    assert games[("cyberpunk_2077", "high")]["resolution"] == "1440p"
    assert detail["performance"]["balance"]["limited_by"] == "gpu"
    assert {b["name"] for b in detail["performance"]["benchmarks"]} >= {"timespy"}
    assert any(p["rule_code"] == "BAL-017" for p in detail["preferences"])


async def test_explanation(api: httpx.AsyncClient, consultation: dict[str, Any]) -> None:
    build = by_tier(consultation, "optimum")
    explanation = (await api.get(f"/api/v1/builds/{build['id']}/explanation")).json()
    codes = [step["rule_code"] for step in explanation["reasoning"]]
    assert {"PRF-011", "REQ-008", "BUD-010"} <= set(codes)
    assert explanation["scenario_contributions"]["aaa_gaming"] > 0


async def test_why_not_and_alternatives(
    api: httpx.AsyncClient, consultation: dict[str, Any]
) -> None:
    build = by_tier(consultation, "maximum")
    rtx5060 = await component_id(api, "GPU-PALIT-RTX5060-DUAL")
    answer = (
        await api.get(f"/api/v1/builds/{build['id']}/why-not", params={"component_id": rtx5060})
    ).json()
    assert answer["verdict"] == "filtered"
    assert answer["reasons"][0]["rule_code"] == "FLT-003"
    alternatives = (
        await api.get(f"/api/v1/builds/{build['id']}/alternatives", params={"category": "ssd"})
    ).json()
    assert alternatives
    assert all(a["verdict"] in ("worse", "better", "over_budget") for a in alternatives)
    assert all(a["sku"] != "SSD-ADATA-LEGEND860-1TB" for a in alternatives)
    missing = await api.get(
        f"/api/v1/builds/{build['id']}/why-not",
        params={"component_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing.status_code == 404


async def test_hypothesis_asks_then_proves(
    api: httpx.AsyncClient, consultation: dict[str, Any]
) -> None:
    build = by_tier(consultation, "maximum")
    url = f"/api/v1/builds/{build['id']}/hypotheses"
    request = {"predicate": "runs_game", "args": {"game": "cyberpunk_2077", "preset": "ultra"}}
    asked = (await api.post(url, json=request)).json()
    assert asked["status"] == "unknown"
    assert [q["variable"] for q in asked["questions"]] == ["target_fps"]
    proved = (await api.post(url, json={**request, "bindings": {"target_fps": 60}})).json()
    assert proved["status"] == "proved"
    assert proved["tree"]["children"][0]["rule_code"] == "GEN-GAME-CYBERPUNK-2077-ULTRA"


async def test_modification_creates_child_build(
    api: httpx.AsyncClient, consultation: dict[str, Any]
) -> None:
    build = by_tier(consultation, "maximum")
    response = await api.post(
        f"/api/v1/builds/{build['id']}/modifications", json={"kind": "cheaper", "category": "gpu"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["build"]["parent_build_id"] == build["id"]
    gpu = next(c for c in body["changes"] if c["category"] == "gpu")
    assert gpu["delta_kop"] < 0
    assert body["fps_avg_after"] < body["fps_avg_before"]
    rejected = await api.post(
        f"/api/v1/builds/{build['id']}/modifications", json={"kind": "cheaper"}
    )
    assert rejected.status_code == 422
    assert rejected.json()["type"].endswith("/edit-rejected")


async def test_compare_patch_and_pdf(api: httpx.AsyncClient, consultation: dict[str, Any]) -> None:
    ids = [by_tier(consultation, t)["id"] for t in ("economy", "maximum")]
    compared = (await api.post("/api/v1/builds/compare", json={"build_ids": ids})).json()
    assert len(compared["builds"]) == 2
    gpu_row = next(r for r in compared["rows"] if r["category"] == "gpu")
    assert len(gpu_row["items"]) == 2
    patched = await api.patch(
        f"/api/v1/builds/{ids[1]}", json={"title": "Игровой ПК", "is_saved": True}
    )
    assert (patched.json()["title"], patched.json()["is_saved"]) == ("Игровой ПК", True)
    pdf = await api.get(f"/api/v1/builds/{ids[1]}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


async def test_infeasible_consultation(api: httpx.AsyncClient) -> None:
    answers = {
        "tasks": {"main": "esports"},
        "budget": 80000,
        "monitor": "fhd_240",
    }
    created = (await api.post("/api/v1/consultations", json={"answers": answers})).json()
    run = (await api.post(f"/api/v1/consultations/{created['id']}/builds")).json()
    assert run["status"] == "infeasible"
    assert run["builds"] == []
    assert run["infeasibility"]["min_budget_rub"] > 80000
    report = (await api.get(f"/api/v1/consultations/{created['id']}/infeasible")).json()
    assert any(b["fact"] == "req.ram_dual_channel" for b in report["blocking"])
    assert any("Full HD, 144–165 Гц" in r["title"] for r in report["relaxations"])
    compromise = report["compromise"]
    assert compromise["total_price_kop"] <= 80000 * 100
    assert compromise["answers"] == {}
    assert report["best_effort"] is None

    # «Подобрать с этими уступками» — новая консультация с изменёнными ответами
    accepted = (
        await api.post(
            "/api/v1/consultations",
            json={
                "answers": {**answers, **compromise["answers"]},
                "waived_requirements": compromise["waived"],
            },
        )
    ).json()
    run = (await api.post(f"/api/v1/consultations/{accepted['id']}/builds")).json()
    assert run["status"] == "completed"
    assert all(b["total_price_kop"] <= 90000 * 100 for b in run["builds"])


async def test_compromise_with_waived_requirement(api: httpx.AsyncClient) -> None:
    answers = {"tasks": {"main": "aaa_gaming"}, "budget": 80000, "monitor": "qhd_144"}
    created = (await api.post("/api/v1/consultations", json={"answers": answers})).json()
    run = (await api.post(f"/api/v1/consultations/{created['id']}/builds")).json()
    assert run["status"] == "infeasible"
    report = (await api.get(f"/api/v1/consultations/{created['id']}/infeasible")).json()
    compromise = report["compromise"]
    assert compromise["waived"] == ["req.cpu_single_min", "req.ram_dual_channel"]
    assert [c["title"].split()[0] for c in compromise["concessions"]] == [
        "SSD",
        "Процессор",
        "Одна",
    ]
    accepted = (
        await api.post(
            "/api/v1/consultations",
            json={
                "answers": {**answers, **compromise["answers"]},
                "waived_requirements": compromise["waived"],
            },
        )
    ).json()
    assert accepted["waived"] == [
        {
            "fact": "req.cpu_single_min",
            "title": "Процессор слабее рекомендованного",
        },
        {
            "fact": "req.ram_dual_channel",
            "title": "Одна планка памяти вместо двух — вторую можно докупить позже",
        },
    ]
    run = (await api.post(f"/api/v1/consultations/{accepted['id']}/builds")).json()
    assert run["status"] == "completed"
    assert "req.ram_dual_channel" not in run["profile"]
    # правка сборки помнит уступку: одна планка не отбрасывается фильтром
    build = by_tier(run, "maximum")
    ram = await component_id(api, "RAM-KINGSTON-BEAST-D4-1X16-3200")
    answer = (
        await api.get(f"/api/v1/builds/{build['id']}/why-not", params={"component_id": ram})
    ).json()
    assert answer["verdict"] != "filtered"


async def test_unknown_waiver_is_rejected(api: httpx.AsyncClient) -> None:
    response = await api.post(
        "/api/v1/consultations",
        json={
            "answers": {"tasks": {"main": "office"}, "budget": 60000},
            "waived_requirements": ["req.color"],
        },
    )
    assert response.status_code == 422
    assert "req.color" in response.json()["detail"]


async def test_owned_component(api: httpx.AsyncClient) -> None:
    gpu = await component_id(api, "GPU-SAPPHIRE-RX9070XT-PULSE")
    answers = {
        "tasks": {"main": "aaa_gaming"},
        "budget": 100000,
        "monitor": "qhd_144",
    }
    created = (
        await api.post(
            "/api/v1/consultations", json={"answers": answers, "owned_component_ids": [gpu]}
        )
    ).json()
    assert [(o["component_id"], o["category"]) for o in created["owned"]] == [(gpu, "gpu")]
    run = (await api.post(f"/api/v1/consultations/{created['id']}/builds")).json()
    assert run["owned"] == created["owned"]
    for build in run["builds"]:
        item = next(i for i in build["items"] if i["category"] == "gpu")
        assert (item["component_id"], item["owned"], item["price_kop"]) == (gpu, True, 0)


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ({"answers": {"budget": 10}}, "invalid-answers"),
        ({"answers": {"budget": 100000, "nope": 1}}, "invalid-answers"),
        (
            {
                "answers": {"budget": 100000, "tasks": {"main": "office"}},
                "owned_component_ids": ["00000000-0000-0000-0000-000000000000"],
            },
            "invalid-consultation",
        ),
    ],
)
async def test_invalid_input(api: httpx.AsyncClient, payload: dict[str, Any], kind: str) -> None:
    response = await api.post("/api/v1/consultations", json=payload)
    assert response.status_code == 422
    assert response.json()["type"].endswith(kind)


async def test_not_found(api: httpx.AsyncClient) -> None:
    zero = "00000000-0000-0000-0000-000000000000"
    assert (await api.get(f"/api/v1/builds/{zero}")).status_code == 404
    assert (await api.get(f"/api/v1/consultations/{zero}")).status_code == 404
