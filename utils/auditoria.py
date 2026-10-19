import logging

import discord

from utils.guild_config import get_config


_LOG = logging.getLogger(__name__)


async def registrar(
    guild: discord.Guild,
    titulo: str,
    descricao: str,
    cor: int = 0x99AAB5,
):
    """Publica auditoria sem deixar falhas de canal/API interromperem o fluxo principal."""
    try:
        config = await get_config(guild.id)
        canal_id = config.get("canal_auditoria_id")
        if not canal_id:
            return False

        canal = guild.get_channel(int(canal_id))
        if canal is None:
            try:
                canal = await guild.fetch_channel(int(canal_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                _LOG.warning(
                    "Canal de auditoria indisponível (guild=%s, channel=%s).",
                    guild.id, canal_id,
                )
                return False

        if not callable(getattr(canal, "send", None)):
            _LOG.warning(
                "Destino de auditoria não aceita mensagens (guild=%s, channel=%s).",
                guild.id, canal_id,
            )
            return False

        embed = discord.Embed(
            title=str(titulo or "Registro de auditoria")[:256],
            description=str(descricao or "Sem detalhes.")[:4096],
            color=cor,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="NÊMESIS • Auditoria")
        await canal.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True
    except discord.Forbidden:
        _LOG.warning("Sem permissão para publicar auditoria (guild=%s).", guild.id)
    except discord.HTTPException:
        _LOG.exception("Falha HTTP ao publicar auditoria (guild=%s).", guild.id)
    except Exception:
        _LOG.exception("Erro inesperado no sistema de auditoria (guild=%s).", guild.id)
    return False
