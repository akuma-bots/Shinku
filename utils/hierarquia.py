"""Sincronização automática das patentes oficiais da NÊMESIS por XP."""
import logging

import discord

from utils.perfis import get_patentes, definir_patente

log = logging.getLogger(__name__)

# Configuração oficial fixa: (nome, XP mínimo, ID do cargo).
# Os IDs são os cargos fornecidos pela liderança da NÊMESIS.
GUILD_NEMESIS_ID = 1543381737961160910
PATENTES_NEMESIS = (
    ("Lutador", 0, 1561705759992057877),
    ("Subtenente", 750, 1559561987296469024),
    ("Tenente", 2000, 1558909073758625973),
    ("Executor", 4000, 1561715055077097603),
    ("Especialista", 7000, 1561715502508933150),
    ("Elite", 11000, 1561703280227262474),
    ("Veterano", 16000, 1561703510406602872),
    ("Treinador", 22000, 1561706517819039845),
    ("Comandante", 30000, 1561715380672798730),
    ("Vice Capitão", 40000, 1560370097577791569),
    ("Capitão", 52000, 1558909311315607723),
    ("Capitão Geral", 68000, 1561706215195541605),
)


async def sincronizar_cargo_patente(
    guild: discord.Guild,
    membro: discord.Member,
    xp: int,
    *,
    atualizar_perfil: bool = True,
) -> str | None:
    """Entrega a patente mais alta atingida e remove as patentes anteriores.

    A sincronização usa os IDs oficiais e os limites de XP definidos no código,
    sem exigir que /hierarquia-inicializar tenha sido executado. Outros cargos
    do membro (staff, identidade, notificações etc.) são preservados.
    """
    if guild.id != GUILD_NEMESIS_ID:
        return None

    xp_atual = max(0, int(xp or 0))
    elegiveis = [
        (nome, xp_minimo, cargo_id)
        for nome, xp_minimo, cargo_id in PATENTES_NEMESIS
        if xp_minimo <= xp_atual
    ]
    if not elegiveis:
        return None

    nome_patente, _, cargo_alvo_id = max(elegiveis, key=lambda item: item[1])
    cargo_alvo = guild.get_role(cargo_alvo_id)
    if cargo_alvo is None:
        log.warning(
            "Cargo oficial da patente %s (%s) não existe no servidor %s.",
            nome_patente, cargo_alvo_id, guild.id,
        )
        return nome_patente

    me = guild.me
    if me is None or me.top_role <= cargo_alvo:
        log.warning(
            "O cargo do bot precisa ficar acima da patente %s (%s).",
            cargo_alvo.name, cargo_alvo.id,
        )
        return nome_patente

    # Também reconhece IDs antigos que estejam salvos na configuração, para
    # que a troca para os cargos oficiais limpe a patente anterior.
    ids_patentes = {cargo_id for _, _, cargo_id in PATENTES_NEMESIS}
    try:
        configuradas = await get_patentes(guild.id)
        for item in configuradas:
            cargo_id = item.get("cargo_id")
            if cargo_id:
                try:
                    ids_patentes.add(int(cargo_id))
                except (TypeError, ValueError):
                    log.warning("ID de patente inválido na configuração: %r", cargo_id)
    except Exception:
        log.exception("Não foi possível ler a configuração antiga de patentes.")

    remover = [
        cargo for cargo in membro.roles
        if cargo.id in ids_patentes and cargo.id != cargo_alvo.id
    ]
    adicionar = cargo_alvo not in membro.roles

    try:
        # Primeiro adiciona a nova patente. Se o Discord recusar, a antiga
        # permanece no membro, evitando deixá-lo sem cargo competitivo.
        if adicionar:
            await membro.add_roles(
                cargo_alvo,
                reason=f"Progressão automática por XP da NÊMESIS ({xp_atual} XP)",
            )
    except (discord.Forbidden, discord.HTTPException):
        log.exception(
            "Não foi possível atribuir a patente %s ao membro %s.",
            nome_patente, membro.id,
        )
        return nome_patente

    if remover:
        try:
            await membro.remove_roles(
                *remover,
                reason=f"Substituição automática de patente por XP da NÊMESIS ({xp_atual} XP)",
            )
        except (discord.Forbidden, discord.HTTPException):
            log.exception(
                "A patente %s foi atribuída, mas não foi possível remover todas as patentes antigas de %s.",
                nome_patente, membro.id,
            )

    if atualizar_perfil:
        try:
            await definir_patente(guild.id, membro.id, nome_patente)
        except Exception:
            log.exception("Cargo sincronizado, mas falhou ao salvar patente do perfil.")

    return nome_patente
