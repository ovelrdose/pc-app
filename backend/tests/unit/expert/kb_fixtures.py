"""Маленькие справочники для unit-тестов генератора и анкеты."""

from typing import Any

from app.expert.tables import KnowledgeTables

PRESETS = {"medium": 100, "high": 80, "ultra": 60}
VRAM = {"medium": 6, "high": 8, "ultra": 10}


def tables_data() -> dict[str, Any]:
    return {
        "sockets": [
            {
                "id": "AM5",
                "vendor": "amd",
                "mem_types": ["DDR5"],
                "perspective": True,
                "release_year": 2022,
            },
            {
                "id": "AM4",
                "vendor": "amd",
                "mem_types": ["DDR4"],
                "perspective": False,
                "release_year": 2017,
            },
        ],
        "chipsets": [
            {
                "id": "B650",
                "socket": "AM5",
                "tier": "mainstream",
                "cpu_overclock": True,
                "gpu_pcie_gen": 4,
                "m2_pcie_gen": 4,
                "max_cpu_tdp_w": 170,
            },
            {
                "id": "A620",
                "socket": "AM5",
                "tier": "entry",
                "cpu_overclock": False,
                "gpu_pcie_gen": 4,
                "m2_pcie_gen": 4,
                "max_cpu_tdp_w": 120,
            },
            {
                "id": "X870E",
                "socket": "AM5",
                "tier": "enthusiast",
                "cpu_overclock": True,
                "gpu_pcie_gen": 5,
                "m2_pcie_gen": 5,
                "max_cpu_tdp_w": 230,
            },
            {
                "id": "B550",
                "socket": "AM4",
                "tier": "mainstream",
                "cpu_overclock": True,
                "gpu_pcie_gen": 4,
                "m2_pcie_gen": 4,
                "max_cpu_tdp_w": 142,
            },
        ],
        "form_factors": {
            "motherboard": [
                {"id": "Mini-ITX", "rank": 1, "width_mm": 170, "height_mm": 170},
                {"id": "Micro-ATX", "rank": 2, "width_mm": 244, "height_mm": 244},
                {"id": "ATX", "rank": 3, "width_mm": 305, "height_mm": 244},
            ],
            "psu": [
                {"id": "SFX", "fits_case_psu": ["SFX", "ATX"]},
                {"id": "ATX", "fits_case_psu": ["ATX"]},
            ],
            "case_sizes": [
                {"size": "mini", "max_board_rank": 2},
                {"size": "mid", "max_board_rank": 3},
            ],
        },
        "games": [
            {
                "id": "cs2",
                "title": "Counter-Strike 2",
                "kind": "esports",
                "rt_supported": False,
                "base_fps": {r: PRESETS for r in ("1080p", "1440p", "2160p")},
                "cpu_fps_cap": 400,
                "vram_need": {r: VRAM for r in ("1080p", "1440p", "2160p")},
                "ram_min_gb": 8,
            },
            {
                "id": "doom_dark_ages",
                "title": "Doom",
                "kind": "aaa",
                "rt_supported": True,
                "rt_required": True,
                "base_fps": {r: PRESETS for r in ("1080p", "1440p", "2160p")},
                "cpu_fps_cap": 200,
                "vram_need": {r: VRAM for r in ("1080p", "1440p", "2160p")},
                "ram_min_gb": 16,
            },
        ],
        "applications": [
            {
                "id": "blender",
                "title": "Blender",
                "scenario": "render_3d",
                "workload": "gpu",
                "task": "Рендер",
                "ref_minutes": 4.0,
                "basic": {"ram_min_gb": 16, "vram_min_gb": 8, "cpu_cores_min": 6, "min_index": 70},
                "pro": {"ram_min_gb": 64, "vram_min_gb": 16, "cpu_cores_min": 12, "min_index": 130},
            },
            {
                "id": "office",
                "title": "Office",
                "scenario": "office",
                "workload": "cpu_single",
                "task": "Таблица",
                "ref_minutes": 0.5,
                "basic": {"ram_min_gb": 8, "vram_min_gb": 0, "cpu_cores_min": 4, "min_index": 50},
                "pro": {"ram_min_gb": 16, "vram_min_gb": 0, "cpu_cores_min": 6, "min_index": 80},
            },
        ],
    }


def small_tables() -> KnowledgeTables:
    return KnowledgeTables.model_validate(tables_data())
