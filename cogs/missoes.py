import discord
from discord import app_commands
from discord.ext import commands

from utils import missoes
from utils.guild_config import get_config, set_config
from utils.perfis import (
    get_perfil,
    calcular_patente_atual,
    definir_patente,
    _salvar_perfil,
)


TIPO_CHOICES = [
    app_commands.Choice(name="Missões", value="missao"),
    app_commands.Choice(name="Contribuições", value="contribuicao"),
    app_commands.Choice(name="Missões Especiais", value="especial"),
]


TIPOS = {
    "missao": {
        "nome": "Missões",
        "icone": "🎯",
        "cor": 0xFEE75C,
    },
    "contribuicao": {
        "nome": "Contribuições",
        "icone": "🤝",
        "cor": 0x5865F2,
    },
    "especial": {
        "nome": "Missões Especiais",
        "icone": "✦",
        "cor": 0x9B59B6,
    },
}


async def _adicionar_xp(
    guild_id: int,
    user_id: int,
    xp_ganho: int,
) -> dict:

    perfil = await get_perfil(
        guild_id,
        user_id,
    )

    patente_antiga = perfil["patente"]

    perfil["xp"] += xp_ganho

    await _salvar_perfil(
        guild_id,
        user_id,
        perfil,
    )

    return {
        "perfil": perfil,
        "patente_antiga": patente_antiga,
    }


class Missoes(commands.Cog):

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

        if not hasattr(
            bot,
            "processadores_revisao",
        ):
            bot.processadores_revisao = {}

        bot.processadores_revisao[
            "missao"
        ] = self.processar_aprovacao

    # ============================================================
    # PROCESSAMENTO DA APROVAÇÃO
    # ============================================================

    async def processar_aprovacao(
        self,
        guild: discord.Guild,
        revisao: dict,
    ) -> str:

        missao = await missoes.get(
            guild.id,
            revisao["referencia_id"],
        )

        if not missao:
            return (
                "⚠️ A missão original não foi encontrada "
                "(pode ter sido removida)."
            )

        recompensa = int(
            missao.get(
                "recompensa_xp",
                0,
            )
        )

        resultado = await _adicionar_xp(
            guild.id,
            revisao["autor_id"],
            recompensa,
        )

        tipo = missao.get(
            "tipo",
            "missao",
        )

        info = TIPOS.get(
            tipo,
            TIPOS["missao"],
        )

        texto = (
            f"+{recompensa} XP para "
            f"<@{revisao['autor_id']}>"
        )

        # ========================================================
        # VERIFICAÇÃO DE PATENTE
        # ========================================================

        nova_patente = await calcular_patente_atual(
            guild.id,
            resultado["perfil"]["xp"],
        )

        if (
            nova_patente
            and nova_patente["nome"]
            != resultado["patente_antiga"]
        ):

            await definir_patente(
                guild.id,
                revisao["autor_id"],
                nova_patente["nome"],
            )

            membro = guild.get_member(
                revisao["autor_id"]
            )

            cargo_id = nova_patente.get(
                "cargo_id"
            )

            if membro and cargo_id:

                cargo = guild.get_role(
                    cargo_id
                )

                if cargo:

                    try:
                        await membro.add_roles(
                            cargo,
                            reason=(
                                "Promoção automática "
                                "por conclusão aprovada."
                            ),
                        )

                    except discord.Forbidden:
                        pass

            texto += (
                f"\n⬆️ Promovido(a) para "
                f"**{nova_patente['nome']}**"
            )

        # ========================================================
        # RECORDES
        # ========================================================

        recordes_cog = self.bot.get_cog(
            "Recordes"
        )

        if recordes_cog:

            await recordes_cog.anunciar_se_recorde(
                guild,
                "xp_total",
                revisao["autor_id"],
                resultado["perfil"]["xp"],
            )

        return texto

    # ============================================================
    # CONFIGURAÇÃO DOS CANAIS
    # ============================================================

    @app_commands.command(
        name="missao-canais",
        description=(
            "Configura os canais de um dos sistemas "
            "de Missões da NÊMESIS."
        ),
    )
    @app_commands.describe(
        tipo="Sistema que será configurado.",
        canal_missoes=(
            "Canal onde as atividades serão publicadas."
        ),
        canal_provas=(
            "Canal onde as provas serão enviadas "
            "para aprovação."
        ),
    )
    @app_commands.choices(
        tipo=TIPO_CHOICES
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def missao_canais(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        canal_missoes: discord.TextChannel,
        canal_provas: discord.TextChannel,
    ):

        chave_missoes = (
            f"canal_missoes_{tipo.value}_id"
        )

        chave_provas = (
            f"canal_provas_{tipo.value}_id"
        )

        await set_config(
            interaction.guild.id,
            **{
                chave_missoes: canal_missoes.id,
                chave_provas: canal_provas.id,
            },
        )

        info = TIPOS[
            tipo.value
        ]

        await interaction.response.send_message(
            (
                f"{info['icone']} **{info['nome']}** configurado.\n\n"
                f"Atividades: {canal_missoes.mention}\n"
                f"Provas: {canal_provas.mention}"
            ),
            ephemeral=True,
        )

    # ============================================================
    # CRIAR
    # ============================================================

    @app_commands.command(
        name="missao-criar",
        description=(
            "Cria uma atividade de Missões, "
            "Contribuições ou Missões Especiais."
        ),
    )
    @app_commands.describe(
        tipo="Tipo da atividade.",
        titulo="Título da atividade.",
        descricao="Descrição e objetivo.",
        recompensa_xp="Quantidade de XP concedida após aprovação.",
    )
    @app_commands.choices(
        tipo=TIPO_CHOICES
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def missao_criar(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        titulo: str,
        descricao: str,
        recompensa_xp: app_commands.Range[int, 1, 100000],
    ):

        missao = await missoes.criar(
            interaction.guild.id,
            tipo.value,
            titulo,
            descricao,
            recompensa_xp,
            interaction.user.id,
        )

        config = await get_config(
            interaction.guild.id
        )

        chave_canal = (
            f"canal_missoes_{tipo.value}_id"
        )

        canal_id = config.get(
            chave_canal
        )

        canal = (
            interaction.guild.get_channel(
                canal_id
            )
            if canal_id
            else interaction.channel
        )

        info = TIPOS[
            tipo.value
        ]

        embed = discord.Embed(
            title=(
                f"{info['icone']} "
                f"{info['nome']}"
            ),
            description=titulo,
            color=info["cor"],
        )

        embed.add_field(
            name="Objetivo",
            value=descricao,
            inline=False,
        )

        embed.add_field(
            name="Recompensa",
            value=f"**{recompensa_xp} XP**",
            inline=True,
        )

        embed.add_field(
            name="Identificação",
            value=f"`{missao['id']}`",
            inline=True,
        )

        embed.set_footer(
            text=(
                "Use /missao-completar "
                "para enviar sua prova."
            )
        )

        await canal.send(
            embed=embed
        )

        await interaction.response.send_message(
            (
                f"✅ {info['nome']} criada em "
                f"{canal.mention}."
            ),
            ephemeral=True,
        )

    # ============================================================
    # LISTAR
    # ============================================================

    @app_commands.command(
        name="missao-listar",
        description=(
            "Lista as atividades ativas."
        ),
    )
    @app_commands.describe(
        tipo="Filtra por tipo.",
    )
    @app_commands.choices(
        tipo=TIPO_CHOICES
    )
    async def missao_listar(
        self,
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str] = None,
    ):

        lista = await missoes.listar(
            interaction.guild.id,
            tipo=tipo.value
            if tipo
            else None,
        )

        if not lista:

            await interaction.response.send_message(
                "Nenhuma atividade ativa no momento.",
                ephemeral=True,
            )

            return

        linhas = []

        for item in lista:

            info = TIPOS.get(
                item.get(
                    "tipo",
                    "missao",
                ),
                TIPOS["missao"],
            )

            linhas.append(
                f"{info['icone']} "
                f"**{item['titulo']}** — "
                f"{item['recompensa_xp']} XP "
                f"`{item['id']}`"
            )

        embed = discord.Embed(
            title="📋 Atividades ativas",
            description="\n".join(linhas),
            color=0x5865F2,
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ============================================================
    # REMOVER
    # ============================================================

    @app_commands.command(
        name="missao-remover",
        description=(
            "Desativa uma atividade."
        ),
    )
    @app_commands.describe(
        missao_id=(
            "ID da atividade."
        ),
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def missao_remover(
        self,
        interaction: discord.Interaction,
        missao_id: str,
    ):

        ok = await missoes.desativar(
            interaction.guild.id,
            missao_id,
        )

        if not ok:

            await interaction.response.send_message(
                (
                    "❌ Não encontrei nenhuma "
                    "atividade ativa com esse ID."
                ),
                ephemeral=True,
            )

            return

        await interaction.response.send_message(
            "🗑️ Atividade desativada.",
            ephemeral=True,
        )

    # ============================================================
    # ENVIAR PROVA
    # ============================================================

    @app_commands.command(
        name="missao-completar",
        description=(
            "Envia uma prova de conclusão."
        ),
    )
    @app_commands.describe(
        missao_id=(
            "ID da atividade."
        ),
        print=(
            "Imagem comprovando a conclusão."
        ),
    )
    async def missao_completar(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        print: discord.Attachment,
    ):

        missao = await missoes.get(
            interaction.guild.id,
            missao_id,
        )

        if not missao or not missao["ativa"]:

            await interaction.response.send_message(
                (
                    "❌ Não encontrei nenhuma "
                    "atividade ativa com esse ID."
                ),
                ephemeral=True,
            )

            return

        tipo = missao.get(
            "tipo",
            "missao",
        )

        if tipo not in TIPOS:

            await interaction.response.send_message(
                (
                    "❌ Essa atividade utiliza "
                    "um tipo antigo que não "
                    "faz mais parte da NÊMESIS."
                ),
                ephemeral=True,
            )

            return

        config = await get_config(
            interaction.guild.id
        )

        chave_provas = (
            f"canal_provas_{tipo}_id"
        )

        canal_id = config.get(
            chave_provas
        )

        canal = (
            interaction.guild.get_channel(
                canal_id
            )
            if canal_id
            else None
        )

        if not canal:

            await interaction.response.send_message(
                (
                    "❌ O canal de provas desse "
                    "sistema ainda não foi configurado."
                ),
                ephemeral=True,
            )

            return

        revisoes_cog = self.bot.get_cog(
            "Revisoes"
        )

        if not revisoes_cog:

            await interaction.response.send_message(
                (
                    "⚠️ O sistema de revisão "
                    "não está carregado."
                ),
                ephemeral=True,
            )

            return

        info = TIPOS[
            tipo
        ]

        await revisoes_cog.abrir_revisao(
            interaction.guild,
            canal,
            tipo="missao",
            autor_id=interaction.user.id,
            referencia_id=missao["id"],
            print_url=print.url,
            titulo=(
                f"{info['nome']} — "
                f"{missao['titulo']}"
            ),
            descricao=(
                f"Prova enviada por "
                f"{interaction.user.mention}."
            ),
        )

        await interaction.response.send_message(
            (
                f"✅ Sua prova foi enviada para "
                f"{canal.mention} e aguarda revisão."
            ),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
):
    await bot.add_cog(
        Missoes(bot)
    )