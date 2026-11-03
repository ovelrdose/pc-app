"""PDF-спецификация сборки: HTML-шаблон Jinja2 → WeasyPrint (архитектура §10)."""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.expert.frames import FRAMES_BY_CATEGORY
from app.schemas.consultations import BuildDetail

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
TIER_TITLES = {"economy": "Эконом", "optimum": "Оптимум", "maximum": "Максимум"}
PRESET_TITLES = {"medium": "средние", "high": "высокие", "ultra": "ультра"}

_environment = Environment(
    loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"])
)


def rub(kop: int) -> str:
    """Копейки → «125 990 ₽» (неразрывные пробелы)."""
    rubles = kop // 100
    return f"{rubles:,}".replace(",", " ") + " ₽"


def render_html(build: BuildDetail, reasoning: list[str]) -> str:
    """HTML спецификации."""
    categories = {
        c: str(frame.model_config.get("title", c.value)) for c, frame in FRAMES_BY_CATEGORY.items()
    }
    context: dict[str, Any] = {
        "build": build,
        "reasoning": reasoning[:12],
        "categories": categories,
        "presets": PRESET_TITLES,
        "tier_title": TIER_TITLES.get(build.tier.value, build.tier.value),
        "rub": rub,
    }
    return _environment.get_template("build.html").render(context)


def render_pdf(build: BuildDetail, reasoning: list[str]) -> bytes:
    """PDF спецификации (WeasyPrint импортируется лениво: ему нужны системные Pango/HarfBuzz)."""
    from weasyprint import HTML

    pdf: bytes = HTML(string=render_html(build, reasoning)).write_pdf()
    return pdf
