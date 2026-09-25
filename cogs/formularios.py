import discord
from discord import app_commands
from discord.ext import commands

from utils import formularios

PREFIXO_ABRIR = "formulario:abrir:"
PREFIXO_APROVAR = "formulario:aprovar:"
PREFIXO_RECUSAR = "formulario:recusar:"


class ModalFormulario(discord.ui.Modal):
    """Modal gerado dinamicamente a partir das perguntas configuradas no
    formulário — no máximo 5, que é o limite de campos do Discord pra esse
    tipo de janela."""

    def __init__(self, formulario: dict):
        super().__init__(title=formulario["nome"][:45])
        self.formulario = formulario
        self.inputs = []
        for pergunta in formulario["perguntas"][:5]:
            campo = discord.ui.TextInput(label=pergunta[:45], style=discord.TextStyle.paragraph,
                                          required=True, max_length=1000)
            self.inputs.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Formularios")
        respostas = [str(campo.value) for campo in self.inputs]
        resposta = await formularios.criar_resposta(interaction.guild.id, self.formulario["id"],
                                                      interaction.user.id, respostas)
        await cog.notificar_cargos(interaction.guild, self.formulario, resposta)
        await interaction.response.send_message("✅ Sua candidatura foi enviada!", ephemeral=True)


def _embed_resposta(formulario: dict, resposta: dict, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(title=f"📥 Nova candidatura — {formulario['nome']}", color=0x5865F2)
    embed.add_field(name="Candidato", value=f"<@{resposta['autor_id']}>", inline=False)
    for pergunta, resp in zip(formulario["perguntas"], resposta["respostas"]):
        embed.add_field(name=pergunta[:256], value=resp[:1024], inline=False)
    embed.set_footer(text=f"ID: {resposta['id']} • {guild.name}")
    return embed


def _view_resposta(resposta_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success, emoji="✅",
                                     custom_id=f"{PREFIXO_APROVAR}{resposta_id}"))
    view.add_item(discord.ui.Button(label="Recusar", style=discord.ButtonStyle.danger, emoji="❌",
                                     custom_id=f"{PREFIXO_RECUSAR}{resposta_id}"))
    return view


class Formularios(commands.Cog):
    """Sistema de formulários/candidaturas customizáveis: cada formulário
    tem seu próprio painel (título, descrição, banner), até 5 perguntas e
    uma lista de cargos que recebem a resposta por DM assim que alguém
    envia. Quem recebe a DM pode aprovar ou recusar direto por ali; o
    candidato é avisado do resultado automaticamente, também por DM."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def notificar_cargos(self, guild: discord.Guild, formulario: dict, resposta: dict):
        embed = _embed_resposta(formulario, resposta, guild)
        view = _view_resposta(resposta["id"])

        notificados = set()
        for cargo_id in formulario["cargos_notificar"]:
            cargo = guild.get_role(cargo_id)
            if not cargo:
                continue
            for membro in cargo.members:
                if membro.id in notificados or membro.bot:
                    continue
                notificados.add(membro.id)
                try:
                    await membro.send(embed=embed, view=view)
                except discord.Forbidden:
                    pass  # DM fechada — a pessoa simplesmente não recebe

    @app_commands.command(name="formulario-criar", description="Cria um formulário de candidatura customizável (até 5 perguntas).")
    @app_commands.describe(
        nome="Nome interno do formulário (ex: Parceria)",
        titulo_painel="Título mostrado no painel", descricao_painel="Descrição mostrada no painel",
        pergunta1="1ª pergunta do formulário", pergunta2="2ª pergunta (opcional)",
        pergunta3="3ª pergunta (opcional)", pergunta4="4ª pergunta (opcional)", pergunta5="5ª pergunta (opcional)",
        banner="Imagem de banner do painel (opcional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_criar(self, interaction: discord.Interaction, nome: str, titulo_painel: str,
                                descricao_painel: str, pergunta1: str, pergunta2: str = None,
                                pergunta3: str = None, pergunta4: str = None, pergunta5: str = None,
                                banner: discord.Attachment = None):
        perguntas = [p for p in [pergunta1, pergunta2, pergunta3, pergunta4, pergunta5] if p]
        formulario = await formularios.criar_formulario(
            interaction.guild.id, nome, titulo_painel, descricao_painel,
            banner.url if banner else None, perguntas, interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ Formulário **{nome}** criado (ID: `{formulario['id']}`). "
            f"Use `/formulario-cargo-adicionar` pra definir quem recebe as candidaturas, "
            f"e `/formulario-painel` pra publicar.", ephemeral=True,
        )

    @app_commands.command(name="formulario-listar", description="Lista os formulários configurados.")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_listar(self, interaction: discord.Interaction):
        lista = await formularios.listar_formularios(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhum formulário criado ainda.", ephemeral=True)
            return
        linhas = [f"**{f['nome']}** (ID: `{f['id']}`) — {len(f['perguntas'])} pergunta(s), "
                  f"{len(f['cargos_notificar'])} cargo(s) notificado(s)" for f in lista]
        embed = discord.Embed(title="📋 Formulários configurados", description="\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="formulario-remover", description="Remove um formulário.")
    @app_commands.describe(formulario_id="ID do formulário (aparece em /formulario-listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_remover(self, interaction: discord.Interaction, formulario_id: str):
        ok = await formularios.remover_formulario(interaction.guild.id, formulario_id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Formulário removido.", ephemeral=True)

    @app_commands.command(name="formulario-cargo-adicionar", description="Adiciona um cargo que recebe as candidaturas por DM.")
    @app_commands.describe(formulario_id="ID do formulário", cargo="Cargo que vai receber as candidaturas")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_cargo_adicionar(self, interaction: discord.Interaction, formulario_id: str, cargo: discord.Role):
        ok = await formularios.adicionar_cargo_notificar(interaction.guild.id, formulario_id, cargo.id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ {cargo.mention} agora recebe candidaturas desse formulário.", ephemeral=True)

    @app_commands.command(name="formulario-cargo-remover", description="Remove um cargo da lista de notificação de um formulário.")
    @app_commands.describe(formulario_id="ID do formulário", cargo="Cargo a remover")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_cargo_remover(self, interaction: discord.Interaction, formulario_id: str, cargo: discord.Role):
        ok = await formularios.remover_cargo_notificar(interaction.guild.id, formulario_id, cargo.id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ {cargo.mention} não recebe mais candidaturas desse formulário.", ephemeral=True)

    @app_commands.command(name="formulario-painel", description="Publica o painel de um formulário neste canal.")
    @app_commands.describe(formulario_id="ID do formulário (aparece em /formulario-listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_painel(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if not formulario:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return

        embed = discord.Embed(title=formulario["titulo_painel"], description=formulario["descricao_painel"], color=0x5865F2)
        if formulario["banner_url"]:
            embed.set_image(url=formulario["banner_url"])

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Candidatar-se", style=discord.ButtonStyle.primary, emoji="📝",
                                         custom_id=f"{PREFIXO_ABRIR}{formulario_id}"))
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Painel publicado.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")

        if custom_id.startswith(PREFIXO_ABRIR):
            formulario_id = custom_id[len(PREFIXO_ABRIR):]
            formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
            if not formulario:
                await interaction.response.send_message("Esse formulário não existe mais.", ephemeral=True)
                return
            await interaction.response.send_modal(ModalFormulario(formulario))
            return

        if custom_id.startswith(PREFIXO_APROVAR) or custom_id.startswith(PREFIXO_RECUSAR):
            aprovado = custom_id.startswith(PREFIXO_APROVAR)
            resposta_id = custom_id.split(":")[-1]

            # O clique acontece na DM, então não existe interaction.guild —
            # procuramos em qual servidor essa resposta foi registrada.
            resposta, guild_encontrada = None, None
            for guild in self.bot.guilds:
                candidata = await formularios.get_resposta(guild.id, resposta_id)
                if candidata:
                    resposta, guild_encontrada = candidata, guild
                    break

            if not resposta:
                await interaction.response.send_message("Essa candidatura não existe mais.", ephemeral=True)
                return
            if resposta["status"] != "pendente":
                await interaction.response.send_message(f"Essa candidatura já foi **{resposta['status']}**.", ephemeral=True)
                return

            novo_status = "aprovada" if aprovado else "recusada"
            await formularios.definir_status_resposta(guild_encontrada.id, resposta_id, novo_status, interaction.user.id)

            embed = interaction.message.embeds[0]
            embed.color = 0x57F287 if aprovado else 0xED4245
            embed.add_field(
                name="Decisão",
                value=f"{'✅ Aprovado' if aprovado else '❌ Recusado'} por {interaction.user.mention}",
                inline=False,
            )
            await interaction.response.edit_message(embed=embed, view=None)

            candidato = guild_encontrada.get_member(resposta["autor_id"])
            if candidato:
                try:
                    texto = "🎉 Sua candidatura foi **aprovada**!" if aprovado else "❌ Sua candidatura foi recusada."
                    await candidato.send(f"{texto} (servidor: {guild_encontrada.name})")
                except discord.Forbidden:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Formularios(bot))