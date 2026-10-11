import discord
from discord import app_commands
from discord.ext import commands

from utils import missoes
from utils.guild_config import get_config
from utils.perfis import (
    get_perfil,
    _salvar_perfil,
    _sincronizar_site,
    calcular_patente_atual,
    definir_patente,
)

TIPOS = {
    "missao": {"nome": "Missão", "emoji": "🎯"},
    "contribuicao": {"nome": "Contribuição", "emoji": "🤝"},
    "especial": {"nome": "Missão especial", "emoji": "⭐"},
}


class Missoes(commands.Cog):
    """Missões da NÊMESIS: envio de provas, revisão e recompensa de XP."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        for tipo in ("missao", "contribuicao", "especial"):
            bot.processadores_revisao[tipo] = self.processar_aprovacao

    async def processar_aprovacao(self, guild: discord.Guild, revisao: dict) -> str:
        atividade = await missoes.get(guild.id, revisao.get("referencia_id", ""))
        if not atividade:
            return "⚠️ A atividade original não foi encontrada; nenhuma recompensa foi aplicada."

        revisao_id = str(revisao.get("id", ""))
        if revisao_id in atividade.get("recompensas_aplicadas", []):
            return "Esta revisão já foi contabilizada; nenhuma recompensa duplicada foi aplicada."

        autor_id = int(revisao.get("autor_id", 0))
        if not autor_id:
            return "⚠️ Não foi possível identificar o participante."

        try:
            recompensa = max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
        except (TypeError, ValueError):
            recompensa = 0

        perfil = await get_perfil(guild.id, autor_id)
        perfil["xp"] = int(perfil.get("xp", 0) or 0) + recompensa
        await _salvar_perfil(guild.id, autor_id, perfil)

        dados_guild = await missoes._guild(guild.id)
        alvo = next(
            (item for item in dados_guild.get("missoes", [])
             if str(item.get("id")) == str(atividade.get("id"))),
            None,
        )
        if alvo is not None:
            aplicadas = alvo.setdefault("recompensas_aplicadas", [])
            if revisao_id not in aplicadas:
                aplicadas.append(revisao_id)
            await missoes._salvar_guild(guild.id, dados_guild)

        membro = guild.get_member(autor_id)
        try:
            # A recompensa da missão também conta como P.C. no ranking compartilhado.
            # O Dashboard e o TOP 10 leem o mesmo competitivo.json.
            await _sincronizar_site(
                user_id=autor_id,
                perfil=perfil,
                nome=membro.display_name if membro else "",
                delta_pontos=recompensa,
            )
        except Exception as erro:
            print(f"[Missoes] Falha ao sincronizar P.C. de {autor_id}: {erro}")

        texto = f"✅ <@{autor_id}> recebeu **+{recompensa} XP**."
        nova_patente = await calcular_patente_atual(guild.id, perfil["xp"])
        if nova_patente and nova_patente.get("nome") != perfil.get("patente"):
            await definir_patente(guild.id, autor_id, nova_patente["nome"])
            cargo_id = nova_patente.get("cargo_id")
            cargo = guild.get_role(int(cargo_id)) if cargo_id else None
            if membro and cargo:
                try:
                    await membro.add_roles(cargo, reason="Promoção automática por conclusão de missão")
                except discord.Forbidden:
                    pass
            texto += f" Nova patente: **{nova_patente['nome']}**."
        return texto

    @app_commands.command(name="missao-completar", description="Envia uma prova de conclusão de missão.")
    @app_commands.describe(
        missao_id="ID da missão, contribuição ou missão especial",
        print="Imagem comprovando a conclusão",
    )
    async def missao_completar(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        print: discord.Attachment,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Use este comando dentro do servidor.", ephemeral=True)
            return

        atividade = await missoes.get(guild.id, missao_id)
        if not atividade or not atividade.get("ativa", True):
            await interaction.followup.send("❌ Não encontrei uma atividade ativa com esse ID.", ephemeral=True)
            return

        tipo = str(atividade.get("tipo", "missao")).lower()
        if tipo not in TIPOS:
            await interaction.followup.send("❌ Tipo de atividade inválido. Peça à staff para corrigir a configuração.", ephemeral=True)
            return

        config = await get_config(guild.id)
        canal_id = config.get(f"canal_provas_{tipo}_id")
        try:
            canal_id = int(canal_id) if canal_id else None
        except (TypeError, ValueError):
            canal_id = None

        canal = guild.get_channel(canal_id) if canal_id else None
        if canal is None and canal_id:
            try:
                canal = await guild.fetch_channel(canal_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                print(f"[Missoes] Falha ao resolver canal de provas {canal_id}: {erro}")

        if not isinstance(canal, discord.TextChannel):
            await interaction.followup.send("❌ O canal de provas desse tipo ainda não foi configurado.", ephemeral=True)
            return

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.followup.send("❌ O sistema de revisão não está carregado. Avise a staff.", ephemeral=True)
            return

        info = TIPOS[tipo]
        await revisoes_cog.abrir_revisao(
            guild,
            canal,
            tipo="missao",
            autor_id=interaction.user.id,
            referencia_id=str(atividade["id"]),
            print_url=print.url,
            titulo=f"{info['emoji']} {info['nome']} — {atividade.get('titulo', 'Atividade')}",
            descricao=f"Prova enviada por {interaction.user.mention}. Recompensa: {int(atividade.get('recompensa_xp', atividade.get('pontos', 0)) or 0)} XP.",
        )
        await interaction.followup.send(
            f"✅ Sua prova foi enviada para {canal.mention} e aguarda revisão da staff.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Missoes(bot))
