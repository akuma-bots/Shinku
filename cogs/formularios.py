import asyncio
import logging
import time

import discord
from discord.ext import commands

from utils.apresentacao import criar_embed, aplicar_identidade_servidor
from utils.storage import carregar, salvar

from utils import formularios
from utils.guild_config import membro_tem_lideranca

PREFIXO_ABRIR = "formulario:abrir:"
PREFIXO_APROVAR = "formulario:aprovar:"
PREFIXO_RECUSAR = "formulario:recusar:"
PREFIXO_AVALIAR = "formulario:avaliar:"
PREFIXO_HISTORICO = "formulario:historico:"
PREFIXO_CONTINUAR = "formulario:continuar:"
SESSOES_FORMULARIOS = {}
TEMPO_SESSAO_FORMULARIO = 15 * 60
LIMITE_SESSOES_FORMULARIO = 5000
CANAL_PAINEIS_FORMULARIOS = 1545835428530360401
CANAL_RECEBIMENTO_CANDIDATURAS = 1563995882540498996


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
        ], [
            "Como você priorizaria tarefas quando várias demandas chegassem ao mesmo tempo?",
            "O que faria se percebesse que outro membro da equipe está abusando das permissões?",
            "Como manteria a confidencialidade de informações internas e denúncias?",
            "Que iniciativa concreta você proporia para melhorar a experiência dos membros?",
            "Por que a liderança deveria confiar a você responsabilidades dentro da NÊMESIS?"
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
        if resposta is None:
            await interaction.followup.send(
                "Você já possui uma candidatura pendente para este formulário. Aguarde a avaliação da equipe.",
                ephemeral=True,
            )
            return
        cog = interaction.client.get_cog("Formularios")
        canal_recebido = False
        if cog is not None:
            canal_recebido = await cog.notificar_cargos(guild, self.formulario, resposta)
        mensagem_envio = (
            "Sua candidatura foi protocolada e publicada no canal da comissão responsável."
            if canal_recebido else
            "Sua candidatura foi salva, mas a publicação no canal da comissão falhou. A equipe técnica precisa verificar as permissões do bot."
        )
        await interaction.followup.send(
            embed=criar_embed(
                "✦・ INSCRIÇÃO RECEBIDA ・✦",
                (
                    f"{mensagem_envio}\n\n"
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
    titulo = f"DOSSIÊ DE CANDIDATURA  /  {resposta.get('formTitulo') or formulario.get('nome') or 'FORMULÁRIO'}"
    itens_salvos = resposta.get("itens")
    if isinstance(itens_salvos, list) and itens_salvos and all(isinstance(item, dict) for item in itens_salvos):
        # Cada candidatura conserva o enunciado original, mesmo que o formulário seja editado depois.
        pares = [
            (str(item.get("pergunta") or "Questão"), str(item.get("resposta") if item.get("resposta") is not None else "—"))
            for item in itens_salvos
        ]
    else:
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
    view.add_item(discord.ui.Button(
        label="Registrar avaliação",
        style=discord.ButtonStyle.primary,
        emoji="📝",
        custom_id=f"{PREFIXO_AVALIAR}{resposta_id}",
    ))
    view.add_item(discord.ui.Button(
        label="Aprovar",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id=f"{PREFIXO_APROVAR}{resposta_id}",
    ))
    view.add_item(discord.ui.Button(
        label="Recusar",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id=f"{PREFIXO_RECUSAR}{resposta_id}",
    ))
    view.add_item(discord.ui.Button(
        label="Histórico",
        style=discord.ButtonStyle.secondary,
        emoji="📚",
        custom_id=f"{PREFIXO_HISTORICO}{resposta_id}",
    ))
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


class ModalAvaliacaoFormulario(discord.ui.Modal):
    """Avaliação estruturada por modal, sem depender de comandos digitados."""

    def __init__(self, resposta_id: str):
        super().__init__(title=f"Avaliar candidatura · {resposta_id[:12]}")
        self.resposta_id = resposta_id
        self.notas = discord.ui.TextInput(
            label="Notas P/R/D/I/C (1–5)",
            placeholder="Postura, responsabilidade, disponibilidade, imparcialidade, comunicação: 5,4,4,5,5",
            required=True,
            max_length=25,
        )
        self.justificativa = discord.ui.TextInput(
            label="Justificativa técnica",
            placeholder="Registre evidências que sustentam a avaliação.",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        self.add_item(self.notas)
        self.add_item(self.justificativa)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Somente a administração autorizada pode avaliar candidaturas.", ephemeral=True)
            return
        resposta = await formularios.get_resposta(interaction.guild.id, self.resposta_id)
        if not resposta or resposta.get("status") != "pendente":
            await interaction.response.send_message("Esta candidatura não está mais pendente.", ephemeral=True)
            return
        try:
            valores = [int(valor.strip()) for valor in str(self.notas.value).replace(";", ",").split(",")]
        except (TypeError, ValueError):
            valores = []
        if len(valores) != 5 or any(valor < 1 or valor > 5 for valor in valores):
            await interaction.response.send_message(
                "Informe exatamente cinco notas inteiras entre 1 e 5, separadas por vírgulas.",
                ephemeral=True,
            )
            return
        campos = ("postura", "responsabilidade", "disponibilidade", "imparcialidade", "comunicacao")
        criterios = dict(zip(campos, valores))
        await interaction.response.defer(ephemeral=True, thinking=True)
        avaliacao = await formularios.registrar_avaliacao(
            interaction.guild.id,
            self.resposta_id,
            interaction.user.id,
            criterios,
            self.justificativa.value,
        )
        if not avaliacao:
            await interaction.followup.send("A ficha foi encerrada antes de salvar a avaliação. Atualize a fila.", ephemeral=True)
            return
        await interaction.followup.send(
            embed=criar_embed(
                "✦・ AVALIAÇÃO REGISTRADA ・✦",
                f"**PROTOCOLO**　{self.resposta_id}\n"
                f"**AVALIADOR**　{interaction.user.mention}\n"
                f"**MÉDIA**　{avaliacao['media']:.2f}/5\n"
                f"**NOTAS**　{' · '.join(str(valor) for valor in valores)}\n\n"
                f"**JUSTIFICATIVA**\n{self.justificativa.value[:1000]}",
                cor=0x9F1239,
                rodape="NÊMESIS • AVALIAÇÃO ESTRUTURADA",
            ),
            ephemeral=True,
        )


class ModalDecisaoFormulario(discord.ui.Modal):
    """Exige justificativa auditável para aprovar ou recusar uma candidatura."""

    def __init__(self, resposta_id: str, aprovado: bool):
        super().__init__(title=f"{'Aprovar' if aprovado else 'Recusar'} candidatura · {resposta_id[:12]}")
        self.resposta_id = resposta_id
        self.aprovado = aprovado
        self.justificativa = discord.ui.TextInput(
            label="Justificativa da decisão",
            placeholder="Explique objetivamente os fundamentos da decisão.",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        self.add_item(self.justificativa)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Somente a administração autorizada pode decidir candidaturas.", ephemeral=True)
            return
        resposta = await formularios.get_resposta(guild.id, self.resposta_id)
        if not resposta or resposta.get("status") != "pendente":
            await interaction.response.send_message("Esta candidatura já foi encerrada ou não existe.", ephemeral=True)
            return
        if not resposta.get("avaliacoes"):
            await interaction.response.send_message(
                "Registre primeiro a avaliação estruturada desta ficha.",
                ephemeral=True,
            )
            return

        novo_status = "aprovada" if self.aprovado else "recusada"
        await interaction.response.defer(ephemeral=True, thinking=True)
        resultado = await formularios.definir_status_resposta(
            guild.id,
            self.resposta_id,
            novo_status,
            interaction.user.id,
            self.justificativa.value,
        )
        if not resultado:
            await interaction.followup.send("Esta ficha foi decidida por outra pessoa. Atualize a fila.", ephemeral=True)
            return

        formulario = await formularios.get_formulario(guild.id, resposta.get("formulario_id", "")) or {
            "nome": resposta.get("formTitulo", "Formulário")
        }
        from utils.registro_global import registrar
        try:
            await registrar(
                guild,
                "formularios",
                f"Candidatura {novo_status}",
                f"Protocolo: {self.resposta_id}\n"
                f"Formulário: **{formulario.get('nome', 'Formulário')}**\n"
                f"Candidato: <@{resposta.get('autor_id')}> ({resposta.get('autor_id')})\n"
                f"Revisor: {interaction.user.mention} ({interaction.user.id})\n"
                f"Justificativa: {self.justificativa.value[:1000]}",
                cor=0x57F287 if self.aprovado else 0xED4245,
            )
        except Exception:
            logging.exception("Falha ao registrar a decisão da candidatura %s.", self.resposta_id)

        candidato = guild.get_member(int(resposta.get("autor_id", 0) or 0))
        if candidato is None:
            try:
                candidato = await guild.fetch_member(int(resposta.get("autor_id", 0) or 0))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                candidato = None
        status_texto = "APROVADA" if self.aprovado else "RECUSADA"
        if candidato:
            try:
                await candidato.send(
                    f"{'🎉' if self.aprovado else '❌'} Sua candidatura para **{formulario.get('nome', 'Formulário')}** "
                    f"foi **{status_texto}** pela administração da NÊMESIS.\n"
                    f"**Justificativa:** {self.justificativa.value[:1000]}"
                )
            except (discord.Forbidden, discord.HTTPException):
                logging.info("Não foi possível enviar o resultado da candidatura %s por DM.", self.resposta_id)

        await interaction.followup.send(
            f"Decisão registrada: candidatura **{novo_status}**. Protocolo {self.resposta_id} atualizado.",
            ephemeral=True,
        )


class SeletorFilaCandidaturas(discord.ui.Select):
    """Entrada da fila privada de fichas pendentes dentro da gestão do formulário."""

    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Administração · consultar fichas pendentes",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Abrir fila de candidaturas pendentes",
                    value="abrir_pendentes",
                    description="Consultar, avaliar e decidir fichas deste formulário",
                    emoji="🗂️",
                )
            ],
            custom_id="nemesis:formularios:fila_pendentes",
        )

    async def callback(self, interaction: discord.Interaction):
        central = self.central
        if interaction.user.id != central.usuario_id:
            await interaction.response.send_message("Esta central pertence a outra pessoa.", ephemeral=True)
            return
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("A fila de candidaturas é restrita à administração autorizada.", ephemeral=True)
            return

        pendentes = await formularios.listar_respostas(
            interaction.guild.id,
            formulario_id=central.formulario_id,
            status="pendente",
        )
        pendentes.sort(
            key=lambda item: float(item.get("criado_em", item.get("timestamp", 0)) or 0),
            reverse=True,
        )
        if not pendentes:
            await interaction.response.send_message(
                "Não há fichas pendentes para este formulário.",
                ephemeral=True,
            )
            return

        view = FilaCandidaturasView(central, pendentes)
        await interaction.response.send_message(
            embed=view.montar_embed(),
            view=view,
            ephemeral=True,
        )


class FilaCandidaturasView(discord.ui.View):
    """Fila paginada; cada seletor respeita o limite de 25 opções do Discord."""

    def __init__(self, central, pendentes: list[dict]):
        super().__init__(timeout=300)
        self.central = central
        self.pendentes = pendentes
        self.pagina = 0
        self._montar()

    @property
    def total_paginas(self):
        return max(1, (len(self.pendentes) + 24) // 25)

    def montar_embed(self):
        inicio = self.pagina * 25
        return criar_embed(
            "𓂀 FILA RESTRITA · CANDIDATURAS",
            f"**FORMULÁRIO**　{self.central.formulario_id}\n"
            f"**PENDENTES**　{len(self.pendentes)}\n"
            f"**PÁGINA**　{self.pagina + 1}/{self.total_paginas}\n\n"
            "Selecione uma ficha para abrir o dossiê, consultar as respostas e continuar a avaliação.",
            cor=0x9F1239,
            rodape="NÊMESIS • ACESSO ADMINISTRATIVO",
        )

    def _montar(self):
        self.clear_items()
        inicio = self.pagina * 25
        self.add_item(SeletorFichaPendente(self.central, self.pendentes[inicio:inicio + 25]))
        self.anterior.disabled = self.pagina <= 0
        self.proxima.disabled = self.pagina >= self.total_paginas - 1
        self.add_item(self.anterior)
        self.add_item(self.proxima)
        self.add_item(self.atualizar_fila)

    async def _validar_interacao(self, interaction: discord.Interaction):
        if interaction.user.id != self.central.usuario_id:
            await interaction.response.send_message("Esta fila pertence a outra pessoa.", ephemeral=True)
            return False
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("A fila de candidaturas é restrita à administração autorizada.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_interacao(interaction):
            return
        self.pagina = max(0, self.pagina - 1)
        self._montar()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_interacao(interaction):
            return
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._montar()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    @discord.ui.button(label="Atualizar fila", style=discord.ButtonStyle.primary, emoji="🔄")
    async def atualizar_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_interacao(interaction):
            return
        atuais = await formularios.listar_respostas(
            interaction.guild.id,
            formulario_id=self.central.formulario_id,
            status="pendente",
        )
        atuais.sort(key=lambda item: float(item.get("criado_em", item.get("timestamp", 0)) or 0), reverse=True)
        self.pendentes = atuais
        self.pagina = min(self.pagina, self.total_paginas - 1)
        self._montar()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)


class SeletorFichaPendente(discord.ui.Select):
    def __init__(self, central, pendentes: list[dict]):
        self.central = central
        opcoes = []
        for item in pendentes[:25]:
            protocolo = str(item.get("id") or "")
            nome = str(item.get("nome") or f"Membro {item.get('autor_id', 'desconhecido')}")
            criado = int(float(item.get("criado_em", item.get("timestamp", 0)) or 0))
            opcoes.append(discord.SelectOption(
                label=f"{nome[:65]} · {protocolo}"[:100],
                value=protocolo,
                description=f"Recebida <t:{criado}:R> · aguardando análise"[:100],
                emoji="📄",
            ))
        super().__init__(
            placeholder="Selecione a ficha que deseja analisar",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:formularios:ficha_pendente",
        )

    async def callback(self, interaction: discord.Interaction):
        central = self.central
        if interaction.user.id != central.usuario_id:
            await interaction.response.send_message("Esta consulta pertence a outra pessoa.", ephemeral=True)
            return
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("A consulta de fichas é restrita à administração autorizada.", ephemeral=True)
            return

        protocolo = self.values[0]
        resposta = await formularios.get_resposta(interaction.guild.id, protocolo)
        if not resposta or resposta.get("status") != "pendente":
            await interaction.response.send_message(
                "Esta ficha não está mais pendente. Atualize a fila para consultar o estado atual.",
                ephemeral=True,
            )
            return
        formulario = await formularios.get_formulario(
            interaction.guild.id,
            resposta.get("formulario_id", ""),
        ) or {"nome": resposta.get("formTitulo", "Formulário"), "paginas": []}
        criado = int(float(resposta.get("criado_em", resposta.get("timestamp", 0)) or 0))
        avaliacoes = resposta.get("avaliacoes", [])
        resumo = criar_embed(
            f"𓂀 DOSSIÊ · {protocolo}",
            f"**CANDIDATO**　<@{int(resposta.get('autor_id', 0) or 0)}>\n"
            f"**PROCESSO**　{formulario.get('nome', 'Formulário')}\n"
            "**SITUAÇÃO**　🟠 PENDENTE\n"
            f"**RECEBIDA**　<t:{criado}:F>\n"
            f"**AVALIAÇÕES**　{len(avaliacoes) if isinstance(avaliacoes, list) else 0}",
            cor=0x9F1239,
            rodape="NÊMESIS • DOSSIÊ RESTRITO • ADMINISTRAÇÃO",
        )
        anexos = [resumo] + _embeds_resposta(formulario, resposta, interaction.guild, central.cog.bot)
        await interaction.response.send_message(
            embeds=anexos[:10],
            view=_view_resposta(protocolo),
            ephemeral=True,
        )
        for inicio in range(10, len(anexos), 10):
            await interaction.followup.send(embeds=anexos[inicio:inicio + 10], ephemeral=True)


def _administrador_formularios(interaction: discord.Interaction, usuario_id: int) -> bool:
    return bool(
        interaction.guild is not None
        and interaction.user.id == usuario_id
        and membro_tem_lideranca(interaction.user)
    )


class ModalCriarFormulario(discord.ui.Modal):
    def __init__(self, cog, guild_id: int, usuario_id: int):
        super().__init__(title="Novo formulário · NÊMESIS")
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.nome = discord.ui.TextInput(label="Nome interno", placeholder="Ex.: Recrutamento Staff", max_length=100)
        self.titulo = discord.ui.TextInput(label="Título do painel", placeholder="Título exibido aos membros", max_length=200)
        self.descricao = discord.ui.TextInput(label="Descrição do painel", style=discord.TextStyle.paragraph, max_length=4000)
        self.banner = discord.ui.TextInput(label="URL do banner (opcional)", required=False, placeholder="https://...", max_length=500)
        for campo in (self.nome, self.titulo, self.descricao, self.banner):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A criação de formulários é restrita à administração que abriu a central.", ephemeral=True)
            return
        nome = str(self.nome.value or "").strip()
        titulo = str(self.titulo.value or "").strip()
        descricao = str(self.descricao.value or "").strip()
        if not nome or not titulo or not descricao:
            await interaction.response.send_message("Nome, título e descrição são obrigatórios.", ephemeral=True)
            return
        banner = str(self.banner.value or "").strip()
        if banner and not banner.startswith("https://"):
            await interaction.response.send_message("O banner precisa ser uma URL HTTPS válida.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        formulario = await formularios.criar_formulario(
            self.guild_id, nome, titulo, descricao, banner or None, interaction.user.id,
        )
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(
            interaction, self.guild_id, self.usuario_id, formulario["id"],
            f"Formulário **{formulario['nome']}** criado. Configure as perguntas e a comissão antes de publicar.",
        )


class ModalEditarFormulario(discord.ui.Modal):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario: dict):
        super().__init__(title=f"Editar · {str(formulario.get('nome') or 'Formulário')[:30]}")
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id = str(formulario["id"])
        self.nome = discord.ui.TextInput(label="Nome interno", default=str(formulario.get("nome") or "")[:100], max_length=100)
        self.titulo = discord.ui.TextInput(label="Título do painel", default=str(formulario.get("titulo_painel") or formulario.get("nome") or "")[:200], max_length=200)
        self.descricao = discord.ui.TextInput(label="Descrição do painel", style=discord.TextStyle.paragraph, default=str(formulario.get("descricao_painel") or "")[:4000], max_length=4000)
        self.banner = discord.ui.TextInput(label="Banner: URL, REMOVER ou vazio", required=False, default=str(formulario.get("banner_url") or "")[:500], placeholder="URL HTTPS; REMOVER apaga; vazio mantém", max_length=500)
        for campo in (self.nome, self.titulo, self.descricao, self.banner):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A edição é restrita à administração que abriu a central.", ephemeral=True)
            return
        nome = str(self.nome.value or "").strip()
        titulo = str(self.titulo.value or "").strip()
        descricao = str(self.descricao.value or "").strip()
        if not nome or not titulo or not descricao:
            await interaction.response.send_message("Nome, título e descrição são obrigatórios.", ephemeral=True)
            return
        banner = str(self.banner.value or "").strip()
        if banner and banner.upper() != "REMOVER" and not banner.startswith("https://"):
            await interaction.response.send_message("O banner precisa ser uma URL HTTPS válida ou o texto REMOVER.", ephemeral=True)
            return
        alteracoes = {"nome": nome, "titulo_painel": titulo, "descricao_painel": descricao}
        if banner.upper() == "REMOVER":
            alteracoes["banner_url"] = ""
        elif banner:
            alteracoes["banner_url"] = banner
        await interaction.response.defer(ephemeral=True, thinking=True)
        atualizado = await formularios.atualizar_formulario(self.guild_id, self.formulario_id, **alteracoes)
        if not atualizado:
            await interaction.followup.send("O formulário não existe mais. Atualize a central.", ephemeral=True)
            return
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(interaction, self.guild_id, self.usuario_id, self.formulario_id, "Dados do formulário atualizados.")


class ModalAdicionarPerguntas(discord.ui.Modal):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario_id: str):
        super().__init__(title="Adicionar etapa · até 5 perguntas")
        self.cog, self.guild_id, self.usuario_id, self.formulario_id = cog, guild_id, usuario_id, formulario_id
        self.perguntas = []
        for indice in range(5):
            campo = discord.ui.TextInput(
                label=f"Pergunta {indice + 1}",
                placeholder="Enunciado da pergunta" if indice == 0 else "Opcional",
                required=(indice == 0),
                style=discord.TextStyle.paragraph,
                max_length=256,
            )
            self.perguntas.append(campo)
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A edição de perguntas é restrita à administração que abriu a central.", ephemeral=True)
            return
        perguntas = [str(campo.value).strip() for campo in self.perguntas if str(campo.value).strip()]
        await interaction.response.defer(ephemeral=True, thinking=True)
        formulario = await formularios.adicionar_pagina(self.guild_id, self.formulario_id, perguntas)
        if not formulario:
            await interaction.followup.send("Não foi possível adicionar a etapa. Confira se o formulário ainda existe.", ephemeral=True)
            return
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(interaction, self.guild_id, self.usuario_id, self.formulario_id, f"Etapa {len(formulario.get('paginas', []))} adicionada com {len(perguntas)} pergunta(s).")


class ConfirmarRemocaoPaginaView(discord.ui.View):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario_id: str, indice: int):
        super().__init__(timeout=120)
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id, self.indice = formulario_id, indice

    @discord.ui.button(label="Confirmar remoção da etapa", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A remoção é restrita à administração que abriu a central.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok = await formularios.remover_pagina(self.guild_id, self.formulario_id, self.indice)
        if not ok:
            await interaction.followup.send("A etapa não existe mais. Atualize a central.", ephemeral=True)
            return
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(interaction, self.guild_id, self.usuario_id, self.formulario_id, "Etapa removida. As candidaturas já recebidas foram preservadas.")


class SeletorPaginaRemover(discord.ui.Select):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario: dict):
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id = str(formulario["id"])
        opcoes = []
        for indice, pagina in enumerate(formulario.get("paginas", [])):
            perguntas = pagina.get("perguntas", []) if isinstance(pagina, dict) else pagina
            titulo = pagina.get("titulo") if isinstance(pagina, dict) else f"Etapa {indice + 1}"
            opcoes.append(discord.SelectOption(label=f"Etapa {indice + 1} · {str(titulo or '')[:65]}", value=str(indice), description=f"{len(perguntas)} pergunta(s)"))
        super().__init__(placeholder="Selecione a etapa que deseja remover", min_values=1, max_values=1, options=opcoes[:25])

    async def callback(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A remoção é restrita à administração que abriu a central.", ephemeral=True)
            return
        indice = int(self.values[0])
        await interaction.response.send_message(
            f"Confirme a remoção da etapa **{indice + 1}**. As candidaturas existentes não serão apagadas.",
            view=ConfirmarRemocaoPaginaView(self.cog, self.guild_id, self.usuario_id, self.formulario_id, indice),
            ephemeral=True,
        )


class GerenciarCargosView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, usuario_id: int, formulario: dict):
        super().__init__(timeout=180)
        self.cog, self.guild_id, self.usuario_id = cog, guild.id, usuario_id
        self.formulario_id = str(formulario["id"])
        ids_atuais = {int(item) for item in formulario.get("cargos_notificar", []) if str(item).isdigit()}
        padroes = [cargo for cargo in guild.roles if cargo.id in ids_atuais and not cargo.is_default() and not cargo.managed]
        self.selected_role_ids = {cargo.id for cargo in padroes}
        self.seletor = discord.ui.RoleSelect(
            placeholder="Escolha os cargos que receberão as fichas",
            min_values=0, max_values=25, default_values=padroes,
            custom_id="nemesis:formularios:cargos_notificar",
        )
        self.seletor.callback = self.atualizar_selecao
        self.add_item(self.seletor)

    async def atualizar_selecao(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("Configuração restrita à administração.", ephemeral=True)
            return
        self.selected_role_ids = {role.id for role in self.seletor.values if not role.is_default() and not role.managed}
        await interaction.response.edit_message(content=f"Cargos selecionados: **{len(self.selected_role_ids)}**. Salve para aplicar.", view=self)

    @discord.ui.button(label="Salvar cargos", style=discord.ButtonStyle.success, emoji="💾")
    async def salvar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("Configuração restrita à administração.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        cargos = sorted(self.selected_role_ids)
        formulario = await formularios.definir_cargos_notificar(self.guild_id, self.formulario_id, cargos)
        if not formulario:
            await interaction.followup.send("O formulário não existe mais.", ephemeral=True)
            return
        await self.cog.enviar_central_formularios(interaction, self.guild_id, self.usuario_id, self.formulario_id, f"Lista de cargos atualizada: **{len(cargos)}** cargo(s).")


class ModalEditarPergunta(discord.ui.Modal):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario_id: str, indice_global: int, texto_atual: str):
        super().__init__(title=f"Editar pergunta {indice_global + 1}")
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id, self.indice_global = formulario_id, indice_global
        self.texto = discord.ui.TextInput(label="Enunciado da pergunta", style=discord.TextStyle.paragraph, default=texto_atual[:256], max_length=256)
        self.add_item(self.texto)

    async def on_submit(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A edição de perguntas é restrita à administração que abriu a central.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok = await formularios.atualizar_pergunta(self.guild_id, self.formulario_id, self.indice_global, self.texto.value)
        if not ok:
            await interaction.followup.send("Não foi possível localizar essa pergunta. Atualize a central.", ephemeral=True)
            return
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(interaction, self.guild_id, self.usuario_id, self.formulario_id, "Pergunta atualizada. Os dossiês existentes continuam exibindo os enunciados originais.")


class EditarPerguntasView(discord.ui.View):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario: dict):
        super().__init__(timeout=180)
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario = formulario
        self.pagina = 0
        self._montar()

    @property
    def total_paginas(self):
        return max(1, (len(_perguntas_flat(self.formulario)) + 24) // 25)

    def _montar(self):
        self.clear_items()
        self.add_item(SeletorPerguntaEditar(self.cog, self.guild_id, self.usuario_id, self.formulario, self.pagina))
        self.anterior.disabled = self.pagina <= 0
        self.proxima.disabled = self.pagina >= self.total_paginas - 1
        self.add_item(self.anterior)
        self.add_item(self.proxima)

    async def _validar(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A edição é restrita à administração que abriu a central.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = max(0, self.pagina - 1)
        self._montar()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._montar()
        await interaction.response.edit_message(view=self)


class SeletorPerguntaEditar(discord.ui.Select):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario: dict, pagina: int = 0):
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id = str(formulario["id"])
        self.perguntas = [_texto_pergunta(pergunta) for pergunta in _perguntas_flat(formulario)]
        inicio = pagina * 25
        opcoes = [
            discord.SelectOption(label=f"Questão {indice + 1:02d}", value=str(indice), description=texto[:100])
            for indice, texto in enumerate(self.perguntas[inicio:inicio + 25], start=inicio)
        ]
        super().__init__(placeholder=f"Selecione uma pergunta · página {pagina + 1}", min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A edição é restrita à administração que abriu a central.", ephemeral=True)
            return
        indice = int(self.values[0])
        await interaction.response.send_modal(ModalEditarPergunta(
            self.cog, self.guild_id, self.usuario_id, self.formulario_id, indice, self.perguntas[indice]
        ))


class SeletorAcaoFormulario(discord.ui.Select):
    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Escolha uma ação para o formulário",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Editar dados do formulário", value="editar"),
                discord.SelectOption(label="Adicionar etapa de perguntas", value="adicionar_etapa"),
                discord.SelectOption(label="Editar pergunta", value="editar_pergunta"),
                discord.SelectOption(label="Remover etapa de perguntas", value="remover_etapa"),
                discord.SelectOption(label="Configurar cargos notificados", value="cargos"),
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
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Você precisa de permissão de Administrador.", ephemeral=True)
            return
        formulario = await formularios.get_formulario(interaction.guild.id, central.formulario_id)
        if not formulario:
            await interaction.response.send_message("O formulário selecionado não existe mais.", ephemeral=True)
            return
        acao = self.values[0]
        if acao == "editar":
            await interaction.response.send_modal(ModalEditarFormulario(central.cog, interaction.guild.id, interaction.user.id, formulario))
            return
        if acao == "adicionar_etapa":
            await interaction.response.send_modal(ModalAdicionarPerguntas(central.cog, interaction.guild.id, interaction.user.id, central.formulario_id))
            return
        if acao == "editar_pergunta":
            perguntas = _perguntas_flat(formulario)
            if not perguntas:
                await interaction.response.send_message("Este formulário ainda não possui perguntas.", ephemeral=True)
                return
            view = EditarPerguntasView(central.cog, interaction.guild.id, interaction.user.id, formulario)
            await interaction.response.send_message(
                f"Selecione a pergunta que deseja editar. Total: **{len(perguntas)}** · página **1/{view.total_paginas}**.",
                view=view, ephemeral=True,
            )
            return
        if acao == "remover_etapa":
            paginas = formulario.get("paginas", [])
            if not paginas:
                await interaction.response.send_message("Este formulário ainda não possui etapas.", ephemeral=True)
                return
            view = discord.ui.View(timeout=120)
            view.add_item(SeletorPaginaRemover(central.cog, interaction.guild.id, interaction.user.id, formulario))
            await interaction.response.send_message("Escolha a etapa que deseja remover. A remoção exige confirmação.", view=view, ephemeral=True)
            return
        if acao == "cargos":
            view = GerenciarCargosView(central.cog, interaction.guild, interaction.user.id, formulario)
            await interaction.response.send_message(
                f"**Comissão de análise · {formulario.get('nome', 'Formulário')}**\nSelecione a lista completa de cargos que deve receber as fichas. O cargo de instrutor padrão continua sendo notificado automaticamente.",
                view=view, ephemeral=True,
            )
            return
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


class SeletorHistoricoCandidaturas(discord.ui.Select):
    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Consultar candidaturas encerradas",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(
                label="Abrir histórico de candidaturas",
                value="encerradas",
                description="Consultar fichas aprovadas e recusadas deste formulário",
                emoji="📚",
            )],
            custom_id="nemesis:formularios:historico_fichas",
        )

    async def callback(self, interaction: discord.Interaction):
        central = self.central
        if interaction.user.id != central.usuario_id or interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("O histórico é restrito à administração que abriu a central.", ephemeral=True)
            return
        respostas = await formularios.listar_respostas(interaction.guild.id, formulario_id=central.formulario_id)
        encerradas = [item for item in respostas if item.get("status") in {"aprovada", "recusada"}]
        encerradas.sort(key=lambda item: float(item.get("atualizado_em", item.get("criado_em", 0)) or 0), reverse=True)
        if not encerradas:
            await interaction.response.send_message("Ainda não existem candidaturas encerradas para este formulário.", ephemeral=True)
            return
        view = FilaHistoricoView(central, encerradas)
        await interaction.response.send_message(embed=view.montar_embed(), view=view, ephemeral=True)


class FilaHistoricoView(discord.ui.View):
    def __init__(self, central, respostas: list[dict]):
        super().__init__(timeout=300)
        self.central, self.respostas, self.pagina = central, respostas, 0
        self._montar()

    @property
    def total_paginas(self):
        return max(1, (len(self.respostas) + 24) // 25)

    def montar_embed(self):
        aprovadas = sum(item.get("status") == "aprovada" for item in self.respostas)
        recusadas = sum(item.get("status") == "recusada" for item in self.respostas)
        return criar_embed(
            "𓂀 HISTÓRICO · CANDIDATURAS ENCERRADAS",
            f"**FORMULÁRIO**　{self.central.formulario_id}\n"
            f"**TOTAL**　{len(self.respostas)}\n"
            f"**APROVADAS**　{aprovadas}　 **RECUSADAS**　{recusadas}\n"
            f"**PÁGINA**　{self.pagina + 1}/{self.total_paginas}\n\n"
            "Selecione uma ficha para consultar o dossiê e a trilha de auditoria.",
            cor=0x9F1239,
            rodape="NÊMESIS • HISTÓRICO RESTRITO",
        )

    def _montar(self):
        self.clear_items()
        inicio = self.pagina * 25
        self.add_item(SeletorFichaHistorica(self.central, self.respostas[inicio:inicio + 25]))
        self.anterior.disabled = self.pagina <= 0
        self.proxima.disabled = self.pagina >= self.total_paginas - 1
        self.add_item(self.anterior)
        self.add_item(self.proxima)

    async def _validar(self, interaction: discord.Interaction):
        if interaction.user.id != self.central.usuario_id or interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("O histórico é restrito à administração que abriu a central.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = max(0, self.pagina - 1)
        self._montar()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._montar()
        await interaction.response.edit_message(embed=self.montar_embed(), view=self)


class SeletorFichaHistorica(discord.ui.Select):
    def __init__(self, central, respostas: list[dict]):
        self.central = central
        opcoes = []
        for item in respostas[:25]:
            protocolo = str(item.get("id") or "")
            nome = str(item.get("nome") or f"Membro {item.get('autor_id', 'desconhecido')}")
            status = str(item.get("status") or "encerrada").upper()
            opcoes.append(discord.SelectOption(
                label=f"{nome[:58]} · {protocolo}"[:100],
                value=protocolo,
                description=f"{status} · protocolo {protocolo}"[:100],
                emoji="✅" if status == "APROVADA" else "❌",
            ))
        super().__init__(placeholder="Selecione uma candidatura encerrada", min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        central = self.central
        if interaction.user.id != central.usuario_id or interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("A consulta é restrita à administração que abriu a central.", ephemeral=True)
            return
        protocolo = self.values[0]
        resposta = await formularios.get_resposta(interaction.guild.id, protocolo)
        if not resposta or resposta.get("status") not in {"aprovada", "recusada"}:
            await interaction.response.send_message("Esta candidatura não está mais encerrada ou não existe.", ephemeral=True)
            return
        formulario = await formularios.get_formulario(interaction.guild.id, resposta.get("formulario_id", "")) or {"nome": resposta.get("formTitulo", "Formulário"), "paginas": []}
        criado = int(float(resposta.get("criado_em", resposta.get("timestamp", 0)) or 0))
        resumo = criar_embed(
            f"𓂀 DOSSIÊ · {protocolo}",
            f"**CANDIDATO**　<@{int(resposta.get('autor_id', 0) or 0)}>\n"
            f"**PROCESSO**　{formulario.get('nome', 'Formulário')}\n"
            f"**SITUAÇÃO**　{str(resposta.get('status')).upper()}\n"
            f"**RECEBIDA**　<t:{criado}:F>",
            cor=0x9F1239,
            rodape="NÊMESIS • DOSSIÊ HISTÓRICO • ADMINISTRAÇÃO",
        )
        anexos = [resumo] + _embeds_resposta(formulario, resposta, interaction.guild, central.cog.bot)
        view = discord.ui.View(timeout=120)
        view.add_item(discord.ui.Button(label="Consultar histórico", style=discord.ButtonStyle.secondary, emoji="📚", custom_id=f"{PREFIXO_HISTORICO}{protocolo}"))
        await interaction.response.send_message(embeds=anexos[:10], view=view, ephemeral=True)
        for inicio in range(10, len(anexos), 10):
            await interaction.followup.send(embeds=anexos[inicio:inicio + 10], ephemeral=True)


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
        criar = discord.ui.Button(label="Novo formulário", style=discord.ButtonStyle.success, emoji="➕")
        async def abrir_criacao(interaction: discord.Interaction):
            if interaction.user.id != self.usuario_id or interaction.guild is None or not membro_tem_lideranca(interaction.user):
                await interaction.response.send_message("A criação é restrita à administração que abriu a central.", ephemeral=True)
                return
            await interaction.response.send_modal(ModalCriarFormulario(self.cog, self.guild_id, self.usuario_id))
        criar.callback = abrir_criacao
        self.add_item(criar)
        if self.lista:
            self.add_item(SeletorFormularioCentral(self))
            self.add_item(SeletorAcaoFormulario(self))
            self.add_item(SeletorFilaCandidaturas(self))
            self.add_item(SeletorHistoricoCandidaturas(self))

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


class Formularios(commands.Cog):
    """Sistema de formulários/candidaturas por páginas: cada formulário tem
    seu painel customizável (título, descrição, banner) e é dividido em
    páginas de até 5 perguntas — o bot encadeia os modais automaticamente
    até completar todas. As respostas vão por DM pros cargos configurados,
    com análise e decisão pela fila administrativa privada; o candidato é avisado do resultado."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._view_inscricoes_registrada = False

    async def enviar_central_formularios(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        usuario_id: int,
        formulario_id: str | None = None,
        mensagem: str | None = None,
    ):
        lista = await formularios.listar_formularios(guild_id)
        lista.sort(key=lambda item: (bool(item.get("arquivado")), str(item.get("nome", "")).casefold()))
        view = CentralFormulariosView(self, guild_id, usuario_id, lista, formulario_id=formulario_id)
        await interaction.followup.send(embed=view.montar_embed(mensagem), view=view, ephemeral=True)

    async def formulario_central(self, interaction: discord.Interaction):
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada da NÊMESIS.", ephemeral=True)
            return
        lista = await formularios.listar_formularios(interaction.guild.id)
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
                    # A definição padrão é aplicada uma única vez. Depois disso, edições
                    # administrativas de perguntas não são desfeitas no próximo on_ready.
                    if int(formulario.get("versao_automatico", 0) or 0) < 1:
                        existentes = set(formularios.perguntas_flat(formulario))
                        faltantes = []
                        for pagina_definida in definicao["paginas"]:
                            for pergunta in pagina_definida:
                                if pergunta not in existentes:
                                    faltantes.append(pergunta)
                                    existentes.add(pergunta)
                        for inicio in range(0, len(faltantes), 5):
                            formulario = await formularios.adicionar_pagina(
                                guild.id, formulario["id"], faltantes[inicio:inicio + 5]
                            )
                            if formulario is None:
                                raise RuntimeError(f"Não foi possível atualizar as perguntas de {definicao['nome']}.")
                        formulario = await formularios.atualizar_formulario(
                            guild.id, formulario["id"], versao_automatico=1
                        )
                        if formulario is None:
                            raise RuntimeError(f"Não foi possível registrar a versão automática de {definicao['nome']}.")
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

    async def notificar_cargos(self, guild: discord.Guild, formulario: dict, resposta: dict) -> bool:
        """Abre um tópico individual por candidatura, evitando inundar o canal da comissão."""
        embeds = _embeds_resposta(formulario, resposta, guild, self.bot)
        canal = guild.get_channel(CANAL_RECEBIMENTO_CANDIDATURAS)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_RECEBIMENTO_CANDIDATURAS)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logging.exception("Canal de candidaturas inacessível: %s", CANAL_RECEBIMENTO_CANDIDATURAS)
                return False
        if not callable(getattr(canal, "create_thread", None)):
            logging.error("O canal de candidaturas precisa permitir a criação de tópicos.")
            return False

        cargos = list(formulario.get("cargos_notificar", []))
        if CARGO_INSTRUTOR_FORMULARIO_ID not in cargos:
            cargos.append(CARGO_INSTRUTOR_FORMULARIO_ID)
        mencoes = []
        for cargo_id in cargos:
            try:
                cargo = guild.get_role(int(cargo_id))
            except (TypeError, ValueError):
                cargo = None
            if cargo and cargo.mention not in mencoes:
                mencoes.append(cargo.mention)

        nome_candidato = str(resposta.get("nome") or f"Membro {resposta.get('autor_id')}").strip()
        nome_thread = f"{formulario.get('nome', 'Candidatura')} • {nome_candidato} • {resposta['id']}"[:100]
        try:
            thread = await canal.create_thread(
                name=nome_thread,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=10080,
                reason=f"Organizar candidatura {resposta['id']} em tópico individual",
            )
            await thread.send(
                content=" ".join(mencoes) if mencoes else None,
                embed=embeds[0],
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
            )
            for embed in embeds[1:]:
                await thread.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            await formularios.atualizar_metadados_resposta(
                guild.id,
                resposta["id"],
                thread_id=thread.id,
                canal_id=canal.id,
                notificacao_em=time.time(),
            )
        except (discord.Forbidden, discord.HTTPException, TypeError):
            logging.exception("Falha ao criar tópico individual para candidatura %s.", resposta.get("id"))
            return False

        # O Registro Global recebe somente um índice sem as respostas pessoais.
        try:
            from utils.registro_global import registrar
            await registrar(
                guild,
                "formularios",
                "Nova candidatura recebida",
                f"Protocolo: `{resposta['id']}`\n"
                f"Formulário: **{formulario.get('nome', 'Formulário')}**\n"
                f"Candidato: <@{resposta.get('autor_id')}>\n"
                f"Análise: [Abrir dossiê individual](https://discord.com/channels/{guild.id}/{thread.id})",
                cor=0x9F1239,
            )
        except Exception:
            logging.exception("Falha ao registrar índice da candidatura %s.", resposta.get("id"))
        return True

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

        if custom_id.startswith(PREFIXO_HISTORICO):
            if interaction.guild is None or not membro_tem_lideranca(interaction.user):
                await interaction.response.send_message("O histórico é restrito à administração autorizada.", ephemeral=True)
                return
            protocolo = custom_id[len(PREFIXO_HISTORICO):]
            resposta = await formularios.get_resposta(interaction.guild.id, protocolo)
            if not resposta:
                await interaction.response.send_message("Não encontrei esta candidatura.", ephemeral=True)
                return
            avaliacoes = resposta.get("avaliacoes", [])
            decisoes = resposta.get("historico_decisoes", [])
            embed = criar_embed(
                f"𓂀 HISTÓRICO · {protocolo}",
                f"**SITUAÇÃO**　{str(resposta.get('status', 'pendente')).upper()}\n"
                f"**AVALIAÇÕES**　{len(avaliacoes) if isinstance(avaliacoes, list) else 0}\n"
                f"**DECISÕES**　{len(decisoes) if isinstance(decisoes, list) else 0}",
                cor=0x9F1239,
                rodape="NÊMESIS • AUDITORIA DO PROCESSO SELETIVO",
            )
            nomes = {"postura": "Postura", "responsabilidade": "Responsabilidade", "disponibilidade": "Disponibilidade", "imparcialidade": "Imparcialidade", "comunicacao": "Comunicação"}
            for indice, item in enumerate(avaliacoes[-8:] if isinstance(avaliacoes, list) else [], 1):
                criterios = item.get("criterios", {})
                notas = " · ".join(f"{nomes.get(chave, chave)} {valor}/5" for chave, valor in criterios.items())
                criado = int(float(item.get("criado_em", 0) or 0))
                embed.add_field(name=f"Avaliação {indice} · <@{int(item.get('revisor_id', 0) or 0)}> · média {float(item.get('media', 0) or 0):.2f}/5", value=f"{notas}\n<t:{criado}:F>\n**Justificativa:** {str(item.get('justificativa') or 'Não informada')[:700]}", inline=False)
            for item in (decisoes[-5:] if isinstance(decisoes, list) else []):
                criado = int(float(item.get("criado_em", 0) or 0))
                embed.add_field(name=f"Decisão · {str(item.get('status', 'indefinida')).upper()}", value=f"**Responsável:** <@{int(item.get('revisor_id', 0) or 0)}>\n**Data:** <t:{criado}:F>\n**Motivo:** {str(item.get('motivo') or 'Não informado')[:700]}", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if custom_id.startswith(PREFIXO_AVALIAR):
            if interaction.guild is None or not membro_tem_lideranca(interaction.user):
                await interaction.response.send_message("Somente a administração autorizada pode avaliar candidaturas.", ephemeral=True)
                return
            resposta_id = custom_id[len(PREFIXO_AVALIAR):]
            resposta = await formularios.get_resposta(interaction.guild.id, resposta_id)
            if not resposta or resposta.get("status") != "pendente":
                await interaction.response.send_message("Esta candidatura não está mais pendente.", ephemeral=True)
                return
            await interaction.response.send_modal(ModalAvaliacaoFormulario(resposta_id))
            return

        if custom_id.startswith(PREFIXO_APROVAR) or custom_id.startswith(PREFIXO_RECUSAR):
            if interaction.guild is None or not membro_tem_lideranca(interaction.user):
                await interaction.response.send_message("Somente a administração autorizada pode decidir candidaturas.", ephemeral=True)
                return
            aprovado = custom_id.startswith(PREFIXO_APROVAR)
            resposta_id = custom_id.split(":")[-1]
            resposta = await formularios.get_resposta(interaction.guild.id, resposta_id)
            if not resposta or resposta.get("status") != "pendente":
                await interaction.response.send_message("Esta candidatura já foi encerrada ou não existe.", ephemeral=True)
                return
            if not resposta.get("avaliacoes"):
                await interaction.response.send_message("Registre primeiro a avaliação estruturada desta ficha.", ephemeral=True)
                return
            await interaction.response.send_modal(ModalDecisaoFormulario(resposta_id, aprovado))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Formularios(bot))