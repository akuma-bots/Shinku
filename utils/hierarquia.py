"""Sincronização segura dos cargos competitivos da NÊMESIS."""
import logging

import discord

from utils.perfis import get_patentes, definir_patente

log = logging.getLogger(__name__)


async def sincronizar_cargo_patente(
    guild: discord.Guild,
    membro: discord.Member,
    xp: int,
    *,
    atualizar_perfil: bool = True,
) -> str | None:
    """Aplica somente a patente mais alta atingida e remove outras patentes configuradas.

    Cargos fora da lista de patentes (staff, identidade, notificações etc.) são preservados.
    """
    patentes = await get_patentes(guild.id)
    if not patentes:
        return None

    elegiveis = [
        patente for patente in patentes
        if int(patente.get("xp_minimo", 0) or 0) <= max(0, int(xp or 0))
    ]
    if not elegiveis:
        return None

    patente = max(elegiveis, key=lambda item: int(item.get("xp_minimo", 0) or 0))
    cargo_id = patente.get("cargo_id")
    cargo_alvo = guild.get_role(int(cargo_id)) if cargo_id else None

    ids_patentes = {
        int(item["cargo_id"])
        for item in patentes
        if item.get("cargo_id") and guild.get_role(int(item["cargo_id"]))
    }
    if cargo_alvo is None:
        log.warning(
            "Patente %s sem cargo válido no servidor %s.",
            patente.get("nome"), guild.id,
        )
        return str(patente.get("nome"))

    me = guild.me
    if me is None or me.top_role <= cargo_alvo:
        log.warning(
            "Hierarquia do bot não permite gerenciar o cargo de patente %s (%s).",
            cargo_alvo.name, cargo_alvo.id,
        )
        return str(patente.get("nome"))

    remover = [
        cargo for cargo in membro.roles
        if cargo.id in ids_patentes and cargo.id != cargo_alvo.id
    ]
    adicionar = cargo_alvo not in membro.roles

    try:
        if remover:
            await membro.remove_roles(
                *remover,
                reason="Sincronização da hierarquia de XP da NÊMESIS",
            )
        if adicionar:
            await membro.add_roles(
                cargo_alvo,
                reason="Progressão automática por XP da NÊMESIS",
            )
    except (discord.Forbidden, discord.HTTPException):
        log.exception(
            "Não foi possível sincronizar patente de %s no servidor %s.",
            membro.id, guild.id,
        )
        return str(patente.get("nome"))

    if atualizar_perfil:
        try:
            perfil_patente = await definir_patente(
                guild.id, membro.id, str(patente.get("nome"))
            )
        except Exception:
            log.exception("Cargo sincronizado, mas falhou ao salvar patente do perfil.")
    return str(patente.get("nome"))
