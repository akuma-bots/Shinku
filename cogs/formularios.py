import discord
from discord import app_commands
from discord.ext import commands

from utils import formularios

PREFIXO_ABRIR = "formulario:abrir:"
PREFIXO_APROVAR = "formulario:aprovar:"
PREFIXO_RECUSAR = "formulario:recusar:"


class ModalFormulario(discord.ui.Modal):
    """Modal de UMA página do formulário (até 5 perguntas, limite do
    Discord). Ao enviar, se ainda houver mais páginas, abre a próxima
    automaticamente — encadeando os modais até completar o formulário
    inteiro. As respostas vão sendo acumuladas de página em página."""

    def __init__(self, formulario: dict, pagina_indice: int = 0, respostas_acumuladas: list = None):
        pagina = formulario["paginas"][pagina_indice]
        total_paginas = len(formulario["paginas"])
        titulo = formulario["nome"][:34]
        if total_paginas > 1:
            titulo = f"{titulo} ({pagina_indice + 1}/{total_paginas})"[:45]
        super().__init__(title=titulo)

        self.formulario = formulario
        self.pagina_indice = pagina_indice
        self.respostas_acumuladas = respostas_acumuladas or []
        self.inputs = []
        for pergunta in pagina:
            campo = discord.ui.TextInput(label=pergunta[:45], style=discord.TextStyle.paragraph,
                                          required=True, max_length=1000)
            self.inputs.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        respostas_desta_pagina = [str(campo.value) for campo in self.inputs]
        todas_respostas = self.respostas_acumuladas + respostas_desta_pagina

        proxima_pagina = self.pagina_indice + 1
        if proxima_pagina < len(self.formulario["paginas"]):
            await interaction.response.send_modal(ModalFormulario(self.formulario, proxima_pagina, todas_respostas))
            return

        cog = interaction.client.get_cog("Formularios")
        resposta = await formularios.criar_resposta(interaction.guild.id, self.formulario["id"],
                                                      interaction.user.id, todas_respostas)
        await cog.notificar_cargos(interaction.guild, self.formulario, resposta)
        await interaction.response.send_message("✅ Sua candidatura foi enviada!", ephemeral=True)


def _embed_resposta(formulario: dict, resposta: dict, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(title=f"📥 Nova candidatura — {formulario['nome']}", color=0x5865F2)
    embed.add_field(name="Candidato", value=f"<@{resposta['autor_id']}>", inline=False)
    perguntas = formularios.perguntas_flat(formulario)
    for pergunta, resp in zip(perguntas, resposta["respostas"]):
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
    """Sistema de formulários/candidaturas por páginas: cada formulário tem
    seu painel customizável (título, descrição, banner) e é dividido em
    páginas de até 5 perguntas — o bot encadeia os modais automaticamente
    até completar todas. As respostas vão por DM pros cargos configurados,
    com botões de Aprovar/Recusar; o candidato é avisado do resultado."""

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

    @app_commands.command(name="formulario-criar", description="Cria um formulário (painel). Adicione as páginas de perguntas depois.")
    @app_commands.describe(nome="Nome interno do formulário (ex: Parceria)",
                            titulo_painel="Título mostrado no painel", descricao_painel="Descrição mostrada no painel",
                            banner="Imagem de banner do painel (opcional)")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_criar(self, interaction: discord.Interaction, nome: str, titulo_painel: str,
                                descricao_painel: str, banner: discord.Attachment = None):
        formulario = await formularios.criar_formulario(
            interaction.guild.id, nome, titulo_painel, descricao_painel,
            banner.url if banner else None, interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ Formulário **{nome}** criado (ID: `{formulario['id']}`). "
            f"Agora use `/formulario-pagina-adicionar` pra adicionar as perguntas (até 5 por página, "
            f"quantas páginas quiser), depois `/formulario-cargo-adicionar` e `/formulario-painel`.",
            ephemeral=True,
        )

    @app_commands.command(name="formulario-pagina-adicionar", description="Adiciona uma página de perguntas (até 5) a um formulário.")
    @app_commands.describe(
        formulario_id="ID do formulário (aparece em /formulario-listar)",
        pergunta1="1ª pergunta desta página", pergunta2="2ª pergunta (opcional)",
        pergunta3="3ª pergunta (opcional)", pergunta4="4ª pergunta (opcional)", pergunta5="5ª pergunta (opcional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_pagina_adicionar(self, interaction: discord.Interaction, formulario_id: str,
                                           pergunta1: str, pergunta2: str = None, pergunta3: str = None,
                                           pergunta4: str = None, pergunta5: str = None):
        perguntas = [p for p in [pergunta1, pergunta2, pergunta3, pergunta4, pergunta5] if p]
        formulario = await formularios.adicionar_pagina(interaction.guild.id, formulario_id, perguntas)
        if not formulario:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Página {len(formulario['paginas'])} adicionada ({len(perguntas)} pergunta(s)). "
            f"Total agora: {len(formulario['paginas'])} página(s).", ephemeral=True,
        )

    @app_commands.command(name="formulario-pagina-remover", description="Remove uma página de um formulário.")
    @app_commands.describe(formulario_id="ID do formulário", numero_pagina="Número da página (1, 2, 3...) — veja em /formulario-paginas-listar")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_pagina_remover(self, interaction: discord.Interaction, formulario_id: str, numero_pagina: int):
        ok = await formularios.remover_pagina(interaction.guild.id, formulario_id, numero_pagina - 1)
        if not ok:
            await interaction.response.send_message("Não achei essa página nesse formulário.", ephemeral=True)
            return
        await interaction.response.send_message(f"🗑️ Página {numero_pagina} removida.", ephemeral=True)

    @app_commands.command(name="formulario-paginas-listar", description="Lista as páginas e perguntas de um formulário.")
    @app_commands.describe(formulario_id="ID do formulário")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_paginas_listar(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if not formulario:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        if not formulario["paginas"]:
            await interaction.response.send_message("Esse formulário ainda não tem nenhuma página de pergunta.", ephemeral=True)
            return

        blocos = []
        for i, pagina in enumerate(formulario["paginas"], start=1):
            perguntas_texto = "\n".join(f"  {j}. {p}" for j, p in enumerate(pagina, start=1))
            blocos.append(f"**Página {i}**\n{perguntas_texto}")
        embed = discord.Embed(title=f"📋 Páginas — {formulario['nome']}", description="\n\n".join(blocos), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="formulario-listar", description="Lista os formulários configurados.")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_listar(self, interaction: discord.Interaction):
        lista = await formularios.listar_formularios(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhum formulário criado ainda.", ephemeral=True)
            return
        linhas = [
            f"**{f['nome']}** (ID: `{f['id']}`) — {len(f['paginas'])} página(s), "
            f"{len(formularios.perguntas_flat(f))} pergunta(s) no total, "
            f"{len(f['cargos_notificar'])} cargo(s) notificado(s)"
            for f in lista
        ]
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
        if not formulario["paginas"]:
            await interaction.response.send_message(
                "Esse formulário ainda não tem nenhuma pergunta. Use `/formulario-pagina-adicionar` primeiro.",
                ephemeral=True,
            )
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
            if not formulario or not formulario["paginas"]:
                await interaction.response.send_message("Esse formulário não existe mais ou não tem perguntas.", ephemeral=True)
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