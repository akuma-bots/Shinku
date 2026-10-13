import json
from pathlib import Path

from cogs.tutorial import TUTORIAIS


def test_tutorial_catalog_has_core_systems():
    assert len(TUTORIAIS) <= 25
    assert {"missoes", "guerras", "moderacao", "roblox", "avisos"}.issubset(TUTORIAIS)


def test_release_manifest_is_valid():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "novidades.json").read_text(encoding="utf-8"))
    assert data["release_id"]
    assert data["titulo"]
    assert data["mensagem"]
