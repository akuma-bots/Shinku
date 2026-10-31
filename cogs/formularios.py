import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import criar_embed, aplicar_identidade_servidor
from utils.storage import carregar, salvar

from utils import formularios

PREFIXO_ABRIR = "formulario:abrir:"
PREFIXO_APROVAR = "formulario:aprovar:"
PREFIXO_RECUSAR = "formulario:recusar:"
PREFIXO_CONTINUAR = "formulario:continuar:"
SESSOES_FORMULARIOS = {}
TEMPO_SESSAO_FORMULARIO = 15 * 60
LIMITE_SESSOES_FORMULARIO = 5000
CANAL_PAINEIS_FORMULARIOS = 1545835428530360401


def _limpar_sessoes_formularios(agora: float | None = None) -> None:
    """Remove sessões abandonadas e limita o uso de memória do processo."""
    agora = time.time() if agora is None else agora
    expiracao = agora - TEMPO_SESSAO_FORMULARIO

    for chave, sessao in list(SESSOES_FORMULARIOS.items()):
        try:
            atualizado = float(sessao.get("atualizado_em", 0))
        except (AttributeError, TypeError, ValueError):
            atualizado = 0
        if atualizado < expiracao:
            SESSOES_FORMULARIOS.pop(chave, None)

    if len(SESSOES_FORMULARIOS) > LIMITE_SESSOES_FORMULARIO:
        ordenadas = sorted(
            SESSOES_FORMULARIOS.items(),
            key=lambda item: float(item[1].get("atualizado_em", 0)),
        )
        excesso = len(SESSOES_FORMULARIOS) - LIMITE_SESSOES_FORMULARIO
        for chave, _ in ordenadas[:excesso]:
            SESSOES_FORMULARIOS.pop(chave, None)
GUILD_NEMESIS_ID = 1563995879981981817
CARGOS_AUTORIZADOS_FORMULARIO_STAFF = {1547306211458940968, 1547306457526181939}
CARGO_INSTRUTOR_FORMULARIO_ID = 1558909311315607723
NOME_FORMULARIO_STAFF = "Inscrição para Staff"
_LOCK_PAINÉIS_AUTOMÁTICOS = asyncio.Lock()
ARQUIVO_PAINÉIS_AUTOMÁTICOS = "paineis_formularios_automaticos.json"

FORMULARIOS_AUTOMATICOS = [
    {
        "chave": "staff",
        "nome": "Inscrição para Staff",
        "titulo": "NÊMESIS — RECRUTAMENTO STAFF",
        "descricao": (
            "CENTRAL DE RECRUTAMENTO • EQUIPE NÊMESIS\n\n"
            "Use este formulário para se candidatar à equipe. Responda com clareza e sinceridade; "
            "candidaturas incompletas ou com informações falsas poderão ser recusadas.\n\n"
            "REQUISITOS\n"
            "— Conhecer e respeitar as regras da NÊMESIS.\n"
            "— Ter postura respeitosa, responsabilidade e maturidade.\n"
            "— Conseguir agir com imparcialidade em conflitos.\n"
            "— Ter disponibilidade para auxiliar a comunidade.\n\n"
            "O envio não garante aprovação. A equipe analisará sua candidatura."
        ),
        "canal_id": 1563995880623841338,
        "paginas": [[
            "Qual é o seu nome ou apelido e qual é seu usuário do Discord?",
            "Por que deseja fazer parte da Staff da NÊMESIS?",
            "Qual é sua disponibilidade semanal para ajudar no servidor?",
            "Você já teve experiência com moderação ou organização? Explique.",
            "Como agiria se dois membros começassem uma discussão séria?"
        ], [
            "Quais são seus principais pontos fortes para atuar na equipe?",
            "Em quais áreas da NÊMESIS você acredita que poderia contribuir melhor?",
            "Como reagiria se um membro desrespeitasse uma regra mesmo após ser alertado?",
            "O que faria se um amigo próximo cometesse uma infração?",
            "Como lidaria com uma situação em que não soubesse qual decisão tomar?"
        ], [
            "Como você organiza seu tempo para cumprir responsabilidades?",
            "O que faria ao perceber um problema importante enquanto nenhum líder está online?",
            "Como receberia uma crítica da liderança sobre seu trabalho?",
            "Na sua opinião, o que caracteriza uma postura imparcial dentro da Staff?",
            "Existe algo mais sobre sua experiência ou disponibilidade que queira acrescentar?"
        ]],
    },
]


def _paginas_modal(formulario: dict) -> list:
    """Divide as páginas em blocos de até cinco perguntas (limite dos modais do Discord)."""
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


def _embeds_painel(formulario: dict, guild: discord.Guild | None = None, bot: discord.Client | None = None) -> list[discord.Embed]:
    """Painel institucional dividido automaticamente dentro dos limites do Discord."""
    titulo = str(formulario.get("titulo_painel") or formulario.get("nome") or "Formulário")[:220]
    descricao = str(formulario.get("descricao_painel") or "").strip() or "Leia as orientações e preencha todas as etapas com atenção."
    limite = 3000
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
        partes.append(restante[:corte])
        restante = restante[corte:].lstrip()
    if not partes:
        partes = [descricao]
    perguntas = _perguntas_flat(formulario)
    total_etapas = len(_paginas_modal(formulario))
    estado = "🟢 RECEBENDO CANDIDATURAS" if formulario.get("ativo") is not False and not formulario.get("arquivado") else "⚫ FORMULÁRIO ARQUIVADO" if formulario.get("arquivado") else "🟠 INSCRIÇÕES PAUSADAS"
    embeds = []
    for indice, parte in enumerate(partes, start=1):
        texto = (
            "╭━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━╮\n"
            "　　　 **CENTRAL DE CANDIDATURAS**\n"
            "╰━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━╯\n\n"
            f"{parte}\n\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
            "**PROTOCOLO DE INSCRIÇÃO**\n"
            "① Selecione **Iniciar inscrição**.\n"
            "② Responda com informações verdadeiras e completas.\n"
            "③ Conclua todas as etapas e aguarde a avaliação.\n"
            "④ O retorno será enviado por mensagem privada.\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
        )
        sufixo = f" • {indice}/{len(partes)}" if len(partes) > 1 else ""
        embed = criar_embed(f"✦・ {titulo} ・✦{sufixo}", texto[:4096], cor=0x9F1239, rodape=f"N̷ÊMESIS  •  PROCESSO SELETIVO  •  {estado}")
        embed.set_author(name="N̷ÊMESIS  /  DEPARTAMENTO DE RECRUTAMENTO")
        if indice == 1:
            embed.add_field(name="SITUAÇÃO", value=estado, inline=True)
            embed.add_field(name="ETAPAS", value=f"{total_etapas:02d}", inline=True)
            embed.add_field(name="QUESTÕES", value=f"{len(perguntas):02d}", inline=True)
            if formulario.get("banner_url"):
                embed.set_image(url=str(formulario["banner_url"]))
        aplicar_identidade_servidor(embed, guild, bot, banner=(indice == 1 and not bool(formulario.get("banner_url"))))
        embeds.append(embed)
    return embeds


def _formularios_disponiveis(lista: list) -> list:
    return [item for item in lista if isinstance(item, dict) and item.get("id")
            and item.get("ativo", True) is not False and not item.get("arquivado")
            and _perguntas_flat(item)]


def _embed_central_inscricoes(lista: list, guild: discord.Guild, bot: discord.Client) -> discord.Embed:
    disponiveis = _formularios_disponiveis(lista)
    linhas = [
        f"**{i:02d}.** {item.get('nome', 'Formulário')}  ·  "
        f"{len(_perguntas_flat(item))} questões  ·  {len(_paginas_modal(item))} etapas"
        for i, item in enumerate(disponiveis[:25], start=1)
    ]
    corpo = "\n".join(linhas) if linhas else "No momento, não há inscrições abertas."
    orientacao = ("Selecione no menu abaixo o processo seletivo desejado para iniciar sua inscrição."
                  if linhas else "Novos processos seletivos serão disponibilizados aqui quando forem ativados.")
    embed = criar_embed(
        "✦・ CENTRAL DE INSCRIÇÕES ・✦",
        "╭━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━╮\n"
        "　　　 **N̷ÊMESIS  /  RECRUTAMENTO**\n"
        "╰━━━━━━━━━━━━━━ ◈ ━━━━━━━━━━━━━━╯\n\n"
        "Acesse os processos seletivos disponíveis em um único lugar. "
        "Cada formulário possui suas próprias etapas e perguntas.\n\n"
        "**PROCESSOS DISPONÍVEIS**\n"
        f"{corpo}\n\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        f"{orientacao}\n"
        "Responda com atenção e aguarde a avaliação da comissão responsável.\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
        cor=0x9F1239,
        rodape=f"N̷ÊMESIS  •  CENTRAL DE RECRUTAMENTO  •  {len(disponiveis)} inscrição(ões) aberta(s)",
    )
    embed.set_author(name="N̷ÊMESIS  /  DEPARTAMENTO DE RECRUTAMENTO")
    aplicar_identidade_servidor(embed, guild, bot, banner=True)
    return embed


class SeletorInscricaoPublico(discord.ui.Select):
    def __init__(self, lista: list):
        disponiveis = _formularios_disponiveis(lista)
        opcoes = [
            discord.SelectOption(
                label=str(item.get("nome") or "Formulário")[:100],
                value=str(item["id"]),
                description=f"{len(_perguntas_flat(item))} questões • {len(_paginas_modal(item))} etapas"[:100],
                emoji="📋",
            )
            for item in disponiveis[:25]
        ]
        if not opcoes:
            opcoes = [discord.SelectOption(label="Nenhuma inscrição disponível", value="indisponivel",
                                           description="Aguarde a abertura de um processo seletivo.")]
        super().__init__(placeholder="Selecione o formulário que deseja preencher",
                         min_values=1, max_values=1, options=opcoes,
                         disabled=not bool(disponiveis),
                         custom_id="nemesis:formularios:seletor_publico")

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Este seletor só pode ser utilizado dentro do servidor da NÊMESIS.", ephemeral=True)
            return
        formulario_id = self.values[0]
        if formulario_id == "indisponivel":
            await interaction.response.send_message("Não há inscrições abertas no momento.", ephemeral=True)
            return
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if (not formulario or formulario.get("ativo", True) is False
                or formulario.get("arquivado") or not _perguntas_flat(formulario)):
            await interaction.response.send_message("Este formulário não está mais disponível. Atualize a central e tente novamente.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalFormulario(formulario, usuario_id=interaction.user.id))


def _view_central_inscricoes(lista: list) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(SeletorInscricaoPublico(lista))
    return view

def _view_painel(formulario: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    ativo = formulario.get("ativo") is not False
    tem_perguntas = bool(_perguntas_flat(formulario))
    view.add_item(discord.ui.Button(
        label="Iniciar inscrição", style=discord.ButtonStyle.primary,
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
            # O Discord limita o rótulo de cada campo a 45 caracteres.
            # Usamos um rótulo curto e reservamos o placeholder para exibir
            # o enunciado da questão, evitando cortar perguntas longas no modal.
            rotulo = f"Questão {len(self.inputs) + 1:02d} • Resposta"
            placeholder = texto[:100] or "Digite sua resposta..."
            campo = discord.ui.TextInput(
                label=rotulo,
                style=discord.TextStyle.paragraph,
                required=bool(obrigatoria),
                max_length=1000,
                placeholder=placeholder,
            )
            self.inputs.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        respostas_desta_pagina = [str(campo.value) for campo in self.inputs]
        todas_respostas = self.respostas_acumuladas + respostas_desta_pagina

        proxima_pagina = self.pagina_indice + 1
        guild_id = interaction.guild.id if interaction.guild else int(self.formulario.get("guild_id") or GUILD_NEMESIS_ID)
        chave = (int(guild_id), int(interaction.user.id), str(self.formulario["id"]))
        if proxima_pagina < len(_paginas_modal(self.formulario)):
            _limpar_sessoes_formularios()
            SESSOES_FORMULARIOS[chave] = {
                "formulario": self.formulario,
                "respostas": todas_respostas,
                "atualizado_em": time.time(),
            }
            _limpar_sessoes_formularios()
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
        # Impede candidaturas duplicadas enquanto uma análise anterior estiver pendente.
        pendentes = await formularios.listar_respostas(
            guild.id, formulario_id=self.formulario["id"], status="pendente"
        )
        if any(int(item.get("autor_id", 0)) == interaction.user.id for item in pendentes):
            await interaction.response.send_message(
                "Você já possui uma candidatura pendente para este formulário. Aguarde a avaliação da equipe.",
                ephemeral=True,
            )
            return

        # A publicação no canal e as DMs podem levar mais que o prazo inicial
        # da interação; defer evita que o Discord mostre falha na interação.
        await interaction.response.defer(ephemeral=True, thinking=True)
        resposta = await formularios.criar_resposta(
            guild.id,
            self.formulario["id"],
            interaction.user.id,
            todas_respostas,
            autor_nome=getattr(interaction.user, "global_name", None)
            or interaction.user.display_name,
        )
        cog = interaction.client.get_cog("Formularios")
        if cog is not None:
            await cog.notificar_cargos(guild, self.formulario, resposta)
        await interaction.followup.send(
            embed=criar_embed(
                "✦・ INSCRIÇÃO RECEBIDA ・✦",
                (
                    "Sua candidatura foi protocolada com sucesso e encaminhada à comissão responsável.\n\n"
                    f"**PROTOCOLO**　{resposta['id']}\n"
                    "**SITUAÇÃO**　🟠 Em análise\n\n"
                    "Você receberá uma mensagem privada quando houver uma decisão. "
                    "Evite enviar outra candidatura enquanto esta estiver pendente."
                ),
                cor=0x9F1239,
                rodape="N̷ÊMESIS  •  CENTRAL DE RECRUTAMENTO",
            ),
            ephemeral=True,
        )


def _embeds_resposta(formulario: dict, resposta: dict, guild: discord.Guild, bot: discord.Client | None = None) -> list[discord.Embed]:
    """Apresenta a candidatura como dossiê de avaliação, respeitando limites do Discord."""
    titulo = f"DOSSIÊ DE CANDIDATURA  /  {formulario.get('nome') or 'FORMULÁRIO'}"
    perguntas = [_texto_pergunta(pergunta) for pergunta in _perguntas_flat(formulario)]
    respostas = resposta.get("respostas") or []
    pares = list(zip(perguntas, respostas))
    blocos = [pares[i:i + 20] for i in range(0, len(pares), 20)] or [[]]
    embeds = []
    for indice, bloco in enumerate(blocos, start=1):
        embed = criar_embed(
            f"✦・ {titulo[:210]} ・✦",
            "╭────────────── ◈ ──────────────╮\n"
            "　　　 **ANÁLISE RESTRITA**\n"
            "╰────────────── ◈ ──────────────╯\n\n"
            f"**CANDIDATO**\n<@{resposta['autor_id']}>  •  {str(resposta.get('nome') or 'Membro')[:70]}\n"
            f"**PROTOCOLO**　{resposta['id']}\n"
            "**SITUAÇÃO**　🟠 AGUARDANDO AVALIAÇÃO\n"
            f"**DOCUMENTO**　{indice:02d}/{len(blocos):02d}",
            cor=0x9F1239, rodape=f"N̷ÊMESIS  •  ACESSO RESTRITO  •  {guild.name}",
        )
        embed.set_author(name="N̷ÊMESIS  /  COMISSÃO AVALIADORA")
        for numero, (pergunta, resp) in enumerate(bloco, start=(indice - 1) * 20 + 1):
            valor = str(resp if resp is not None else "—").strip() or "—"
            embed.add_field(name=f"〔 {numero:02d} 〕 {str(pergunta or 'Questão')[:245]}", value=valor[:1024], inline=False)
        aplicar_identidade_servidor(embed, guild, bot, banner=False)
        embeds.append(embed)
    return embeds

def _view_resposta(resposta_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success, emoji="✅",
                                     custom_id=f"{PREFIXO_APROVAR}{resposta_id}"))
    view.add_item(discord.ui.Button(label="Recusar", style=discord.ButtonStyle.danger, emoji="❌",
                                     custom_id=f"{PREFIXO_RECUSAR}{resposta_id}"))
    return view



class SeletorFormularioCentral(discord.ui.Select):
    def __init__(self, central):
        self.central = central
        opcoes = [
            discord.SelectOption(
                label=str(item.get("nome") or "Formulário")[:100],
                value=str(item.get("id", "")),
                description=(
                    f"{len(_perguntas_flat(item))} pergunta(s) • "
                    f"{'Arquivado' if item.get('arquivado') else 'Ativo' if item.get('ativo', True) else 'Pausado'}"
                )[:100],
                default=str(item.get("id", "")) == str(central.formulario_id),
            )
            for item in central.lista[:25] if item.get("id")
        ]
        super().__init__(placeholder="Selecione um formulário", min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.central.usuario_id:
            await interaction.response.send_message("Esta central pertence a outra pessoa.", ephemeral=True)
            return
        self.central.formulario_id = self.values[0]
        await self.central.atualizar(interaction)


class SeletorAcaoFormulario(discord.ui.Select):
    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Escolha uma ação para o formulário",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Atualizar central pública", value="publicar"),
                discord.SelectOption(label="Pausar inscrições", value="pausar"),
                discord.SelectOption(label="Reativar inscrições", value="reativar"),
                discord.SelectOption(label="Arquivar formulário", value="arquivar"),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        central = self.central
        if interaction.user.id != central.usuario_id:
            await interaction.response.send_message("Esta central pertence a outra pessoa.", ephemeral=True)
            return
        if interaction.guild is None or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Você precisa de permissão de Administrador.", ephemeral=True)
            return
        formulario = await formularios.get_formulario(interaction.guild.id, central.formulario_id)
        if not formulario:
            await interaction.response.send_message("O formulário selecionado não existe mais.", ephemeral=True)
            return
        acao = self.values[0]
        if acao == "publicar":
            if not _perguntas_flat(formulario):
                await interaction.response.send_message("Adicione perguntas antes de disponibilizar a inscrição.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                await central.cog.atualizar_central_inscricoes(interaction.guild)
            except (discord.Forbidden, discord.HTTPException, TypeError):
                logging.exception("Falha ao atualizar a central pública de inscrições.")
                await interaction.followup.send("Não consegui atualizar a central. Verifique as permissões do bot no canal de inscrições.", ephemeral=True)
                return
            await interaction.followup.send("Central pública de inscrições atualizada.", ephemeral=True)
            return
        if acao == "pausar":
            await formularios.atualizar_formulario(interaction.guild.id, central.formulario_id, ativo=False)
        elif acao == "reativar":
            await formularios.reativar_formulario(interaction.guild.id, central.formulario_id)
        elif acao == "arquivar":
            await formularios.remover_formulario(interaction.guild.id, central.formulario_id)
        await central.cog.atualizar_central_inscricoes(interaction.guild)
        await central.atualizar(interaction, mensagem=f"Ação aplicada: **{acao.upper()}**.")


class CentralFormulariosView(discord.ui.View):
    def __init__(self, cog, guild_id: int, usuario_id: int, lista: list, formulario_id: str | None = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.usuario_id = usuario_id
        self.lista = lista
        self.formulario_id = formulario_id or (str(lista[0].get("id")) if lista else None)
        self._montar_seletores()

    def _montar_seletores(self):
        self.clear_items()
        if self.lista:
            self.add_item(SeletorFormularioCentral(self))
            self.add_item(SeletorAcaoFormulario(self))

    def montar_embed(self, mensagem: str | None = None):
        formulario = next((item for item in self.lista if str(item.get("id")) == str(self.formulario_id)), None)
        if not formulario:
            return criar_embed("✦・ CENTRAL DE FORMULÁRIOS ・✦", "Nenhum formulário disponível.", cor=0x9F1239)
        status = "ARQUIVADO" if formulario.get("arquivado") else "ATIVO" if formulario.get("ativo", True) else "PAUSADO"
        corpo = (
            f"**FORMULÁRIO**\n{formulario.get('nome', 'Sem nome')}\n\n"
            f"**SITUAÇÃO**　{status}\n"
            f"**IDENTIFICADOR**　{formulario.get('id')}\n"
            f"**ETAPAS**　{len(_paginas_modal(formulario)):02d}\n"
            f"**PERGUNTAS**　{len(_perguntas_flat(formulario)):02d}\n"
            f"**CARGOS NOTIFICADOS**　{len(formulario.get('cargos_notificar', [])):02d}"
        )
        if mensagem:
            corpo += f"\n\n{mensagem}"
        return criar_embed(
            "✦・ CENTRAL DE FORMULÁRIOS — NÊMESIS ・✦",
            "╭────────────── ◈ ──────────────╮\n"
            "　　　 **GESTÃO DE PROCESSOS SELETIVOS**\n"
            "╰────────────── ◈ ──────────────╯\n\n"
            + corpo + "\n\nSelecione um formulário ou escolha uma ação nos menus abaixo.",
            cor=0x9F1239,
            rodape="N̷ÊMESIS  •  ADMINISTRAÇÃO DE FORMULÁRIOS",
        )

    async def atualizar(self, interaction: discord.Interaction, mensagem: str | None = None):
        self.lista = await formularios.listar_formularios(self.guild_id)
        if not any(str(item.get("id")) == str(self.formulario_id) for item in self.lista):
            self.formulario_id = str(self.lista[0].get("id")) if self.lista else None
        self._montar_seletores()
        await interaction.response.edit_message(embed=self.montar_embed(mensagem), view=self)


class Formularios(commands.GroupCog, group_name="formularios", group_description="Gerenciamento dos formulários da NÊMESIS"):
    """Sistema de formulários/candidaturas por páginas: cada formulário tem
    seu painel customizável (título, descrição, banner) e é dividido em
    páginas de até 5 perguntas — o bot encadeia os modais automaticamente
    até completar todas. As respostas vão por DM pros cargos configurados,
    com botões de Aprovar/Recusar; o candidato é avisado do resultado."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._view_inscricoes_registrada = False

    @app_commands.command(name="central", description="Abre a central interativa de administração dos formulários.")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_central(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro da NÊMESIS.", ephemeral=True)
            return
        lista = await formularios.listar_formularios(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Ainda não existem formulários cadastrados.", ephemeral=True)
            return
        lista.sort(key=lambda item: (bool(item.get("arquivado")), str(item.get("nome", "")).casefold()))
        view = CentralFormulariosView(self, interaction.guild.id, interaction.user.id, lista)
        await interaction.response.send_message(embed=view.montar_embed(), view=view, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """Garante o formulário automático de Staff e mantém uma central pública única."""
        async with _LOCK_PAINÉIS_AUTOMÁTICOS:
            guild = self.bot.get_guild(GUILD_NEMESIS_ID)
            if guild is None:
                logging.warning("Central de inscrições: servidor NÊMESIS não está disponível.")
                return
            for definicao in FORMULARIOS_AUTOMATICOS:
                try:
                    lista = await formularios.listar_formularios(guild.id)
                    formulario = next((item for item in lista if item.get("nome") == definicao["nome"]), None)
                    if formulario is None:
                        formulario = await formularios.criar_formulario(
                            guild.id, definicao["nome"], definicao["titulo"],
                            definicao["descricao"], None, self.bot.user.id if self.bot.user else 0,
                        )
                    if not formularios.perguntas_flat(formulario):
                        for perguntas in definicao["paginas"]:
                            formulario = await formularios.adicionar_pagina(guild.id, formulario["id"], perguntas)
                            if formulario is None:
                                raise RuntimeError(f"Não foi possível configurar perguntas para {definicao['nome']}.")
                except Exception:
                    logging.exception("Erro ao configurar o formulário automático %s.", definicao["nome"])
            try:
                await self.atualizar_central_inscricoes(guild)
            except Exception:
                logging.exception("Não foi possível atualizar a central pública de inscrições.")

    async def atualizar_central_inscricoes(self, guild: discord.Guild):
        """Cria/atualiza a central única, reaproveitando a mensagem antiga do painel Staff."""
        canal_id = 1563995880623841338
        canal = guild.get_channel(canal_id)
        if canal is None:
            canal = await guild.fetch_channel(canal_id)
        if not callable(getattr(canal, "send", None)):
            raise TypeError(f"O canal {canal_id} não aceita mensagens.")
        estado = await carregar(ARQUIVO_PAINÉIS_AUTOMÁTICOS, {})
        estado = estado if isinstance(estado, dict) else {}
        registro = estado.get("central_inscricoes") or estado.get("staff") or {}
        mensagem_existente = None
        if registro.get("canal_id") == canal_id and registro.get("mensagem_id"):
            try:
                mensagem_existente = await canal.fetch_message(int(registro["mensagem_id"]))
            except discord.NotFound:
                mensagem_existente = None
        lista = await formularios.listar_formularios(guild.id)
        embed = _embed_central_inscricoes(lista, guild, self.bot)
        view = _view_central_inscricoes(lista)
        if mensagem_existente is not None:
            mensagem = await mensagem_existente.edit(embed=embed, view=view)
            acao = "atualizada"
        else:
            mensagem = await canal.send(embed=embed, view=view)
            acao = "publicada"
        estado.pop("staff", None)
        estado["central_inscricoes"] = {"canal_id": canal_id, "mensagem_id": mensagem.id, "tipo": "seletor_dinamico"}
        await salvar(ARQUIVO_PAINÉIS_AUTOMÁTICOS, estado)
        if not getattr(self, "_view_inscricoes_registrada", False):
            self.bot.add_view(_view_central_inscricoes(lista))
            self._view_inscricoes_registrada = True
        logging.info("Central pública de inscrições %s (canal=%s, mensagem=%s, disponíveis=%s).",
                     acao, canal_id, mensagem.id, len(_formularios_disponiveis(lista)))

    async def notificar_cargos(self, guild: discord.Guild, formulario: dict, resposta: dict):

        embeds = _embeds_resposta(formulario, resposta, guild, self.bot)
        view = _view_resposta(resposta["id"])

        # Publica todas as partes da candidatura; os botões ficam na primeira.
        canal_candidaturas = guild.get_channel(1545835428530360401)
        if canal_candidaturas is None:
            try:
                canal_candidaturas = await guild.fetch_channel(1545835428530360401)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal_candidaturas = None
        if canal_candidaturas is not None:
            for indice, embed in enumerate(embeds):
                try:
                    await canal_candidaturas.send(
                        embed=embed,
                        view=view if indice == 0 else None,
                    )
                except (discord.Forbidden, discord.HTTPException):
                    logging.exception("Falha ao publicar candidatura %s no canal.", resposta.get("id"))
                    break

        # Instrutores/aprovadores recebem todas as candidaturas por DM.
        cargos_notificar = list(formulario.get("cargos_notificar", []))
        if CARGO_INSTRUTOR_FORMULARIO_ID not in cargos_notificar:
            cargos_notificar.append(CARGO_INSTRUTOR_FORMULARIO_ID)

        notificados = set()
        for cargo_id in cargos_notificar:
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
                for indice, embed in enumerate(embeds):
                    try:
                        await membro.send(
                            embed=embed,
                            view=view if indice == 0 else None,
                        )
                    except discord.Forbidden:
                        break  # DM fechada — a pessoa simplesmente não recebe
                    except discord.HTTPException:
                        logging.exception("Falha ao enviar candidatura %s por DM.", resposta.get("id"))
                        break

    @app_commands.command(name="criar", description="Cria um formulário (painel). Adicione as páginas de perguntas depois.")
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
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.atualizar_central_inscricoes(interaction.guild)
        await interaction.followup.send(
            f"✅ Formulário **{nome}** criado (ID: `{formulario['id']}`). "
            f"Agora use `/formularios pagina-adicionar` pra adicionar as perguntas (até 5 por página, "
            f"quantas páginas quiser), depois `/formularios cargo-adicionar` e `/formularios painel`.",
            ephemeral=True,
        )

    @app_commands.command(name="pagina-adicionar", description="Adiciona uma página de perguntas (até 5) a um formulário.")
    @app_commands.describe(
        formulario_id="ID do formulário (aparece em /formularios listar)",
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
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.atualizar_central_inscricoes(interaction.guild)
        await interaction.followup.send(
            f"✅ Página {len(formulario['paginas'])} adicionada ({len(perguntas)} pergunta(s)). "
            f"Total agora: {len(formulario['paginas'])} página(s).", ephemeral=True,
        )

    @app_commands.command(name="pagina-remover", description="Remove uma página de um formulário.")
    @app_commands.describe(formulario_id="ID do formulário", numero_pagina="Número da página (1, 2, 3...) — veja em /formularios paginas-listar")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_pagina_remover(self, interaction: discord.Interaction, formulario_id: str, numero_pagina: int):
        ok = await formularios.remover_pagina(interaction.guild.id, formulario_id, numero_pagina - 1)
        if not ok:
            await interaction.response.send_message("Não achei essa página nesse formulário.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.atualizar_central_inscricoes(interaction.guild)
        await interaction.followup.send(f"🗑️ Página {numero_pagina} removida.", ephemeral=True)

    @app_commands.command(name="paginas-listar", description="Lista as páginas e perguntas de um formulário.")
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
        embed = criar_embed(f"📋 Páginas — {formulario['nome']}", "\n\n".join(blocos), rodape="NÊMESIS • Configuração de formulários")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="listar", description="Lista os formulários configurados.")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_listar(self, interaction: discord.Interaction):
        lista = await formularios.listar_formularios(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhum formulário criado ainda.", ephemeral=True)
            return
        linhas = [
            f"**{f['nome']}** (ID: `{f['id']}`) — "
            f"{'ARQUIVADO' if f.get('arquivado') else 'ATIVO' if f.get('ativo', True) else 'PAUSADO'}, "
            f"{len(f.get('paginas', []))} etapa(s), "
            f"{len(formularios.perguntas_flat(f))} pergunta(s), "
            f"{len(f.get('cargos_notificar', []))} cargo(s) notificado(s)"
            for f in lista
        ]
        embed = criar_embed("N̷ÊMESIS ━ CENTRAL DE FORMULÁRIOS", "\n".join(linhas), rodape="NÊMESIS • Administração de formulários")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remover", description="Remove um formulário.")
    @app_commands.describe(formulario_id="ID do formulário (aparece em /formularios listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_remover(self, interaction: discord.Interaction, formulario_id: str):
        ok = await formularios.remover_formulario(interaction.guild.id, formulario_id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.atualizar_central_inscricoes(interaction.guild)
        await interaction.followup.send(
            "✦ Formulário arquivado. O histórico de candidaturas foi preservado.",
            ephemeral=True,
        )

    @app_commands.command(name="reativar", description="Reabre um formulário arquivado ou pausado.")
    @app_commands.describe(formulario_id="ID do formulário")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_reativar(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if not formulario:
            await interaction.response.send_message("Não encontrei esse formulário.", ephemeral=True)
            return
        await formularios.reativar_formulario(interaction.guild.id, formulario_id)
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.atualizar_central_inscricoes(interaction.guild)
        await interaction.followup.send(
            f"✦ **{formulario.get('nome', 'Formulário')}** reativado e já está disponível no seletor de inscrições.",
            ephemeral=True,
        )

    @app_commands.command(name="pausar", description="Pausa inscrições sem arquivar o formulário.")
    @app_commands.describe(formulario_id="ID do formulário")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_pausar(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.atualizar_formulario(interaction.guild.id, formulario_id, ativo=False)
        if not formulario:
            await interaction.response.send_message("Não encontrei esse formulário.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.atualizar_central_inscricoes(interaction.guild)
        await interaction.followup.send(
            f"Inscrições de **{formulario.get('nome', 'Formulário')}** pausadas. O histórico foi preservado.",
            ephemeral=True,
        )

    @app_commands.command(name="cargo-adicionar", description="Adiciona um cargo que recebe as candidaturas por DM.")
    @app_commands.describe(formulario_id="ID do formulário", cargo="Cargo que vai receber as candidaturas")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_cargo_adicionar(self, interaction: discord.Interaction, formulario_id: str, cargo: discord.Role):
        ok = await formularios.adicionar_cargo_notificar(interaction.guild.id, formulario_id, cargo.id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ {cargo.mention} agora recebe candidaturas desse formulário.", ephemeral=True)

    @app_commands.command(name="cargo-remover", description="Remove um cargo da lista de notificação de um formulário.")
    @app_commands.describe(formulario_id="ID do formulário", cargo="Cargo a remover")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_cargo_remover(self, interaction: discord.Interaction, formulario_id: str, cargo: discord.Role):
        ok = await formularios.remover_cargo_notificar(interaction.guild.id, formulario_id, cargo.id)
        if not ok:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ {cargo.mention} não recebe mais candidaturas desse formulário.", ephemeral=True)

    @app_commands.command(name="painel", description="Atualiza a central pública com os formulários disponíveis.")
    @app_commands.describe(formulario_id="ID do formulário que deseja disponibilizar")
    @app_commands.checks.has_permissions(administrator=True)
    async def formulario_painel(self, interaction: discord.Interaction, formulario_id: str):
        formulario = await formularios.get_formulario(interaction.guild.id, formulario_id)
        if not formulario:
            await interaction.response.send_message("Não achei nenhum formulário com esse ID.", ephemeral=True)
            return
        if not _perguntas_flat(formulario):
            await interaction.response.send_message(
                "Esse formulário ainda não tem perguntas. Use `/formularios pagina-adicionar` primeiro.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.atualizar_central_inscricoes(interaction.guild)
        except (discord.Forbidden, discord.HTTPException, TypeError):
            logging.exception("Falha ao atualizar central pública pelo comando painel.")
            await interaction.followup.send("Não consegui atualizar a central. Verifique as permissões do bot.", ephemeral=True)
            return
        await interaction.followup.send(
            f"Central atualizada. **{formulario.get('nome')}** aparece no seletor se estiver ativo.",
            ephemeral=True,
        )

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
            _limpar_sessoes_formularios()
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

            formulario_resposta = await formularios.get_formulario(
                guild_encontrada.id,
                resposta.get("formulario_id", ""),
            )
            # Apenas instrutores/aprovadores e administradores podem revisar formulários.
            membro_revisor = guild_encontrada.get_member(interaction.user.id)
            if membro_revisor is None:
                try:
                    membro_revisor = await guild_encontrada.fetch_member(interaction.user.id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    membro_revisor = None

            autorizado = bool(
                membro_revisor
                and (
                    membro_revisor.guild_permissions.administrator
                    or any(cargo.id == CARGO_INSTRUTOR_FORMULARIO_ID for cargo in membro_revisor.roles)
                )
            )
            if not autorizado:
                await interaction.response.send_message(
                    "Você precisa do cargo Instrutor/Aprovador ou da permissão Administrador para revisar formulários.",
                    ephemeral=True,
                )
                return

            if resposta["status"] != "pendente":
                await interaction.response.send_message(f"Essa candidatura já foi **{resposta['status']}**.", ephemeral=True)
                return

            novo_status = "aprovada" if aprovado else "recusada"
            resultado = await formularios.definir_status_resposta(
                guild_encontrada.id,
                resposta_id,
                novo_status,
                interaction.user.id,
            )
            if not resultado:
                await interaction.response.send_message(
                    "Essa candidatura já foi revisada por outra pessoa.",
                    ephemeral=True,
                )
                return

            embed = interaction.message.embeds[0]
            embed.color = 0x57F287 if aprovado else 0xED4245
            embed.add_field(
                name="Decisão",
                value=f"{'✅ Aprovado' if aprovado else '❌ Recusado'} por {interaction.user.mention}",
                inline=False,
            )
            await interaction.response.edit_message(embed=embed, view=None)

            status_texto = "APROVADA" if aprovado else "RECUSADA"
            nome_formulario = (formulario_resposta or {}).get("nome", "Formulário")
            texto_resultado = (
                f"{'🎉' if aprovado else '❌'} Sua candidatura para **{nome_formulario}** foi "
                f"**{status_texto}** por {interaction.user} no servidor **{guild_encontrada.name}**."
            )

            candidato = guild_encontrada.get_member(int(resposta["autor_id"]))
            if candidato is None:
                try:
                    candidato = await guild_encontrada.fetch_member(int(resposta["autor_id"]))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    candidato = None
            if candidato:
                try:
                    await candidato.send(texto_resultado)
                except (discord.Forbidden, discord.HTTPException):
                    logging.info("Não foi possível enviar o resultado da candidatura %s ao candidato %s por DM.", resposta_id, resposta["autor_id"])

            # Informa os instrutores/aprovadores do resultado.
            cargo_instrutor = guild_encontrada.get_role(CARGO_INSTRUTOR_FORMULARIO_ID)
            if cargo_instrutor:
                for instrutor in cargo_instrutor.members:
                    if instrutor.bot:
                        continue
                    try:
                        await instrutor.send(
                            f"Resultado de formulário: {nome_formulario} — candidatura ID {resposta_id} "
                            f"de {resposta['autor_id']} foi {status_texto} por {interaction.user}."
                        )
                    except (discord.Forbidden, discord.HTTPException):
                        logging.info("Não foi possível notificar instrutor %s sobre candidatura %s.", instrutor.id, resposta_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Formularios(bot))