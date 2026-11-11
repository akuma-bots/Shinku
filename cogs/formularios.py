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
    {
        "chave": "ingresso_nemesis",
        "nome": "Inscrição para NÊMESIS",
        "titulo": "NÊMESIS — PROCESSO DE INGRESSO",
        "descricao": (
            "CENTRAL DE RECRUTAMENTO • 𓂀 NÊMESIS - ORG\n\n"
            "Este é o processo oficial para quem deseja ingressar na NÊMESIS. "
            "Responda às 15 perguntas com sinceridade e atenção. "
            "A candidatura será analisada pela administração; o envio não garante aprovação.\n\n"
            "REQUISITOS\n"
            "— Respeitar as regras, a hierarquia e os integrantes.\n"
            "— Manter postura responsável e colaboração com a organização.\n"
            "— Ter disponibilidade para participar das atividades.\n"
            "— Informar corretamente seus dados e experiências.\n\n"
            "Após o envio, sua candidatura receberá um protocolo e ficará em análise. "
            "A decisão será comunicada por mensagem privada."
        ),
        "canal_id": 1563995880623841338,
        "paginas": [
            {
                "titulo": "Identificação e disponibilidade",
                "perguntas": [
                    {"texto": "Como gostaria de ser chamado dentro da NÊMESIS?", "tipo": "texto"},
                    {"texto": "Qual é seu usuário Roblox e o link do seu perfil?", "tipo": "texto"},
                    {"texto": "Há quanto tempo participa de grupos ou organizações no Roblox? Conte brevemente.", "tipo": "paragrafo"},
                    {"texto": "Qual é sua disponibilidade semanal e em quais horários costuma estar ativo?", "tipo": "paragrafo"},
                    {"texto": "Por que deseja ingressar na NÊMESIS?", "tipo": "paragrafo"}
                ]
            },
            {
                "titulo": "Perfil e atuação",
                "perguntas": [
                    {
                        "texto": "Qual divisão mais desperta seu interesse?",
                        "tipo": "escolha",
                        "opcoes": ["N1 Alpha", "N2 Vanguard", "N3 Elite", "N4 Recon", "N5 Assault", "N6 Guard", "Ainda não sei"]
                    },
                    {
                        "texto": "Em qual tipo de atividade você acredita que se destaca?",
                        "tipo": "escolha",
                        "opcoes": ["Combate", "Reconhecimento", "Defesa", "Suporte e organização", "Treinamento", "Ainda estou descobrindo"]
                    },
                    {"texto": "Quais experiências você possui em jogos, combate ou trabalho em equipe?", "tipo": "paragrafo"},
                    {"texto": "O que você entende sobre o propósito e o funcionamento de uma organização como a NÊMESIS?", "tipo": "paragrafo"},
                    {"texto": "Quais habilidades ou qualidades você pode oferecer à organização?", "tipo": "paragrafo"}
                ]
            },
            {
                "titulo": "Conduta e compromisso",
                "perguntas": [
                    {"texto": "Como você lida com ordens, regras e a hierarquia de uma organização?", "tipo": "paragrafo"},
                    {"texto": "Como agiria ao presenciar um conflito entre integrantes da NÊMESIS?", "tipo": "paragrafo"},
                    {"texto": "Se discordasse de uma decisão de um superior, como apresentaria sua posição?", "tipo": "paragrafo"},
                    {"texto": "Como pretende conciliar seus compromissos pessoais com as atividades da NÊMESIS?", "tipo": "paragrafo"},
                    {"texto": "Existe algo mais que gostaria que a comissão soubesse sobre você ou sua candidatura?", "tipo": "paragrafo"}
                ]
            }
        ]
    }
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


def _tipo_pergunta(pergunta) -> str:
    tipo = str(pergunta.get("tipo") or "paragrafo").lower() if isinstance(pergunta, dict) else "paragrafo"
    return tipo if tipo in {"texto", "paragrafo", "escolha"} else "paragrafo"


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


def _texto_embed_inscricoes(embed: discord.Embed) -> str:
    partes = []
    if embed.author and embed.author.name:
        partes.append(f"-# {embed.author.name}")
    if embed.title:
        partes.append(f"## {embed.title}")
    if embed.description:
        partes.append(embed.description)
    for campo in embed.fields:
        partes.append(f"### {campo.name}\n{campo.value}")
    if embed.footer and embed.footer.text:
        partes.append(f"-# {embed.footer.text}")
    return "\n\n".join(partes)


def _dividir_texto_componentes(texto: str, limite: int = 3900) -> list[str]:
    """Divide conteúdo sem exceder o limite do TextDisplay nem descartar caracteres."""
    texto = str(texto or "")
    if not texto:
        return ["—"]
    if limite < 1 or limite > 4000:
        raise ValueError("O limite de TextDisplay deve ficar entre 1 e 4000 caracteres.")

    partes = []
    restante = texto
    while len(restante) > limite:
        corte = restante.rfind("\n", 0, limite + 1)
        if corte >= limite // 2:
            corte += 1
        else:
            corte = restante.rfind(" ", 0, limite + 1)
            if corte >= limite // 2:
                corte += 1
            else:
                corte = limite
        partes.append(restante[:corte])
        restante = restante[corte:]
    if restante:
        partes.append(restante)
    return partes


def _url_media_embed_inscricoes(embed: discord.Embed, atributo: str) -> str | None:
    media = getattr(embed, atributo, None)
    url = str(getattr(media, "url", "") or "").strip()
    if url.startswith(("https://", "http://")):
        return url
    return None


def _componentes_embed_inscricoes(embeds: list[discord.Embed]) -> list:
    """Converte embeds para componentes V2 preservando texto, thumbnails e imagens."""
    componentes = []
    validos = [item for item in embeds if isinstance(item, discord.Embed)]
    for indice, embed in enumerate(validos):
        blocos = _dividir_texto_componentes(_texto_embed_inscricoes(embed))
        thumbnail = _url_media_embed_inscricoes(embed, "thumbnail")
        if thumbnail:
            primeiros = blocos[:3]
            componentes.append(discord.ui.Section(
                *(discord.ui.TextDisplay(bloco) for bloco in primeiros),
                accessory=discord.ui.Thumbnail(
                    thumbnail,
                    description=f"Imagem de identificação: {embed.title or 'formulário'}"[:256],
                ),
            ))
            blocos = blocos[3:]
        componentes.extend(discord.ui.TextDisplay(bloco) for bloco in blocos)

        imagem = _url_media_embed_inscricoes(embed, "image")
        if imagem:
            componentes.append(discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    imagem,
                    description=f"Imagem do documento: {embed.title or 'formulário'}"[:256],
                )
            ))
        if indice < len(validos) - 1:
            componentes.append(discord.ui.Separator(
                visible=True, spacing=discord.SeparatorSpacing.small
            ))
    return componentes


def _contar_componentes_aninhados(item) -> int:
    return 1 + sum(
        _contar_componentes_aninhados(filho)
        for filho in (getattr(item, "children", None) or [])
    )


def _card_form_view(origem: discord.ui.View, embed: discord.Embed | list[discord.Embed] | None = None,
                    titulo: str = "CENTRAL DE INSCRIÇÕES", descricao: str = "",
                    marcador: str = "NÊMESIS • Gestão de Inscrições") -> discord.ui.LayoutView:
    """Mantém conteúdo integral, mídias e controles no mesmo cartão Components V2."""
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    if isinstance(embed, (list, tuple)):
        embeds = [item for item in embed if isinstance(item, discord.Embed)]
    elif isinstance(embed, discord.Embed):
        embeds = [embed]
    else:
        embeds = []

    if embeds:
        componentes = _componentes_embed_inscricoes(embeds)
    else:
        texto = f"## {titulo}\n{descricao}".strip()
        componentes = [
            discord.ui.TextDisplay(bloco)
            for bloco in _dividir_texto_componentes(texto)
        ]

    componentes.append(discord.ui.Separator(
        visible=True, spacing=discord.SeparatorSpacing.small
    ))
    seletores, botoes = [], []
    for item in origem.children:
        if isinstance(item, discord.ui.UserSelect):
            novo = discord.ui.UserSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, custom_id=item.custom_id,
                disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.RoleSelect):
            novo = discord.ui.RoleSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, custom_id=item.custom_id,
                disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.ChannelSelect):
            novo = discord.ui.ChannelSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, channel_types=list(item.channel_types),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.MentionableSelect):
            novo = discord.ui.MentionableSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, custom_id=item.custom_id,
                disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    clone_resolvido = clone._resolved
                    original._resolved = clone_resolvido
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            botoes.append(novo)

    for seletor in seletores:
        componentes.append(discord.ui.ActionRow(seletor))
    for inicio in range(0, len(botoes), 5):
        componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(f"-# {marcador}"),
    ])

    # O Discord limita a 40 componentes no total, contando itens aninhados.
    # Falhar explicitamente é preferível a truncar respostas do candidato.
    total_componentes = 1 + sum(_contar_componentes_aninhados(item) for item in componentes)
    if total_componentes > 40:
        raise ValueError(
            "O dossiê excede o limite de 40 componentes do Discord; "
            "é necessário paginar o conteúdo antes de publicar o cartão."
        )
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


def _mensagem_tem_cartao_inscricoes(mensagem: discord.Message) -> bool:
    pendentes = list(getattr(mensagem, "components", []) or [])
    while pendentes:
        item = pendentes.pop()
        if "central de recrutamento" in str(getattr(item, "content", "") or "").casefold():
            return True
        pendentes.extend(list(getattr(item, "children", []) or []))
    return False


def _view_central_inscricoes(lista: list, embed: discord.Embed) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    seletor = SeletorInscricaoPublico(lista)
    componentes = _componentes_embed_inscricoes([embed])
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("### ◈ ACESSO AOS PROCESSOS SELETIVOS"),
        discord.ui.ActionRow(seletor),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# Nêmesis Systeam"),
    ])
    view.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
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
    """Modal de até cinco perguntas, com campos de texto e escolhas nativas do Discord."""

    def __init__(self, formulario: dict, pagina_indice: int = 0, respostas_acumuladas: list = None, usuario_id: int = None):
        paginas = _paginas_modal(formulario)
        pagina_info = paginas[pagina_indice] if 0 <= pagina_indice < len(paginas) else {
            "titulo": f"Etapa {pagina_indice + 1}",
            "perguntas": [],
        }
        pagina = pagina_info["perguntas"]
        total_paginas = len(paginas)
        nome_formulario = str(formulario.get("nome") or formulario.get("titulo_painel") or "Formulário")
        nome_etapa = str(pagina_info.get("titulo") or f"Etapa {pagina_indice + 1}")
        titulo = f"{nome_formulario[:18]} · {nome_etapa[:18]}"
        if total_paginas > 1:
            titulo = f"{titulo} ({pagina_indice + 1}/{total_paginas})"
        super().__init__(title=titulo[:45])

        self.formulario = formulario
        self.pagina_indice = pagina_indice
        self.respostas_acumuladas = respostas_acumuladas or []
        self.usuario_id = usuario_id
        self.inputs = []

        for indice, pergunta in enumerate(pagina[:5], start=1):
            texto = _texto_pergunta(pergunta)
            obrigatoria = pergunta.get("obrigatoria", True) if isinstance(pergunta, dict) else True
            tipo = _tipo_pergunta(pergunta)
            rotulo = f"Questão {indice:02d}"

            if tipo == "escolha":
                opcoes = []
                vistos = set()
                for opcao in (pergunta.get("opcoes") or []):
                    valor = str(opcao or "").strip()
                    if not valor:
                        continue
                    chave = valor.casefold()
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    opcoes.append(valor[:100])
                    if len(opcoes) == 25:
                        break
                if len(opcoes) >= 2:
                    campo = discord.ui.Select(
                        placeholder="Selecione uma opção",
                        min_values=1 if obrigatoria else 0,
                        max_values=1,
                        required=bool(obrigatoria),
                        options=[discord.SelectOption(label=opcao, value=opcao) for opcao in opcoes],
                    )
                    self.inputs.append(campo)
                    self.add_item(discord.ui.Label(
                        text=rotulo,
                        description=texto[:100] or "Escolha uma das opções disponíveis.",
                        component=campo,
                    ))
                    continue

            estilo = discord.TextStyle.short if tipo == "texto" else discord.TextStyle.paragraph
            campo = discord.ui.TextInput(
                style=estilo,
                required=bool(obrigatoria),
                max_length=1000,
                placeholder=texto[:100] or "Digite sua resposta...",
            )
            self.inputs.append(campo)
            self.add_item(discord.ui.Label(
                text=rotulo,
                description=texto[:100] or None,
                component=campo,
            ))

    async def on_submit(self, interaction: discord.Interaction):
        respostas_desta_pagina = []
        for campo in self.inputs:
            if isinstance(campo, discord.ui.Select):
                valor = campo.values[0] if campo.values else ""
            else:
                valor = str(campo.value or "")
            respostas_desta_pagina.append(str(valor).strip() or "—")
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
                view=_card_form_view(
                    view, None, "INSCRIÇÃO • ETAPA CONCLUÍDA",
                    f"Etapa {self.pagina_indice + 1} concluída. Continue para responder às próximas perguntas.",
                ),
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
        pendentes = await formularios.listar_respostas(
            guild.id, formulario_id=self.formulario["id"], status="pendente"
        )
        if any(int(item.get("autor_id", 0)) == interaction.user.id for item in pendentes):
            await interaction.response.send_message(
                "Você já possui uma candidatura pendente para este formulário. Aguarde a avaliação da equipe.",
                ephemeral=True,
            )
            return

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
        if not _administrador_formularios(interaction, self.central.usuario_id, self.central.guild_id):
            await interaction.response.send_message("Esta central pertence a outra pessoa ou servidor.", ephemeral=True)
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
            view=_card_form_view(view, view.montar_embed()), ephemeral=True,
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
        instrucao = (
            "Selecione uma ficha para abrir o dossiê, consultar as respostas e continuar a avaliação."
            if self.pendentes
            else "Nenhuma ficha está pendente neste momento. Use **Atualizar fila** para consultar novas candidaturas."
        )
        return criar_embed(
            "𓂀 FILA RESTRITA · CANDIDATURAS",
            f"**FORMULÁRIO**　{self.central.formulario_id}\n"
            f"**PENDENTES**　{len(self.pendentes)}\n"
            f"**PÁGINA**　{self.pagina + 1}/{self.total_paginas}\n\n"
            f"{instrucao}",
            cor=0x9F1239,
            rodape="NÊMESIS • ACESSO ADMINISTRATIVO",
        )

    def _montar(self):
        self.clear_items()
        inicio = self.pagina * 25
        fichas_da_pagina = self.pendentes[inicio:inicio + 25]
        # O Discord não aceita um Select sem opções. Quando a fila zera após
        # uma decisão, mantém somente os controles de navegação desativados e
        # a atualização, evitando que a interação falhe ao redesenhar a view.
        if fichas_da_pagina:
            self.add_item(SeletorFichaPendente(self.central, fichas_da_pagina))
        self.anterior.disabled = not self.pendentes or self.pagina <= 0
        self.proxima.disabled = not self.pendentes or self.pagina >= self.total_paginas - 1
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
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed())
        )

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar_interacao(interaction):
            return
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._montar()
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed())
        )

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
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed())
        )


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
            view=_card_form_view(
                _view_resposta(protocolo), anexos[:10],
                marcador="NÊMESIS • DOSSIÊ DE CANDIDATURA • V2",
            ),
            ephemeral=True,
        )
        for inicio in range(10, len(anexos), 10):
            await interaction.followup.send(embeds=anexos[inicio:inicio + 10], ephemeral=True)


def _administrador_formularios(
    interaction: discord.Interaction,
    usuario_id: int,
    guild_id: int | None = None,
) -> bool:
    return bool(
        interaction.guild is not None
        and (guild_id is None or interaction.guild.id == guild_id)
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


class ModalEditarEtapa(discord.ui.Modal):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario_id: str, indice: int, titulo_atual: str):
        super().__init__(title=f"Editar etapa {indice + 1}")
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id, self.indice = formulario_id, indice
        self.titulo = discord.ui.TextInput(
            default=str(titulo_atual or f"Etapa {indice + 1}")[:100],
            max_length=100,
            placeholder="Ex.: Informações pessoais",
        )
        self.add_item(discord.ui.Label(text="Nome da etapa", component=self.titulo))

    async def on_submit(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id, self.guild_id):
            await interaction.response.send_message("A edição da etapa é restrita à administração que abriu a central.", ephemeral=True)
            return
        titulo = str(self.titulo.value or "").strip()
        if not titulo:
            await interaction.response.send_message("Informe um nome para a etapa.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok = await formularios.atualizar_pagina(self.guild_id, self.formulario_id, self.indice, titulo)
        if not ok:
            await interaction.followup.send("A etapa não existe mais. Atualize a central.", ephemeral=True)
            return
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(
            interaction, self.guild_id, self.usuario_id, self.formulario_id,
            f"Etapa {self.indice + 1} renomeada para **{titulo}**.",
        )


class SeletorPaginaEditar(discord.ui.Select):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario: dict):
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id = str(formulario["id"])
        opcoes = []
        for indice, pagina in enumerate(formulario.get("paginas", [])):
            perguntas = pagina.get("perguntas", []) if isinstance(pagina, dict) else pagina if isinstance(pagina, list) else []
            titulo = pagina.get("titulo") if isinstance(pagina, dict) else f"Etapa {indice + 1}"
            opcoes.append(discord.SelectOption(
                label=f"Etapa {indice + 1} · {str(titulo or '')[:65]}"[:100],
                value=str(indice),
                description=f"{len(perguntas)} pergunta(s)",
            ))
        super().__init__(
            placeholder="Selecione a etapa que deseja renomear",
            min_values=1,
            max_values=1,
            options=opcoes[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id, self.guild_id):
            await interaction.response.send_message("A edição da etapa é restrita à administração que abriu a central.", ephemeral=True)
            return
        indice = int(self.values[0])
        formulario = await formularios.get_formulario(self.guild_id, self.formulario_id)
        if not formulario or not 0 <= indice < len(formulario.get("paginas", [])):
            await interaction.response.send_message("A etapa não existe mais. Atualize a central.", ephemeral=True)
            return
        pagina = formulario["paginas"][indice]
        titulo = pagina.get("titulo") if isinstance(pagina, dict) else f"Etapa {indice + 1}"
        await interaction.response.send_modal(ModalEditarEtapa(
            self.cog, self.guild_id, self.usuario_id, self.formulario_id, indice, str(titulo or "")
        ))


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
            view=_card_form_view(
                ConfirmarRemocaoPaginaView(self.cog, self.guild_id, self.usuario_id, self.formulario_id, indice),
                None, "CONFIRMAR REMOÇÃO",
                f"Confirme a remoção da etapa **{indice + 1}**. As candidaturas existentes não serão apagadas.",
            ),
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
        await interaction.response.edit_message(
            view=_card_form_view(
                self, None, "COMISSÃO DE ANÁLISE",
                f"Cargos selecionados: **{len(self.selected_role_ids)}**. Salve para aplicar.",
            )
        )

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
    def __init__(
        self, cog, guild_id: int, usuario_id: int, formulario_id: str,
        indice_global: int, texto_atual: str, tipo_atual: str = "paragrafo",
        obrigatoria_atual: bool = True, opcoes_atuais: list[str] | None = None,
    ):
        super().__init__(title=f"Editar pergunta {indice_global + 1}"[:45])
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id, self.indice_global = formulario_id, indice_global
        tipo_atual = tipo_atual if tipo_atual in {"texto", "paragrafo", "escolha"} else "paragrafo"
        self.texto = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, default=str(texto_atual or "")[:256], max_length=256,
        )
        self.tipo = discord.ui.Select(
            placeholder="Tipo de resposta", min_values=1, max_values=1, required=True,
            options=[
                discord.SelectOption(label="Texto curto", value="texto", default=tipo_atual == "texto"),
                discord.SelectOption(label="Texto longo", value="paragrafo", default=tipo_atual == "paragrafo"),
                discord.SelectOption(label="Escolha única", value="escolha", default=tipo_atual == "escolha"),
            ],
        )
        self.obrigatoria = discord.ui.Select(
            placeholder="Obrigatoriedade", min_values=1, max_values=1, required=True,
            options=[
                discord.SelectOption(label="Obrigatória", value="sim", default=bool(obrigatoria_atual)),
                discord.SelectOption(label="Opcional", value="nao", default=not bool(obrigatoria_atual)),
            ],
        )
        texto_opcoes = "\n".join(str(item) for item in (opcoes_atuais or []))[:3000]
        self.opcoes = discord.ui.TextInput(
            style=discord.TextStyle.paragraph, required=False, default=texto_opcoes or None,
            placeholder="Uma opção por linha (ou separadas por |). Máximo: 25.", max_length=3000,
        )
        self.add_item(discord.ui.Label(text="Enunciado", component=self.texto))
        self.add_item(discord.ui.Label(text="Tipo de resposta", component=self.tipo))
        self.add_item(discord.ui.Label(text="Obrigatoriedade", component=self.obrigatoria))
        self.add_item(discord.ui.Label(
            text="Opções da escolha", description="Usado somente no tipo Escolha única.",
            component=self.opcoes,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id, self.guild_id):
            await interaction.response.send_message("A edição de perguntas é restrita à administração que abriu a central.", ephemeral=True)
            return
        tipo = self.tipo.values[0] if self.tipo.values else "paragrafo"
        obrigatoria = bool(self.obrigatoria.values and self.obrigatoria.values[0] == "sim")
        opcoes = [
            parte.strip()
            for linha in str(self.opcoes.value or "").splitlines()
            for parte in linha.split("|")
            if parte.strip()
        ]
        if tipo == "escolha":
            if len(opcoes) < 2:
                await interaction.response.send_message("Uma pergunta de escolha única precisa de pelo menos duas opções.", ephemeral=True)
                return
            if len(opcoes) > 25:
                await interaction.response.send_message("O Discord permite no máximo 25 opções por pergunta.", ephemeral=True)
                return
            if any(len(opcao) > 100 for opcao in opcoes):
                await interaction.response.send_message("Cada opção pode ter no máximo 100 caracteres.", ephemeral=True)
                return
        else:
            opcoes = []

        await interaction.response.defer(ephemeral=True, thinking=True)
        ok = await formularios.atualizar_pergunta(
            self.guild_id, self.formulario_id, self.indice_global, self.texto.value,
            tipo=tipo, obrigatoria=obrigatoria, opcoes=opcoes,
        )
        if not ok:
            await interaction.followup.send("Não foi possível salvar a pergunta. Confira o enunciado e as opções.", ephemeral=True)
            return
        await self.cog.atualizar_central_inscricoes(interaction.guild)
        await self.cog.enviar_central_formularios(
            interaction, self.guild_id, self.usuario_id, self.formulario_id,
            "Pergunta e configuração atualizadas. Os dossiês existentes continuam exibindo os enunciados originais.",
        )


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
        await interaction.response.edit_message(
            view=_card_form_view(
                self, None, "EDIÇÃO DO FORMULÁRIO",
                f"Página {self.pagina + 1}/{self.total_paginas}. Selecione uma opção para continuar.",
            )
        )

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._montar()
        await interaction.response.edit_message(
            view=_card_form_view(
                self, None, "EDIÇÃO DO FORMULÁRIO",
                f"Página {self.pagina + 1}/{self.total_paginas}. Selecione uma opção para continuar.",
            )
        )


class SeletorPerguntaEditar(discord.ui.Select):
    def __init__(self, cog, guild_id: int, usuario_id: int, formulario: dict, pagina: int = 0):
        self.cog, self.guild_id, self.usuario_id = cog, guild_id, usuario_id
        self.formulario_id = str(formulario["id"])
        self.perguntas = _perguntas_flat(formulario)
        inicio = pagina * 25
        opcoes = [
            discord.SelectOption(
                label=f"Questão {indice + 1:02d}",
                value=str(indice),
                description=_texto_pergunta(pergunta)[:100],
            )
            for indice, pergunta in enumerate(self.perguntas[inicio:inicio + 25], start=inicio)
        ]
        super().__init__(placeholder=f"Selecione uma pergunta · página {pagina + 1}", min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        if not _administrador_formularios(interaction, self.usuario_id) or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("A edição é restrita à administração que abriu a central.", ephemeral=True)
            return
        indice = int(self.values[0])
        pergunta = self.perguntas[indice]
        tipo = _tipo_pergunta(pergunta)
        obrigatoria = pergunta.get("obrigatoria", True) if isinstance(pergunta, dict) else True
        opcoes = pergunta.get("opcoes", []) if isinstance(pergunta, dict) else []
        await interaction.response.send_modal(ModalEditarPergunta(
            self.cog, self.guild_id, self.usuario_id, self.formulario_id, indice,
            _texto_pergunta(pergunta), tipo, bool(obrigatoria), opcoes,
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
                discord.SelectOption(label="Renomear etapa", value="editar_etapa"),
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
        if acao == "editar_etapa":
            paginas = formulario.get("paginas", [])
            if not paginas:
                await interaction.response.send_message("Este formulário ainda não possui etapas.", ephemeral=True)
                return
            view = discord.ui.View(timeout=120)
            view.add_item(SeletorPaginaEditar(central.cog, interaction.guild.id, interaction.user.id, formulario))
            await interaction.response.send_message(
                view=_card_form_view(view, None, "EDITAR ETAPA", "Escolha a etapa cujo título deseja alterar."), ephemeral=True,
            )
            return
        if acao == "editar_pergunta":
            perguntas = _perguntas_flat(formulario)
            if not perguntas:
                await interaction.response.send_message("Este formulário ainda não possui perguntas.", ephemeral=True)
                return
            view = EditarPerguntasView(central.cog, interaction.guild.id, interaction.user.id, formulario)
            await interaction.response.send_message(
                view=_card_form_view(
                    view, None, "EDITAR PERGUNTAS",
                    f"Selecione a pergunta que deseja editar. Total: **{len(perguntas)}** · página **1/{view.total_paginas}**.",
                ), ephemeral=True,
            )
            return
        if acao == "remover_etapa":
            paginas = formulario.get("paginas", [])
            if not paginas:
                await interaction.response.send_message("Este formulário ainda não possui etapas.", ephemeral=True)
                return
            view = discord.ui.View(timeout=120)
            view.add_item(SeletorPaginaRemover(central.cog, interaction.guild.id, interaction.user.id, formulario))
            await interaction.response.send_message(
                view=_card_form_view(view, None, "REMOVER ETAPA", "Escolha a etapa que deseja remover. A remoção exige confirmação."), ephemeral=True
            )
            return
        if acao == "cargos":
            view = GerenciarCargosView(central.cog, interaction.guild, interaction.user.id, formulario)
            await interaction.response.send_message(
                view=_card_form_view(
                    view, None, "COMISSÃO DE ANÁLISE",
                    f"Formulário: **{formulario.get('nome', 'Formulário')}**\nSelecione os cargos que receberão as fichas. O instrutor padrão continua sendo notificado automaticamente.",
                ), ephemeral=True,
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
        view = FilaHistoricoView(central, encerradas)
        await interaction.response.send_message(
            view=_card_form_view(view, view.montar_embed()), ephemeral=True
        )


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
        instrucao = (
            "Selecione uma ficha para consultar o dossiê e a trilha de auditoria."
            if self.respostas
            else "Ainda não existem candidaturas encerradas. Use **Atualizar histórico** para consultar novos resultados."
        )
        return criar_embed(
            "𓂀 HISTÓRICO · CANDIDATURAS ENCERRADAS",
            f"**FORMULÁRIO**　{self.central.formulario_id}\n"
            f"**TOTAL**　{len(self.respostas)}\n"
            f"**APROVADAS**　{aprovadas}　 **RECUSADAS**　{recusadas}\n"
            f"**PÁGINA**　{self.pagina + 1}/{self.total_paginas}\n\n"
            f"{instrucao}",
            cor=0x9F1239,
            rodape="NÊMESIS • HISTÓRICO RESTRITO",
        )

    def _montar(self):
        self.clear_items()
        inicio = self.pagina * 25
        fichas_da_pagina = self.respostas[inicio:inicio + 25]
        if fichas_da_pagina:
            self.add_item(SeletorFichaHistorica(self.central, fichas_da_pagina))
        self.anterior.disabled = not self.respostas or self.pagina <= 0
        self.proxima.disabled = not self.respostas or self.pagina >= self.total_paginas - 1
        self.add_item(self.anterior)
        self.add_item(self.proxima)
        self.add_item(self.atualizar_historico)

    async def _validar(self, interaction: discord.Interaction):
        if interaction.user.id != self.central.usuario_id or interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("O histórico é restrito à administração que abriu a central.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Atualizar histórico", style=discord.ButtonStyle.primary, emoji="🔄")
    async def atualizar_historico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        respostas = await formularios.listar_respostas(
            interaction.guild.id,
            formulario_id=self.central.formulario_id,
        )
        self.respostas = [
            item for item in respostas
            if item.get("status") in {"aprovada", "recusada"}
        ]
        self.respostas.sort(
            key=lambda item: float(item.get("atualizado_em", item.get("criado_em", 0)) or 0),
            reverse=True,
        )
        self.pagina = min(self.pagina, self.total_paginas - 1)
        self._montar()
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed())
        )

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = max(0, self.pagina - 1)
        self._montar()
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed())
        )

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._validar(interaction):
            return
        self.pagina = min(self.total_paginas - 1, self.pagina + 1)
        self._montar()
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed())
        )


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
        await interaction.response.send_message(
            view=_card_form_view(view, anexos[:10]), ephemeral=True
        )
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _administrador_formularios(interaction, self.usuario_id, self.guild_id):
            await interaction.response.send_message(
                "Esta central é privada e só pode ser utilizada pela liderança que a abriu no servidor de origem.",
                ephemeral=True,
            )
            return False
        return True

    def montar_embed(self, mensagem: str | None = None):
        formulario = next((item for item in self.lista if str(item.get("id")) == str(self.formulario_id)), None)
        if not formulario:
            return criar_embed("✦・ CENTRAL DE FORMULÁRIOS ・✦", "Nenhum formulário disponível.", cor=0x9F1239)
        status = "ARQUIVADO" if formulario.get("arquivado") else "ATIVO" if formulario.get("ativo", True) else "PAUSADO"
        paginas = formulario.get("paginas", []) if isinstance(formulario.get("paginas", []), list) else []
        linhas_etapas = []
        for indice, pagina in enumerate(paginas[:6], start=1):
            perguntas_pagina = pagina.get("perguntas", []) if isinstance(pagina, dict) else pagina if isinstance(pagina, list) else []
            titulo_etapa = pagina.get("titulo") if isinstance(pagina, dict) else f"Etapa {indice}"
            linhas_etapas.append(f"• **{indice}. {str(titulo_etapa or f'Etapa {indice}')[:55]}** — {len(perguntas_pagina)} pergunta(s)")
        if len(paginas) > 6:
            linhas_etapas.append(f"• + {len(paginas) - 6} etapa(s)")
        if not linhas_etapas:
            linhas_etapas = ["• Nenhuma etapa configurada."]
        contagem_tipos = {"texto": 0, "paragrafo": 0, "escolha": 0}
        for pergunta in _perguntas_flat(formulario):
            contagem_tipos[_tipo_pergunta(pergunta)] += 1
        resumo_tipos = (
            f"Texto curto: {contagem_tipos['texto']} · Texto longo: {contagem_tipos['paragrafo']} · "
            f"Escolha única: {contagem_tipos['escolha']}"
        )
        corpo = (
            f"**FORMULÁRIO**\n{formulario.get('nome', 'Sem nome')}\n\n"
            f"**SITUAÇÃO**　{status}\n"
            f"**IDENTIFICADOR**　{formulario.get('id')}\n"
            f"**ETAPAS**　{len(_paginas_modal(formulario)):02d}\n"
            f"**PERGUNTAS**　{len(_perguntas_flat(formulario)):02d}\n"
            f"**CARGOS NOTIFICADOS**　{len(formulario.get('cargos_notificar', [])):02d}\n\n"
            f"**ESTRUTURA DAS ETAPAS**\n{chr(10).join(linhas_etapas)}\n\n"
            f"**TIPOS DE RESPOSTA**\n{resumo_tipos}"
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
        await interaction.response.edit_message(
            view=_card_form_view(self, self.montar_embed(mensagem))
        )


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
        await interaction.followup.send(
            view=_card_form_view(view, view.montar_embed(mensagem)), ephemeral=True
        )

    async def formulario_central(self, interaction: discord.Interaction):
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Acesso restrito à liderança autorizada da NÊMESIS.", ephemeral=True)
            return
        lista = await formularios.listar_formularios(interaction.guild.id)
        lista.sort(key=lambda item: (bool(item.get("arquivado")), str(item.get("nome", "")).casefold()))
        view = CentralFormulariosView(self, interaction.guild.id, interaction.user.id, lista)
        await interaction.response.send_message(
            view=_card_form_view(view, view.montar_embed()), ephemeral=True
        )

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
                    # Cada processo seletivo é identificado pelo próprio nome e chave.
                    # Nunca reutiliza o registro de Staff para criar/atualizar o ingresso geral.
                    formulario = next(
                        (item for item in lista if item.get("nome") == definicao["nome"]),
                        None,
                    )
                    if formulario is None:
                        formulario = await formularios.criar_formulario(
                            guild.id, definicao["nome"], definicao["titulo"],
                            definicao["descricao"], None, self.bot.user.id if self.bot.user else 0,
                        )
                    if int(formulario.get("versao_automatico", 0) or 0) < 3:
                        formulario = await formularios.atualizar_formulario(
                            guild.id,
                            formulario["id"],
                            nome=definicao["nome"],
                            titulo_painel=definicao["titulo"],
                            descricao_painel=definicao["descricao"],
                            paginas=definicao["paginas"],
                            versao_automatico=3,
                        )
                        if formulario is None:
                            raise RuntimeError(f"Não foi possível configurar o formulário {definicao['nome']}.")
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
        view = _view_central_inscricoes(lista, embed)
        if mensagem_existente is not None:
            if not _mensagem_tem_cartao_inscricoes(mensagem_existente):
                await mensagem_existente.edit(content=None, embeds=[], attachments=[])
            mensagem = await mensagem_existente.edit(view=view)
            acao = "atualizada"
        else:
            mensagem = await canal.send(view=view)
            acao = "publicada"
        estado.pop("staff", None)
        estado["central_inscricoes"] = {"canal_id": canal_id, "mensagem_id": mensagem.id, "tipo": "seletor_dinamico"}
        await salvar(ARQUIVO_PAINÉIS_AUTOMÁTICOS, estado)
        if not getattr(self, "_view_inscricoes_registrada", False):
            self.bot.add_view(_view_central_inscricoes(lista, embed))
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