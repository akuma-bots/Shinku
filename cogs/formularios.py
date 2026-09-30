import discord
from discord import app_commands
from discord.ext import commands

from utils import formularios

PREFIXO_ABRIR = "formulario:abrir:"
PREFIXO_APROVAR = "formulario:aprovar:"
PREFIXO_RECUSAR = "formulario:recusar:"


class ModalFormulario(discord.ui.Modal):
    """Modal de UMA pÃ¡gina do formulÃ¡rio (atÃ© 5 perguntas, limite do
    Discord). Ao enviar, se ainda houver mais pÃ¡ginas, abre a prÃ³xima
    automaticamente â€” encadeando os modais atÃ© completar o formulÃ¡rio
    inteiro. As respostas vÃ£o sendo acumuladas de pÃ¡gina em pÃ¡gina."""

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
            campo = discord.ui.TextInput(
                label=pergunta[:45],
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=1000
            )
            self.inputs.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        respostas_desta_pagina = [str(campo.value) for campo in self.inputs]
        todas_respostas = self.respostas_acumuladas + respostas_desta_pagina

        proxima_pagina = self.pagina_indice + 1
        if proxima_pagina < len(self.formulario["paginas"]):
            await interaction.response.send_modal(
                ModalFormulario(self.formulario, proxima_pagina, todas_respostas)
            )
            return

        # Adia a resposta no Discord para evitar estouro de tempo (timeout de 3s)
        await interaction.response.defer(ephemeral=True)

        cog = interaction.client.get_cog("Formularios")
        resposta = await formularios.criar_resposta(
            interaction.guild.id,
            self.formulario["id"],
            interaction.user.id,
            todas_respostas
        )
        
        await cog.notificar_cargos(interaction.guild, self.formulario, resposta)
        
        # Envia a confirmaÃ§Ã£o apÃ³s processar o banco e os envios de DM
        await interaction.followup.send("âœ… Sua candidatura foi enviada!", ephemeral=True)


def _embed_resposta(formulario: dict, resposta: dict, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(title=f"ðŸ“¥ Nova candidatura â€” {formulario['nome']}", color=0x5865F2)
    embed.add_field(name="Candidato", value=f"<@{resposta['autor_id']}>", inline=False)
    perguntas = formularios.perguntas_flat(formulario)
    for pergunta, resp in zip(perguntas, resposta["respostas"]):
        embed.add_field(name=pergunta[:256], value=resp[:1024], inline=False)
    embed.set_footer(text=f"ID: {resposta['id']} â€¢ {guild.name}")
    return embed


def _view_resposta(resposta_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(
        label="Aprovar",
        style=discord.ButtonStyle.success,
        emoji="âœ…",
        custom_id=f"{PREFIXO_APROVAR}{resposta_id}"
    ))
    view.add_item(discord.ui.Button(
        label="Recusar",
        style=discord.ButtonStyle.danger,
        emoji="âŒ",
        custom_id=f"{PREFIXO_RECUSAR}{resposta_id}"
    ))
    return view


class Formularios(commands.Cog):
    """Sistema de formulÃ¡rios/candidaturas por pÃ¡ginas: cada formulÃ¡rio tem
    seu painel customizÃ¡vel (tÃ­tulo, descriÃ§Ã£o, banner) e Ã© dividido em
    pÃ¡ginas de atÃ© 5 perguntas â€” o bot encadeia os modais automaticamente
    atÃ© completar todas. As respostas vÃ£o por DM pros cargos configurados,
    com botÃµes de Aprovar/Recusar; o candidato Ã© avisado do resultado."""

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
                    pass  # DM fechada â€” a pessoa simplesmente nÃ£o recebe

    @app_commands.command(name="formulario-criar", description="Cria um formulÃ¡rio (painel). Adicione as pÃ¡ginas de perguntas depois.")
    @app_commands.describe(
        nome="Nome interno do formulÃ¡rio (ex: Parceria)",
        titulo_painel="TÃ­tulo mostrado no painel",
        descricao_painel="DescriÃ§Ã£o mostrada no painel",
        banner="Imagem de banner do painel (opcional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_criar(
        self,
        interaction: discord.Interaction,
        nome: str,
        titulo_painel: str,
        descricao_painel: str,
        banner: discord.Attachment = None
    ):
        formulario = await formularios.criar_formulario(
            interaction.guild.id,
            nome,
            titulo_painel,
            descricao_painel,
            banner.url if banner else None,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"âœ… FormulÃ¡rio **{nome}** criado (ID: `{formulario['id']}`). "
            f"Agora use `/formulario-pagina-adicionar` pra adicionar as perguntas (atÃ© 5 por pÃ¡gina, "
            f"quantas pÃ¡ginas quiser), depois `/formulario-cargo-adicionar` e `/formulario-painel`.",
            ephemeral=True,
        )

    @app_commands.command(name="formulario-pagina-adicionar", description="Adiciona uma pÃ¡gina de perguntas (atÃ© 5) a um formulÃ¡rio.")
    @app_commands.describe(
        formulario_id="ID do formulÃ¡rio (aparece em /formulario-listar)",
        pergunta1="1Âª pergunta desta pÃ¡gina",
        pergunta2="2Âª pergunta (opcional)",
        pergunta3="3Âª pergunta (opcional)",
        pergunta4="4Âª pergunta (opcional)",
        pergunta5="5Âª pergunta (opcional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_pagina_adicionar(
        self,
        interaction: discord.Interaction,
        formulario_id: str,
        pergunta1: str,
        pergunta2: str = None,
        pergunta3: str = None,
        pergunta4: str = None,
        pergunta5: str = None
    ):
        perguntas = [p for p in [pergunta1, pergunta2, pergunta3, pergunta4, pergunta5] if p]
        formulario = await formularios.adicionar_pagina(interaction.guild.id, formulario_id, perguntas)
        if not formulario:
            await interaction.response.send_message("NÃ£o achei nenhum formulÃ¡rio com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"âœ… PÃ¡gina {len(formulario['paginas'])} adicionada ({len(perguntas)} pergunta(s)). "
            f"Total agora: {len(formulario['paginas'])} pÃ¡gina(s).",
            ephemeral=True,
        )

    @app_commands.command(name="formulario-pagina-remover", description="Remove uma pÃ¡gina de um formulÃ¡rio.")
    @app_commands.describe(
        formulario_id="ID do formulÃ¡rio",
        numero_pagina="NÃºmero da pÃ¡gina (1, 2, 3...) â€” veja em /formulario-paginas-listar"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_pagina_remover(self, interaction: discord.Interaction, formulario_id: str, numero_pagina: int):
        ok = await formularios.remover_pagina(interaction.guild.id, formulario_id, numero_pagina - 1)
        if not ok:
            await interaction.response.send_message("NÃ£o achei essa pÃ¡gina nesse formulÃ¡rio.", ephemeral=True)
            return
        await interaction.response.send_message(f"ðŸ—‘ï¸ PÃ¡gina {numero_pagina} removida.", ephemeral=True)

    @app_commands.command(name="formulario-paginas-listar", description="Lista as pÃ¡ginas e perguntas de um formulÃ¡rio.")
    @app_commands.describe(formulario_id="ID do formulÃ¡rio")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_paginas_listar(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if not formulario:
            await interaction.response.send_message("NÃ£o achei nenhum formulÃ¡rio com esse ID.", ephemeral=True)
            return
        if not formulario["paginas"]:
            await interaction.response.send_message("Esse formulÃ¡rio ainda nÃ£o tem nenhuma pÃ¡gina de pergunta.", ephemeral=True)
            return

        blocos = []
        for i, pagina in enumerate(formulario["paginas"], start=1):
            perguntas_texto = "\n".join(f"  {j}. {p}" for j, p in enumerate(pagina, start=1))
            blocos.append(f"**PÃ¡gina {i}**\n{perguntas_texto}")
        embed = discord.Embed(title=f"ðŸ“‹ PÃ¡ginas â€” {formulario['nome']}", description="\n\n".join(blocos), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="formulario-listar", description="Lista os formulÃ¡rios configurados.")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_listar(self, interaction: discord.Interaction):
        lista = await formularios.listar_formularios(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhum formulÃ¡rio criado ainda.", ephemeral=True)
            return
        linhas = [
            f"**{f['nome']}** (ID: `{f['id']}`) â€” {len(f['paginas'])} pÃ¡gina(s), "
            f"{len(formularios.perguntas_flat(f))} pergunta(s) no total, "
            f"{len(f['cargos_notificar'])} cargo(s) notificado(s)"
            for f in lista
        ]
        embed = discord.Embed(title="ðŸ“‹ FormulÃ¡rios configurados", description="\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="formulario-remover", description="Remove um formulÃ¡rio.")
    @app_commands.describe(formulario_id="ID do formulÃ¡rio (aparece em /formulario-listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_remover(self, interaction: discord.Interaction, formulario_id: str):
        ok = await formularios.remover_formulario(interaction.guild.id, formulario_id)
        if not ok:
            await interaction.response.send_message("NÃ£o achei nenhum formulÃ¡rio com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message("ðŸ—‘ï¸ FormulÃ¡rio removido.", ephemeral=True)

    @app_commands.command(name="formulario-cargo-adicionar", description="Adiciona um cargo que recebe as candidaturas por DM.")
    @app_commands.describe(formulario_id="ID do formulÃ¡rio", cargo="Cargo que vai receber as candidaturas")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_cargo_adicionar(self, interaction: discord.Interaction, formulario_id: str, cargo: discord.Role):
        ok = await formularios.adicionar_cargo_notificar(interaction.guild.id, formulario_id, cargo.id)
        if not ok:
            await interaction.response.send_message("NÃ£o achei nenhum formulÃ¡rio com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(f"âœ… {cargo.mention} agora recebe candidaturas desse formulÃ¡rio.", ephemeral=True)

    @app_commands.command(name="formulario-cargo-remover", description="Remove um cargo da lista de notificaÃ§Ã£o de um formulÃ¡rio.")
    @app_commands.describe(formulario_id="ID do formulÃ¡rio", cargo="Cargo a remover")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_cargo_remover(self, interaction: discord.Interaction, formulario_id: str, cargo: discord.Role):
        ok = await formularios.remover_cargo_notificar(interaction.guild.id, formulario_id, cargo.id)
        if not ok:
            await interaction.response.send_message("NÃ£o achei nenhum formulÃ¡rio com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(f"âœ… {cargo.mention} nÃ£o recebe mais candidaturas desse formulÃ¡rio.", ephemeral=True)

    @app_commands.command(name="formulario-painel", description="Publica o painel de um formulÃ¡rio neste canal.")
    @app_commands.describe(formulario_id="ID do formulÃ¡rio (aparece em /formulario-listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_painel(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if not formulario:
            await interaction.response.send_message("NÃ£o achei nenhum formulÃ¡rio com esse ID.", ephemeral=True)
            return
        if not formulario["paginas"]:
            await interaction.response.send_message(
                "Esse formulÃ¡rio ainda nÃ£o tem nenhuma pergunta. Use `/formulario-pagina-adicionar` primeiro.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title=formulario["titulo_painel"], description=formulario["descricao_painel"], color=0x5865F2)
        if formulario["banner_url"]:
            embed.set_image(url=formulario["banner_url"])

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="Candidatar-se",
            style=discord.ButtonStyle.primary,
            emoji="ðŸ“",
            custom_id=f"{PREFIXO_ABRIR}{formulario_id}"
        ))
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("âœ… Painel publicado.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")

        if custom_id.startswith(PREFIXO_ABRIR):
            formulario_id = custom_id[len(PREFIXO_ABRIR):]
            formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
            if not formulario or not formulario["paginas"]:
                await interaction.response.send_message("Esse formulÃ¡rio nÃ£o existe mais ou nÃ£o tem perguntas.", ephemeral=True)
                return
            await interaction.response.send_modal(ModalFormulario(formulario))
            return

        if custom_id.startswith(PREFIXO_APROVAR) or custom_id.startswith(PREFIXO_RECUSAR):
            aprovado = custom_id.startswith(PREFIXO_APROVAR)
            resposta_id = custom_id.split(":")[-1]

            resposta, guild_encontrada = None, None
            for guild in self.bot.guilds:
                candidata = await formularios.get_resposta(guild.id, resposta_id)
                if candidata:
                    resposta, guild_encontrada = candidata, guild
                    break

            if not resposta:
                await interaction.response.send_message("Essa candidatura nÃ£o existe mais.", ephemeral=True)
                return
            if resposta["status"] != "pendente":
                await interaction.response.send_message(f"Essa candidatura jÃ¡ foi **{resposta['status']}**.", ephemeral=True)
                return

            novo_status = "aprovada" if aprovado else "recusada"
            await formularios.definir_status_resposta(guild_encontrada.id, resposta_id, novo_status, interaction.user.id)

            embed = interaction.message.embeds[0]
            embed.color = 0x57F287 if aprovado else 0xED4245
            embed.add_field(
                name="DecisÃ£o",
                value=f"{'âœ… Aprovado' if aprovado else 'âŒ Recusado'} por {interaction.user.mention}",
                inline=False,
            )
            await interaction.response.edit_message(embed=embed, view=None)

            candidato = guild_encontrada.get_member(resposta["autor_id"])
            if candidato:
                try:
                    texto = "ðŸŽ‰ Sua candidatura foi **aprovada**!" if aprovado else "âŒ Sua candidatura foi recusada."
                    await candidato.send(f"{texto} (servidor: {guild_encontrada.name})")
                except discord.Forbidden:
                    pass

