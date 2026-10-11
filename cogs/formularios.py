import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import formularios
from utils.storage import carregar, salvar

PREFIXO_ABRIR = "formulario:abrir:"
PREFIXO_APROVAR = "formulario:aprovar:"
PREFIXO_RECUSAR = "formulario:recusar:"
PREFIXO_CONTINUAR = "formulario:continuar:"
SESSOES_FORMULARIOS = {}
CANAL_PAINEIS_FORMULARIOS = 1545835428530360401
ARQUIVO_PAINEIS_DISCORD = "formularios_discord.json"
GUILD_NEMESIS_ID = 1543381737961160910


def _paginas_modal(formulario: dict) -> list:
    """Divide cada etapa do site em blocos de até cinco perguntas (limite do Discord)."""
    resultado = []
    for indice, pagina in enumerate(formulario.get("paginas") or [], start=1):
        if isinstance(pagina, dict):
            perguntas = pagina.get("perguntas") or []
            titulo = pagina.get("titulo") or f"Etapa {indice}"
        else:
            perguntas = pagina if isinstance(pagina, list) else []
            titulo = f"Etapa {indice}"
        for inicio in range(0, len(perguntas), 5):
            resultado.append({
                "titulo": titulo,
                "perguntas": perguntas[inicio:inicio + 5],
            })
    return resultado


def _perguntas_pagina(formulario: dict, indice: int) -> list:
    paginas = _paginas_modal(formulario)
    if not 0 <= indice < len(paginas):
        return []
    return paginas[indice]["perguntas"]


def _texto_pergunta(pergunta) -> str:
    if isinstance(pergunta, dict):
        return str(pergunta.get("texto") or pergunta.get("pergunta") or "Pergunta")
    return str(pergunta)


def _perguntas_flat(formulario: dict) -> list:
    return [
        pergunta
        for pagina in _paginas_modal(formulario)
        for pergunta in pagina["perguntas"]
    ]


def _embeds_painel(formulario: dict) -> list[discord.Embed]:
    """Monta todas as partes da descrição sem descartar texto acima do limite do Discord."""
    titulo = str(formulario.get("titulo_painel") or formulario.get("nome") or "Formulário")[:256]
    descricao = str(
        formulario.get("descricao_painel")
        or "Leia as informações e envie sua candidatura pelo botão abaixo."
    ).strip() or "Leia as informações e envie sua candidatura pelo botão abaixo."

    # O Discord limita a descrição de cada embed a 4.096 caracteres.
    # Dividimos em blocos menores e publicamos cada parte em uma mensagem própria.
    limite = 3800
    partes = []
    restante = descricao
    while restante:
        if len(restante) <= limite:
            partes.append(restante)
            break
        corte = restante.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = restante.rfind(" ", 0, limite)
        if corte < limite // 2:
            corte = limite
        partes.append(restante[:corte].rstrip())
        restante = restante[corte:].lstrip()

    if not partes:
        partes = ["Leia as informações e envie sua candidatura pelo botão abaixo."]

    embeds = []
    for indice, parte in enumerate(partes, start=1):
        titulo_parte = titulo if indice == 1 else f"{titulo[:230]} (continuação {indice}/{len(partes)})"
        embed = discord.Embed(title=titulo_parte, description=parte, color=0x5865F2)
        if indice == 1 and formulario.get("banner_url"):
            embed.set_image(url=str(formulario["banner_url"]))
        embed.set_footer(text=f"NÊMESIS • Formulário sincronizado com o site • {indice}/{len(partes)}")
        embeds.append(embed)
    return embeds

def _view_painel(formulario: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    ativo = formulario.get("ativo") is not False
    tem_perguntas = bool(_perguntas_flat(formulario))
    view.add_item(discord.ui.Button(
        label="Preencher formulário", style=discord.ButtonStyle.primary, emoji="📝",
        custom_id=f"{PREFIXO_ABRIR}{formulario.get('id', '')}",
        disabled=(not ativo or not tem_perguntas),
    ))
    return view


class ModalFormulario(discord.ui.Modal):
    """Modal de UMA página do formulário (até 5 perguntas, limite do
    Discord). Ao enviar, se ainda houver mais páginas, abre a próxima
    automaticamente — encadeando os modais até completar o formulário
    inteiro. As respostas vão sendo acumuladas de página em página."""

    def __init__(self, formulario: dict, pagina_indice: int = 0, respostas_acumuladas: list = None, usuario_id: int = None):
        pagina = _perguntas_pagina(formulario, pagina_indice)
        total_paginas = len(_paginas_modal(formulario))
        titulo = str(formulario.get("nome") or formulario.get("titulo_painel") or "Formulário")[:34]
        if total_paginas > 1:
            titulo = f"{titulo} ({pagina_indice + 1}/{total_paginas})"[:45]
        super().__init__(title=titulo)

        self.formulario = formulario
        self.pagina_indice = pagina_indice
        self.respostas_acumuladas = respostas_acumuladas or []
        self.usuario_id = usuario_id
        self.inputs = []
        for pergunta in pagina[:5]:
            texto = _texto_pergunta(pergunta)
            obrigatoria = pergunta.get("obrigatoria", True) if isinstance(pergunta, dict) else True
            opcoes = pergunta.get("opcoes") or [] if isinstance(pergunta, dict) else []
            placeholder = None
            if isinstance(pergunta, dict) and pergunta.get("tipo") == "escolha" and opcoes:
                placeholder = ("Escolha uma opção: " + " | ".join(str(opcao) for opcao in opcoes))[:100]
            campo = discord.ui.TextInput(label=texto[:45], style=discord.TextStyle.paragraph,
                                          required=bool(obrigatoria), max_length=1000,
                                          placeholder=placeholder)
            self.inputs.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        respostas_desta_pagina = [str(campo.value) for campo in self.inputs]
        todas_respostas = self.respostas_acumuladas + respostas_desta_pagina

        proxima_pagina = self.pagina_indice + 1
        guild_id = interaction.guild.id if interaction.guild else int(self.formulario.get("guild_id") or GUILD_NEMESIS_ID)
        chave = (int(guild_id), int(interaction.user.id), str(self.formulario["id"]))
        if proxima_pagina < len(_paginas_modal(self.formulario)):
            SESSOES_FORMULARIOS[chave] = {
                "formulario": self.formulario,
                "respostas": todas_respostas,
            }
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(
                label=f"Continuar para etapa {proxima_pagina + 1}",
                style=discord.ButtonStyle.primary,
                custom_id=f"{PREFIXO_CONTINUAR}{self.formulario['id']}:{proxima_pagina}:{interaction.user.id}",
            ))
            await interaction.response.send_message(
                f"Etapa {self.pagina_indice + 1} concluída. Continue para responder às próximas perguntas.",
                view=view,
                ephemeral=True,
            )
            return

        SESSOES_FORMULARIOS.pop(chave, None)
        guild = interaction.guild or interaction.client.get_guild(int(guild_id))
        if guild is None:
            await interaction.response.send_message(
                "Não consegui identificar o servidor desta candidatura. Tente novamente pelo canal do formulário.",
                ephemeral=True,
            )
            return
        cog = interaction.client.get_cog("Formularios")
        resposta = await formularios.criar_resposta(guild.id, self.formulario["id"],
                                                      interaction.user.id, todas_respostas)
        await cog.notificar_cargos(guild, self.formulario, resposta)
        await interaction.response.send_message("✅ Sua candidatura foi enviada!", ephemeral=True)


def _embed_resposta(formulario: dict, resposta: dict, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(title=f"📥 Nova candidatura — {formulario['nome']}", color=0x5865F2)
    embed.add_field(name="Candidato", value=f"<@{resposta['autor_id']}>", inline=False)
    perguntas = [_texto_pergunta(pergunta) for pergunta in _perguntas_flat(formulario)]
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
        self.sincronizar_paineis.start()

    def cog_unload(self):
        self.sincronizar_paineis.cancel()

    @tasks.loop(seconds=60)
    async def sincronizar_paineis(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            return
        canal = guild.get_channel(CANAL_PAINEIS_FORMULARIOS)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_PAINEIS_FORMULARIOS)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        lista = await formularios.listar_formularios(guild.id)
        lista = [item for item in lista if isinstance(item, dict) and item.get("id")]
        dados_paineis = await carregar(ARQUIVO_PAINEIS_DISCORD, {})
        if not isinstance(dados_paineis, dict):
            dados_paineis = {}
        registros = dados_paineis.setdefault(str(guild.id), {})
        ids_atuais = {str(item["id"]) for item in lista}

        for item in lista:
            formulario_id = str(item["id"])
            registro = registros.get(formulario_id, {})
            embeds = _embeds_painel(item)
            view = _view_painel(item)

            # Compatibilidade com o formato antigo (um único message_id).
            ids_mensagens = []
            if isinstance(registro, dict):
                ids_mensagens = registro.get("message_ids") or []
                if not ids_mensagens and registro.get("message_id"):
                    ids_mensagens = [registro["message_id"]]

            mensagens = []
            for indice, embed in enumerate(embeds):
                mensagem = None
                if indice < len(ids_mensagens):
                    try:
                        mensagem = await canal.fetch_message(int(ids_mensagens[indice]))
                    except discord.NotFound:
                        mensagem = None
                    except (discord.Forbidden, discord.HTTPException):
                        continue

                try:
                    if mensagem is None:
                        mensagem = await canal.send(
                            embed=embed,
                            view=view if indice == 0 else None,
                        )
                    else:
                        await mensagem.edit(
                            embed=embed,
                            view=view if indice == 0 else None,
                        )
                    mensagens.append(int(mensagem.id))
                except (discord.Forbidden, discord.HTTPException):
                    # Não apaga registros antigos se o Discord recusar a operação.
                    mensagens = []
                    break

            if not mensagens:
                continue

            # Remove mensagens excedentes se a descrição ficou menor após uma edição.
            for id_antigo in ids_mensagens[len(embeds):]:
                try:
                    antiga = await canal.fetch_message(int(id_antigo))
                    await antiga.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

            registros[formulario_id] = {
                "channel_id": int(canal.id),
                "message_id": mensagens[0],
                "message_ids": mensagens,
            }

        for formulario_id in list(registros):
            if formulario_id in ids_atuais:
                continue
            registro = registros.get(formulario_id, {})
            if isinstance(registro, dict) and registro.get("message_id"):
                try:
                    mensagem = await canal.fetch_message(int(registro["message_id"]))
                    await mensagem.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            registros.pop(formulario_id, None)

        await salvar(ARQUIVO_PAINEIS_DISCORD, dados_paineis)

    @sincronizar_paineis.before_loop
    async def antes_de_sincronizar_paineis(self):
        await self.bot.wait_until_ready()

    async def notificar_cargos(self, guild: discord.Guild, formulario: dict, resposta: dict):
        embed = _embed_resposta(formulario, resposta, guild)
        view = _view_resposta(resposta["id"])

        # Publica todas as candidaturas no canal fixo da NÊMESIS.
        canal_candidaturas = guild.get_channel(1545835428530360401)
        if canal_candidaturas is None:
            try:
                canal_candidaturas = await guild.fetch_channel(1545835428530360401)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal_candidaturas = None
        if canal_candidaturas is not None:
            try:
                await canal_candidaturas.send(embed=embed, view=view)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Mantém também as notificações por DM para os cargos configurados.
        notificados = set()
        for cargo_id in formulario["cargos_notificar"]:
            try:
                cargo_id_int = int(cargo_id)
            except (TypeError, ValueError):
                continue
            cargo = guild.get_role(cargo_id_int)
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
            perguntas_pagina = pagina.get("perguntas", []) if isinstance(pagina, dict) else pagina
            perguntas_texto = "\n".join(
                f"  {j}. {_texto_pergunta(p)}" for j, p in enumerate(perguntas_pagina, start=1)
            )
            titulo_pagina = pagina.get("titulo") if isinstance(pagina, dict) else f"Página {i}"
            blocos.append(f"**{titulo_pagina or f'Página {i}'}**\n{perguntas_texto}")
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

        if custom_id.startswith(PREFIXO_CONTINUAR):
            if interaction.guild is None:
                await interaction.response.send_message("Abra a continuação no servidor da NÊMESIS.", ephemeral=True)
                return
            partes = custom_id[len(PREFIXO_CONTINUAR):].rsplit(":", 2)
            if len(partes) != 3:
                await interaction.response.send_message("Este botão de continuação é inválido.", ephemeral=True)
                return
            formulario_id, indice_texto, usuario_texto = partes
            try:
                indice = int(indice_texto)
                usuario_id = int(usuario_texto)
            except ValueError:
                await interaction.response.send_message("Este botão de continuação é inválido.", ephemeral=True)
                return
            if interaction.user.id != usuario_id:
                await interaction.response.send_message("Somente a pessoa que iniciou o formulário pode continuar.", ephemeral=True)
                return
            chave = (interaction.guild.id, interaction.user.id, formulario_id)
            sessao = SESSOES_FORMULARIOS.get(chave)
            if not sessao:
                await interaction.response.send_message("Sua sessão de formulário expirou. Abra o formulário novamente.", ephemeral=True)
                return
            await interaction.response.send_modal(
                ModalFormulario(sessao["formulario"], indice, sessao["respostas"], usuario_id=interaction.user.id)
            )
            return

        if custom_id.startswith(PREFIXO_ABRIR):
            if interaction.guild is None:
                await interaction.response.send_message("Abra este formulário no servidor da NÊMESIS.", ephemeral=True)
                return
            formulario_id = custom_id[len(PREFIXO_ABRIR):]
            formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
            if not formulario or not _perguntas_flat(formulario) or formulario.get("ativo") is False:
                await interaction.response.send_message("Esse formulário não está disponível ou ainda não tem perguntas.", ephemeral=True)
                return
            await interaction.response.send_modal(ModalFormulario(formulario, usuario_id=interaction.user.id))
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