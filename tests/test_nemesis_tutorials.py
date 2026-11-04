import json
from pathlib import Path

from cogs.tutorial import TUTORIAIS, Tutorial, CANAL_TUTORIAIS_ID, _embed_indice
from utils.guia_servidores import CANAIS_GUIA_SERVIDORES, CARGO_VISITANTES_ID, TAG_ORG_NEMESIS


def test_tutorial_catalog_has_core_systems():
    assert len(TUTORIAIS) <= 25
    assert {"missoes", "guerras", "moderacao", "roblox", "avisos", "academia"}.issubset(TUTORIAIS)


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
    ids = [canal_id for _, canal_id, *_ in CANAIS_GUIA_SERVIDORES]
    assert len(ids) == len(set(ids))
    assert len(CANAIS_GUIA_SERVIDORES) <= 25
    assert all(canal_id > 0 for canal_id in ids)


def test_start_tutorial_explains_visitor_role_and_org_tag():
    texto = " ".join(TUTORIAIS["inicio"]["passos"])
    assert "Visitantes" in texto
    assert "NΞM" in texto
    assert CARGO_VISITANTES_ID == 1563995879990624371
    assert TAG_ORG_NEMESIS == "NΞM"


def test_visitor_role_is_part_of_automatic_entry_roles():
    from cogs.autocargo import CargoAutomatico

    assert CARGO_VISITANTES_ID in CargoAutomatico.CARGOS_ENTRADA


def test_tutorial_index_is_short_and_keeps_teaching_content_behind_selector():
    embed = _embed_indice()
    assert len(embed.fields) == 1
    assert "seletor" in embed.description.lower()
    assert "Começando na NÊMESIS" not in embed.description
    assert all(item["descricao"] not in embed.description for item in TUTORIAIS.values())
