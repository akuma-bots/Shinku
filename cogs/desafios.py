import discord
from discord import app_commands
from discord.ext import commands

from utils import desafios
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config
from utils.perfis import ARQUIVO_PERFIS, get_perfil, calcular_patente_atual, definir_patente

XP_VITORIA_PVP = 50  # ajuste esse valor como preferir


def _view_desafio(desafio_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aceitar", style=discord.ButtonStyle.success,
                                     emoji="⚔️", custom_id=f"desafio:aceitar:{desafio_id}"))
    view.add_item(discord.ui.Button(label="Recusar", style=discord.ButtonStyle.danger,
                                     emoji="🚫", custom_id=f"desafio:recusar:{desafio_id}"))
    return view


async def _atualizar_stats_pvp(guild_id: int, vencedor_id: int, perdedor_id: int):
    await get_perfil(guild_id, vencedor_id)
    await get_perfil(guild_id, perdedor_id)
    todos = await carregar(ARQUIVO_PERFIS, {})
    perfis_guild = todos.setdefault(str(guild_id), {})

    pv = perfis_guild[str(vencedor_id)]
    patente_antiga = pv.get("patente")
    pv["vitorias"] = pv.get("vitorias", 0) + 1
    pv["kills"] = pv.get("kills", 0) + 1
    pv["xp"] = pv.get("xp", 0) + XP_VITORIA_PVP

    pp = perfis_guild[str(perdedor_id)]
    pp["derrotas"] = pp.get("derrotas", 0) + 1
    pp["deaths"] = pp.get("deaths", 0) + 1

    await salvar(ARQUIVO_PERFIS, todos)
    return pv, patente_antiga


class Desafios(commands.Cog):
    """Duelo PvP casual: /desafiar posta em Desafios com botões Aceitar/
    Recusar; se aceito, anuncia em Lutas; o resultado é enviado por print e
    passa pelo mesmo motor de revisão manual (Provas-PVP) antes de atualizar
    XP, vitórias/derrotas e patente automaticamente."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.processadores_revisao["pvp"] = self.processar_aprovacao_pvp

    async def processar_aprovacao_pvp(self, guild: discord.Guild, revisao: dict) -> str:
        desafio = await desafios.get(guild.id, revisao["referencia_id"])
        if not desafio:
            return "⚠️ Desafio original não foi encontrado."

        pv, patente_antiga = await _atualizar_stats_pvp(guild.id, desafio["vencedor_id"], desafio["perdedor_id"])
        await desafios.definir_status(guild.id, desafio["id"], "concluido")

        texto = f"🏆 <@{desafio['vencedor_id']}> venceu! +{XP_VITORIA_PVP} XP, +1 vitória. <@{desafio['perdedor_id']}> +1 derrota."

        nova_patente = await calcular_patente_atual(guild.id, pv["xp"])
        if nova_patente and nova_patente["nome"] != patente_antiga:
            await definir_patente(guild.id, desafio["vencedor_id"], nova_patente["nome"])
            membro = guild.get_member(desafio["vencedor_id"])
            cargo_id = nova_patente.get("cargo_id")
            if membro and cargo_id:
                cargo = guild.get_role(cargo_id)
                if cargo:
                    try:
                        await membro.add_roles(cargo, reason="Promoção automática por PvP")
                    except discord.Forbidden:
                        pass
            texto += f"\n⬆️