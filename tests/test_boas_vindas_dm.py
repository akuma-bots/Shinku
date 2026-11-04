import json
from pathlib import Path

from cogs.boas_vindas_dm import carregar_catalogo_codigos, TAG_GANGUE, CONVITE_NEMESIS, BoasVindasDM, CARGO_VISITANTES_ID
from utils.guia_servidores import TAG_ORG_NEMESIS, NOME_CARGO_VISITANTES, GuiaServidoresView, CANAIS_GUIA_SERVIDORES


def test_welcome_codes_catalog_has_all_games_and_requirements():
    catalogo = carregar_catalogo_codigos()
    assert {"shigaku", "gakuran", "fistborn"}.issubset(catalogo["jogos"])
    for jogo in ("shigaku", "gakuran", "fistborn"):
        dados = catalogo["jogos"][jogo]
        assert dados["codigos"]
        assert dados["requisitos"]
        assert dados["fonte"].startswith("https://")


def test_welcome_uses_nemesis_tag_and_invite():
    assert TAG_GANGUE == "NΞM"
    assert TAG_ORG_NEMESIS == "NΞM"
    assert CONVITE_NEMESIS.startswith("https://discord.gg/")


def test_welcome_uses_official_visitor_role():
    assert CARGO_VISITANTES_ID == 1563995879990624371
    assert NOME_CARGO_VISITANTES == "Visitantes"


def test_codes_catalog_is_valid_json():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "codigos_jogos.json").read_text(encoding="utf-8"))
    assert len(data["atualizado_em"]) == 10
    assert data["atualizado_em"][4] == "-" and data["atualizado_em"][7] == "-"
    if "semana_referente" in data:
        semana = data["semana_referente"]
        assert semana["inicio"] <= semana["fim"]
        assert semana["fuso"]


def test_weekly_catalog_period_is_monday_through_sunday():
    from datetime import date
    from scripts.atualizar_codigos_jogos import calcular_semana

    inicio, fim = calcular_semana(date(2026, 10, 15))
    assert inicio == date(2026, 10, 12)
    assert fim == date(2026, 10, 18)
    assert fim.weekday() == 6
    assert (fim - inicio).days == 6


def test_interactive_codes_slash_command_is_registered():
    assert BoasVindasDM.consultar_codigos.name == "codigos"


def test_entry_navigation_uses_one_select_instead_of_link_buttons():
    import discord

    view = GuiaServidoresView()
    assert len(view.children) == 1
    seletor = view.children[0]
    assert isinstance(seletor, discord.ui.Select)
    assert len(seletor.options) == len(CANAIS_GUIA_SERVIDORES) == 12
    assert seletor.placeholder == "◈ Escolha uma área para conhecer"
