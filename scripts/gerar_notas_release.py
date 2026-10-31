#!/usr/bin/env python3
"""Gera notas públicas somente para alterações funcionais relevantes da NÊMESIS."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUSO = ZoneInfo("America/Sao_Paulo")
MANIFEST = ROOT / "config" / "novidades.json"
IGNORAR = (
    ".github/",
    "tests/",
    "docs/",
    "scripts/",
    "README",
    "LICENSE",
    "CHANGELOG",
)
AREAS = {
    "cogs/": "sistemas e comandos",
    "utils/": "mecanismos internos e infraestrutura",
    "config/": "configurações dos sistemas",
    "bot.py": "núcleo e inicialização do bot",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def arquivos_alterados(before: str, after: str) -> list[tuple[str, str]]:
    if not before or set(before) == {"0"}:
        raw = git("show", "--format=", "--name-status", after)
    else:
        raw = git("diff", "--name-status", before, after)
    itens = []
    for linha in raw.splitlines():
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        status = partes[0]
        caminho = partes[-1]
        if caminho == "config/novidades.json" or caminho.startswith(IGNORAR):
            continue
        if not (caminho.startswith(("cogs/", "utils/", "config/")) or caminho == "bot.py"):
            continue
        if caminho.endswith((".pyc", ".log")):
            continue
        itens.append((status, caminho))
    return itens


def assunto_commits(before: str, after: str) -> list[str]:
    try:
        if not before or set(before) == {"0"}:
            saida = git("log", "-1", "--format=%s", after)
        else:
            saida = git("log", "--format=%s", f"{before}..{after}")
        return [linha.strip() for linha in saida.splitlines() if linha.strip()]
    except subprocess.CalledProcessError:
        return []


def gerar(before: str, after: str) -> dict | None:
    alteracoes = arquivos_alterados(before, after)
    if not alteracoes:
        return None

    assuntos = assunto_commits(before, after)
    textos = " ".join(assuntos).lower()
    status = [s for s, _ in alteracoes]
    if any(s.startswith("D") for s in status):
        tipo = "Melhorias e alterações"
    elif re.search(r"\b(fix|bug|corrig|hotfix|patch)\b", textos):
        tipo = "Correções"
    elif any(s.startswith("A") for s in status):
        tipo = "Sistemas novos e melhorias"
    else:
        tipo = "Melhorias dos sistemas"

    areas = []
    for prefixo, nome in AREAS.items():
        if any(caminho.startswith(prefixo) if prefixo.endswith("/") else caminho == prefixo
               for _, caminho in alteracoes):
            areas.append(nome)

    # Os assuntos dos commits são a fonte principal; os caminhos apenas contextualizam.
    rotulos = {
        "missoes": "Missões", "revisoes": "Análise de provas",
        "ranking": "Rankings", "parcerias": "Parcerias",
        "tickets": "Atendimento", "automod": "Moderação automática",
        "moderacao": "Moderação", "eventos": "Eventos",
        "perfil": "Perfis", "novidades": "Central de atualizações",
        "desafios": "Desafios", "guerras": "Guerras",
    }
    # Notas públicas nunca devem reproduzir assuntos de commits em inglês.
    # Traduções explícitas preservam detalhes; assuntos desconhecidos recebem
    # uma descrição funcional em português baseada nas áreas realmente alteradas.
    traducoes = {
        "fix multi-step form continuation interaction listener":
            "Formulários: corrigida a continuidade entre as etapas de inscrição.",
        "improve update announcements with bot branding":
            "Central de atualizações: identidade visual do bot aplicada aos comunicados.",
        "write current update notes in brazilian portuguese":
            "Central de atualizações: notas padronizadas em português do Brasil.",
        "fix application delivery channel and migrate staff form questions":
            "Formulários: corrigido o canal de recebimento e ampliado o questionário de recrutamento.",
        "add regression tests for staff questions and submission channel":
            "Formulários: adicionados testes para as perguntas e o canal de recebimento.",
    }
    unicos = list(dict.fromkeys(assuntos))
    linhas = []
    for assunto in unicos[:6]:
        limpo = traducoes.get(assunto.casefold().strip())
        if limpo:
            linhas.append(f"• {limpo[:220]}")
    if not linhas:
        descricao_areas = ", ".join(areas) if areas else "sistemas internos"
        linhas.append(f"• Foram aplicadas melhorias em {descricao_areas}.")
    mensagem = (
        "A NÊMESIS recebeu uma nova atualização nos sistemas do bot.\n\n"
        + "\n".join(linhas)
    )
    if areas:
        mensagem += "\n\n**Áreas envolvidas:** " + ", ".join(areas) + "."
    mensagem += (
        "\n\nAs alterações foram integradas ao repositório principal. "
        "A disponibilidade das funções depende da conclusão do deploy do bot."
    )

    titulo = linhas[0].removeprefix("• ") if len(linhas) == 1 else "Novidades e melhorias nos sistemas"
    agora = datetime.now(FUSO)
    return {
        "release_id": agora.strftime("%Y%m%d-%H%M%S"),
        "tipo": tipo,
        "titulo": titulo[:180] or "Atualização da NÊMESIS",
        "mensagem": mensagem[:3400],
        "data_atualizacao": agora.strftime("%d/%m/%Y"),
        "hora_atualizacao": agora.strftime("%H:%M"),
        "fuso_horario": "Horário de Brasília (BRT)",
        "gerado_em": agora.isoformat(),
    }


def main() -> int:
    before = os.environ.get("BEFORE_SHA", "").strip()
    after = os.environ.get("AFTER_SHA", "").strip() or git("rev-parse", "HEAD")
    release = gerar(before, after)
    if release is None:
        print("Nenhuma alteração funcional elegível; manifesto preservado.")
        return 0

    anterior = {}
    if MANIFEST.exists():
        try:
            anterior = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            anterior = {}
    if anterior.get("release_id") == release["release_id"]:
        print("Este commit já possui manifesto; nenhuma alteração necessária.")
        return 0

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(release, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Notas geradas: {release['data_atualizacao']} às {release['hora_atualizacao']} — {release['titulo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
