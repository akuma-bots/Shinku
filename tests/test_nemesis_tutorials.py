import json
from pathlib import Path

from cogs.tutorial import TUTORIAIS, Tutorial, CANAL_TUTORIAIS_ID
from utils.guia_servidores import CANAIS_GUIA_SERVIDORES


def test_tutorial_catalog_has_core_systems():
    assert len(TUTORIAIS) <= 25
    assert {"missoes", "guerras", "moderacao", "roblox", "avisos"}.issubset(TUTORIAIS)


def test_release_manifest_is_valid():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "novidades.json").read_text(encoding="utf-8"))
    assert data["release_id"]
    assert data["titulo"]
    assert data["mensagem"]


def test_tutorial_is_channel_panel_not_slash_command():
    assert CANAL_TUTORIAIS_ID == 1563995880833421512
    assert not hasattr(Tutorial, "tutorial")
    assert len(TUTORIAIS) <= 25


def test_welcome_guide_links_only_known_nemesis_channels():
    ids = [canal_id for _, canal_id, _ in CANAIS_GUIA_SERVIDORES]
    assert len(ids) == len(set(ids))
    assert len(CANAIS_GUIA_SERVIDORES) <= 25
    assert all(canal_id > 0 for canal_id in ids)
