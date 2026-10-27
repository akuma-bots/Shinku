import logging

import discord
from discord.ext import commands

from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
CANAL_MODELO_CONVITE_ID = 1563995880623841332
ARQUIVO_ESTADO = "painel_modelo_convite.json"

TEXTO_CONVITE = (
    "✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — RECRUTAMENTO・✦\\n"
    "⟡・Procura uma organização para evoluir, competir e fazer parte de uma equipe ativa?\\n\\n"
    "A NÊMESIS reúne jogadores com foco em jogos de luta, PvP, missões, eventos e competições. "
    "Se você busca cooperação, desenvolvimento e disputas organizadas, venha conhecer nossa comunidade.\\n\\n"
    "➜ Entre no servidor, leia as regras e preencha o formulário de entrada no canal indicado. "
    "A equipe avaliará sua candidatura.\\n\\n"
    "NÊMESIS — entre, evolua e prove seu valor."
)


class PainelModeloConvite(commands.Cog):
    """Publica e mantém o modelo oficial de convite no canal definido."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            logger.warning("Modelo de convite: servidor NÊMESIS indisponível.")
            return

        try:
            canal = guild.get_channel(CANAL_MODELO_CONVITE_ID)
            if canal is None:
                canal = await guild.fetch_channel(CANAL_MODELO_CONVITE_ID)
            if not callable(getattr(canal, "send", None)):
                logger.error("Canal do modelo de convite não aceita mensagens.")
                return

            estado = await carregar(ARQUIVO_ESTADO, {})
            mensagem = None
            if estado.get("canal_id") == CANAL_MODELO_CONVITE_ID and estado.get("mensagem_id"):
                try:
                    mensagem = await canal.fetch_message(int(estado["mensagem_id"]))
                except discord.NotFound:
                    mensagem = None

            embed = discord.Embed(
                title="✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — MODELO DE CONVITE・✦",
                description=(
                    "Use o texto abaixo para convidar novos membros. Copie a mensagem e compartilhe "
                    "com pessoas que tenham interesse em jogos competitivos e na comunidade.\\n\\n"
                    f"> {TEXTO_CONVITE.replace(chr(10), chr(10) + chr(62) + chr(32))}"
                ),
                color=0xB51F32,
            )
            embed.set_footer(text="NÊMESIS • CENTRAL DE RECRUTAMENTO")
            if mensagem:
                await mensagem.edit(embed=embed)
                acao = "atualizado"
            else:
                mensagem = await canal.send(embed=embed)
                acao = "publicado"

            await salvar(ARQUIVO_ESTADO, {
                "canal_id": CANAL_MODELO_CONVITE_ID,
                "mensagem_id": mensagem.id,
            })
            logger.info("Modelo de convite %s (canal=%s, mensagem=%s).",
                        acao, CANAL_MODELO_CONVITE_ID, mensagem.id)
        except (discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            logger.exception("Falha ao publicar modelo de convite da NÊMESIS.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PainelModeloConvite(bot))