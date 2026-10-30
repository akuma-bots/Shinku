import asyncio
import logging
import re
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import criar_embed, aplicar_identidade_servidor

from utils import missoes
from utils.catalogo_missoes import (
    carregar_catalogo,
    sincronizar_catalogo,
    salvar_mensagem_discord,
    obter_mensagem_discord,
)
from utils.guild_config import get_config
from utils import ranking_missoes_jogos
from utils.perfis import (
    get_perfil,
    _salvar_perfil,
    calcular_patente_atual,
    definir_patente,
)


log = logging.getLogger(__name__)


class EnviarProvaMissaoModal(discord.ui.Modal, title="Enviar provas da missão"):
    missao_id = discord.ui.TextInput(
        label="ID da missão",
        placeholder="Ex.: SHI-NM001",
        required=True,
        max_length=50,
    )
    imagem_url = discord.ui.TextInput(
        label="Link da imagem da prova (Discord)",
        placeholder="Envie a imagem no Discord e cole o link da imagem",
        required=True,
        max_length=1000,
    )
    auxiliar = discord.ui.TextInput(
        label="Auxiliar (opcional)",
        placeholder="Mencione o membro ou informe o ID do Discord",
        required=False,
        max_length=30,
    )

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.receber_prova_modal(
            interaction,
            str(self.missao_id.value),
            str(self.imagem_url.value),
            str(self.auxiliar.value or ""),
        )


class EnviarProvaMissaoView(discord.ui.View):
    """Botão persistente para abrir o formulário de envio de provas."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="ENVIAR PROVAS",
        style=discord.ButtonStyle.primary,
        emoji="📨",
        custom_id="nemesis:missao:enviar_provas",
    )
    async def enviar_provas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EnviarProvaMissaoModal(self.cog))


class CategoriaMissoesSelect(discord.ui.Select):
    """Seletor persistente para trocar de departamento sem percorrer páginas."""
    def __init__(self, cog):
        self.cog = cog
        opcoes = [
            discord.SelectOption(label="Missões", value="missao", emoji="🎯", description="Atividades competitivas"),
            discord.SelectOption(label="Contribuições", value="contribuicao", emoji="✦", description="Mérito e desenvolvimento"),
            discord.SelectOption(label="Operações especiais", value="especial", emoji="✧", description="Protocolos especiais"),
        ]
        super().__init__(
            placeholder="Acessar departamento operacional",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:missoes:categoria",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("Este painel só pode ser utilizado no servidor.", ephemeral=True)
            return
        footer = interaction.message.embeds[0].footer.text if interaction.message.embeds else ""
        partes = footer.split(":")
        jogo = partes[1] if len(partes) > 1 and partes[1] in ranking_missoes_jogos.JOGOS else "shigaku"
        categoria = self.values[0]
        embed = await self.cog._montar_painel_missoes(interaction.guild, jogo, categoria)
        await interaction.response.edit_message(embed=embed, view=NavegacaoMissoesView(self.cog))


class NavegacaoMissoesView(discord.ui.View):
    """Navegação persistente por departamento, jogo e envio de evidências."""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(CategoriaMissoesSelect(cog))

    @discord.ui.button(label="Anterior", emoji="◀", style=discord.ButtonStyle.secondary, custom_id="nemesis:missoes:anterior", row=1)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.navegar_painel_missoes(interaction, -1)

    @discord.ui.button(label="Enviar evidência", emoji="📨", style=discord.ButtonStyle.success, custom_id="nemesis:missoes:provas", row=1)
    async def enviar_provas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EnviarProvaMissaoModal(self.cog))

    @discord.ui.button(label="Próximo", emoji="▶", style=discord.ButtonStyle.secondary, custom_id="nemesis:missoes:proxima", row=1)
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.navegar_painel_missoes(interaction, 1)


class NavegacaoRankingJogosView(discord.ui.View):
    """Alternador persistente entre rankings independentes por jogo."""
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Ranking anterior", style=discord.ButtonStyle.secondary, custom_id="nemesis:ranking_jogos:anterior")
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.navegar_painel_ranking(interaction, -1)

    @discord.ui.button(label="Próximo ranking", style=discord.ButtonStyle.primary, custom_id="nemesis:ranking_jogos:proximo")
    async def proximo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.navegar_painel_ranking(interaction, 1)


TIPOS = {
    "missao": {
        "nome": "Missão",
        "plural": "MISSÕES",
        "emoji": "🎯",
        "cor": 0x9F2035,
        "assinatura": "AÇÃO • DESEMPENHO • COMPETITIVIDADE",
    },
    # O valor interno antigo é mantido para compatibilidade com os dados existentes.
    "contribuicao": {
        "nome": "Contribuição",
        "plural": "CONTRIBUIÇÕES",
        "emoji": "✦",
        "cor": 0x9A7836,
        "assinatura": "APOIO • EVOLUÇÃO • COMPROMISSO",
    },
    "especial": {
        "nome": "Missão especial",
        "plural": "OPERAÇÕES ESPECIAIS",
        "emoji": "✧",
        "cor": 0x754A9E,
        "assinatura": "ACESSO ESPECIAL • OBJETIVOS DE DESTAQUE",
    },
}

CANAIS_PADRAO = {
    "canal_missoes_missao_id": 1556543214885019668,
    "canal_missoes_contribuicao_id": 1556543539213639760,
    "canal_missoes_especial_id": 1556543708478972015,
    "canal_provas_missao_id": 1556543417843056641,
    "canal_provas_contribuicao_id": 1556543628296593448,
    "canal_provas_especial_id": 1556543872534839336,
}

NOMES_CANAIS = {}


class Missoes(commands.Cog):
    """Missões permanentes definidas no GitHub e revisão de provas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sync_lock = asyncio.Lock()
        self._reward_lock = asyncio.Lock()
        # O custom_id fixo mantém o botão funcional mesmo após reinícios do bot.
        self.bot.add_view(EnviarProvaMissaoView(self))
        self.bot.add_view(NavegacaoMissoesView(self))
        self.bot.add_view(NavegacaoRankingJogosView(self))
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        for tipo in ("missao", "contribuicao", "especial"):
            bot.processadores_revisao[tipo] = self.processar_aprovacao

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(1563995879981981817)
        if guild is None:
            log.warning("Missões padrão: servidor NÊMESIS não encontrado no cache.")
            return
        await self.sincronizar_missoes_discord(guild)

    async def _resolver_canal(self, guild: discord.Guild, canal_id: int):
        canal = guild.get_channel(int(canal_id))
        if canal is None:
            try:
                canal = await guild.fetch_channel(int(canal_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível resolver o canal %s: %s", canal_id, erro)
                return None
        return canal if isinstance(canal, discord.TextChannel) else None

    async def _renomear_canais_pontuacao(self, guild: discord.Guild, config: dict):
        bot_member = guild.me
        if bot_member is None:
            return
        for chave, nome_novo in NOMES_CANAIS.items():
            canal_id = config.get(chave) or CANAIS_PADRAO.get(chave)
            if not canal_id:
                continue
            canal = await self._resolver_canal(guild, canal_id)
            if canal is None or canal.name == nome_novo:
                continue
            if not canal.permissions_for(bot_member).manage_channels:
                log.warning("Sem permissão para renomear o canal %s para %s.", canal.id, nome_novo)
                continue
            try:
                await canal.edit(name=nome_novo, reason="Padronização do sistema de missões da NÊMESIS")
            except discord.HTTPException:
                log.exception("Falha ao renomear o canal %s.", canal.id)

    @staticmethod
    def _dividir_descricao(descricao: str, limite: int = 3800) -> list[str]:
        """Divide descrições longas em blocos compatíveis com o limite do Discord."""
        texto = str(descricao if descricao is not None else "")
        if not texto:
            texto = "Consulte a descrição com a liderança."
        if len(texto) > 20000:
            texto = texto[:20000]

        partes = []
        while texto:
            if len(texto) <= limite:
                partes.append(texto)
                break

            corte = texto.rfind(chr(10), 0, limite)
            if corte < limite // 2:
                corte = texto.rfind(" ", 0, limite)
            if corte < limite // 2:
                corte = limite
            elif corte < limite:
                # Mantém a quebra de linha/espaço para não perder caracteres.
                corte += 1

            partes.append(texto[:corte])
            texto = texto[corte:]

        return partes or ["Consulte a descrição com a liderança."]

    @classmethod
    def _montar_embeds(cls, atividade: dict) -> list[discord.Embed]:
        """Cria cartões consistentes para o catálogo público de missões."""
        tipo_chave = str(atividade.get("tipo", "missao")).strip().lower()
        tipo = TIPOS.get(tipo_chave, TIPOS["missao"])
        ativa = atividade.get("ativa", True) is not False

        try:
            recompensa = max(
                0,
                int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0),
            )
        except (TypeError, ValueError):
            recompensa = 0

        missao_id = str(atividade.get("id") or "—").strip()
        titulo_original = str(atividade.get("titulo") or "Operação sem título").strip()
        descricao_original = str(atividade.get("descricao") or "").strip()
        if not descricao_original:
            descricao_original = (
                "Os detalhes desta operação ainda não foram definidos. "
                "Consulte a liderança antes de iniciar."
            )

        origem = str(atividade.get("origem") or "oficial").strip().replace("_", " ").title()
        status = "OPERAÇÃO DISPONÍVEL" if ativa else "OPERAÇÃO ENCERRADA"
        status_icone = "◉" if ativa else "■"
        cores = {
            "missao": 0x9F2035,
            "contribuicao": 0x8B6A35,
            "especial": 0xC19A45,
        }
        cor = cores.get(tipo_chave, 0x9F2035)

        # A dificuldade é informativa e derivada dos dados existentes.
        # Um valor explícito no catálogo sempre tem prioridade.
        dificuldade = str(atividade.get("dificuldade") or "").strip()
        if not dificuldade:
            if tipo_chave == "especial" or recompensa >= 60:
                dificuldade = "Alta"
            elif recompensa >= 25:
                dificuldade = "Intermediária"
            else:
                dificuldade = "Moderada"

        requisitos = str(atividade.get("requisitos") or "").strip()
        prazo = str(atividade.get("prazo") or "").strip()
        partes = cls._dividir_descricao(descricao_original, limite=3000)
        embeds = []

        for indice, parte in enumerate(partes, start=1):
            sufixo = f"  ━  PARTE {indice}/{len(partes)}" if len(partes) > 1 else ""
            titulo = f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  {titulo_original}{sufixo}"[:256]
            cabecalho = (
                f"**{status_icone} {status}**  ·  **{tipo['nome'].upper()}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            embed = criar_embed(
                titulo,
                f"{cabecalho}\n\n{parte}",
                cor=cor,
                rodape=None,
            )
            embed.set_author(name="NÊMESIS  /  CENTRAL DE OPERAÇÕES")

            if indice == 1:
                jogo_slug = str(atividade.get("jogo") or "").strip().lower()
                jogo_nome = ranking_missoes_jogos.JOGOS.get(
                    jogo_slug, {}
                ).get("nome")
                identificacao = (
                    f"**Código**  `{missao_id}`\n"
                    f"**Categoria**  {tipo['nome']}\n"
                    f"**Origem**  {origem}"
                )
                if jogo_nome:
                    identificacao += f"\n**Jogo**  {jogo_nome}"
                embed.add_field(
                    name="◈ IDENTIFICAÇÃO",
                    value=identificacao,
                    inline=True,
                )
                embed.add_field(
                    name="◈ CLASSIFICAÇÃO",
                    value=(
                        f"**Dificuldade**  {dificuldade}\n"
                        f"**Estado**  {'Aberta' if ativa else 'Arquivada'}"
                    ),
                    inline=True,
                )
                embed.add_field(
                    name="◈ RECOMPENSA",
                    value=f"**{recompensa:,} XP** por aprovação".replace(",", "."),
                    inline=True,
                )

                if requisitos:
                    embed.add_field(
                        name="◈ REQUISITOS",
                        value=requisitos[:1024],
                        inline=False,
                    )
                if prazo:
                    embed.add_field(
                        name="◈ PRAZO",
                        value=prazo[:1024],
                        inline=True,
                    )

                if ativa:
                    embed.add_field(
                        name="◈ DIRETRIZES DA OPERAÇÃO",
                        value=(
                            "Leia o objetivo por completo e cumpra as condições descritas. "
                            "A evidência precisa corresponder à atividade e permitir a conferência."
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name="◈ CRITÉRIOS DE RECOMPENSA",
                        value=(
                            f"Responsável sem auxiliar: **{recompensa:,} XP** após aprovação.\n"
                            "Com auxiliar opcional: **60%** para o responsável e **40%** para o auxiliar.\n"
                            "A recompensa não é duplicada; a validação da staff continua obrigatória."
                        ).replace(",", "."),
                        inline=False,
                    )
                    embed.set_footer(
                        text="NÊMESIS  •  CATÁLOGO OFICIAL  •  Participação sujeita à validação da staff"
                    )
                else:
                    embed.add_field(
                        name="◈ REGISTRO DE ENCERRAMENTO",
                        value=(
                            "Esta operação foi encerrada. O cartão permanece disponível "
                            "para consulta e referência do catálogo."
                        ),
                        inline=False,
                    )
                    embed.set_footer(text="NÊMESIS  •  ARQUIVO DE OPERAÇÕES  •  SOMENTE CONSULTA")
            else:
                embed.set_footer(
                    text=f"NÊMESIS  •  CONTINUAÇÃO DA OPERAÇÃO  •  {indice}/{len(partes)}"
                )

            embeds.append(embed)

        return embeds

    @staticmethod
    def _slug_da_mensagem(mensagem, prefixo: str, padrao: str = "shigaku") -> str:
        if not mensagem or not getattr(mensagem, "embeds", None):
            return padrao
        rodape = str(mensagem.embeds[0].footer.text or "")
        marcador = prefixo + ":"
        for slug in ranking_missoes_jogos.JOGOS:
            if marcador + slug in rodape:
                return slug
        return padrao

    async def _montar_painel_missoes(
        self, guild: discord.Guild, jogo: str, categoria: str = "missao"
    ) -> discord.Embed:
        """Monta a central premium de atividades, compacta e dentro dos limites do Discord."""
        jogo = jogo if jogo in ranking_missoes_jogos.JOGOS else "shigaku"
        categoria = categoria if categoria in TIPOS else "missao"
        nome_jogo = ranking_missoes_jogos.JOGOS[jogo]["nome"]
        tipo = TIPOS[categoria]
        dados = await missoes._guild(guild.id)
        atividades = [
            item for item in dados.get("missoes", [])
            if isinstance(item, dict)
            and str(item.get("jogo") or "").strip().lower() == jogo
            and str(item.get("tipo") or "missao").strip().lower() == categoria
        ]
        atividades.sort(key=lambda item: str(item.get("id") or ""))
        abertas = [item for item in atividades if item.get("ativa", True) is not False]
        encerradas = len(atividades) - len(abertas)

        nomes_categoria = {
            "missao": "MISSÕES",
            "contribuicao": "CONTRIBUIÇÕES",
            "especial": "OPERAÇÕES ESPECIAIS",
        }
        nome_categoria = nomes_categoria.get(categoria, tipo["plural"].upper())
        embed = criar_embed(
            "✦・ CENTRAL DE MISSÕES — NÊMESIS ・✦",
            (
                "╭────────────── ◈ ──────────────╮\n"
                f"                 **{nome_categoria}  /  {nome_jogo.upper()}**\n"
                "╰────────────── ◈ ──────────────╯\n\n"
                f"Um catálogo estratégico de atividades da **NÊMESIS**. "
                "Selecione uma operação, cumpra seus objetivos e encaminhe "
                "a evidência para avaliação da equipe.\n\n"
                "**✧ Protocolo de envio**  /missao-enviar-prova\n"
                "**✧ Navegação**  Utilize os controles abaixo para explorar "
                "as categorias disponíveis."
            ),
            cor=tipo["cor"], rodape=None,
        )
        embed.set_author(name="N̷ÊMESIS  •  DEPARTAMENTO DE OPERAÇÕES")
        embed.add_field(
            name="◈  OPERAÇÕES ATIVAS",
            value=f"**{len(abertas):02d}**\nDisponíveis para execução",
            inline=True,
        )
        embed.add_field(
            name="◈  ARQUIVADAS",
            value=f"**{encerradas:02d}**\nOperações encerradas",
            inline=True,
        )
        embed.add_field(
            name="◈  TOTAL REGISTRADO",
            value=f"**{len(atividades):02d}**\nRegistros do catálogo",
            inline=True,
        )

        if not atividades:
            embed.add_field(
                name="╭・CATÁLOGO EM PREPARAÇÃO",
                value=(
                    "Esta seção ainda não possui operações publicadas. "
                    "Novas atividades serão disponibilizadas pela administração."
                ),
                inline=False,
            )

        exibidas = atividades[:20]
        for indice, item in enumerate(exibidas, start=1):
            try:
                recompensa = max(
                    0, int(item.get("recompensa_xp", item.get("pontos", 0)) or 0)
                )
            except (TypeError, ValueError, OverflowError):
                recompensa = 0
            ativa = item.get("ativa", True) is not False
            estado = "✦ EM OPERAÇÃO" if ativa else "◈ ARQUIVADA"
            titulo = str(item.get("titulo") or "Operação sem título").strip()
            descricao = str(item.get("descricao") or "Objetivo não informado.").strip()
            identificador = str(item.get("id") or "—")
            dificuldade = str(item.get("dificuldade") or "Não definida").strip()
            valor = (
                f"{descricao[:145]}\n\n"
                f"**IDENTIFICAÇÃO**  {identificador[:32]}\n"
                f"**NÍVEL**  {dificuldade[:36]}\n"
                f"**RECOMPENSA**  {recompensa:,} XP\n"
                f"**SITUAÇÃO**  {estado}"
            ).replace(",", ".")[:1024]
            embed.add_field(
                name=f"〔 {indice:02d} 〕  {titulo[:58]}"[:256],
                value=valor or "Informações indisponíveis.",
                inline=False,
            )

        if len(atividades) > len(exibidas):
            embed.add_field(
                name="✧  ARQUIVO COMPLEMENTAR",
                value=(
                    f"**{len(exibidas)} de {len(atividades)}** operações nesta visualização. "
                    "Avance pelo catálogo para consultar os demais registros."
                ),
                inline=False,
            )

        indice_jogo = list(ranking_missoes_jogos.JOGOS).index(jogo) + 1
        indice_categoria = list(TIPOS).index(categoria) + 1
        embed.set_footer(
            text=(
                f"PÁGINA:{jogo}:{categoria} • NÊMESIS  /  "
                f"{indice_jogo}/{len(ranking_missoes_jogos.JOGOS)} JOGOS • "
                f"{indice_categoria}/{len(TIPOS)} CATEGORIAS"
            )
        )

        def _tamanho_embed() -> int:
            return (
                len(embed.title or "")
                + len(embed.description or "")
                + len(embed.author.name or "")
                + len(embed.footer.text or "")
                + sum(len(field.name) + len(field.value) for field in embed.fields)
            )

        while embed.fields and (_tamanho_embed() > 5900 or len(embed.fields) > 25):
            embed.remove_field(len(embed.fields) - 1)
        aplicar_identidade_servidor(embed, guild, self.bot)
        return embed

    async def navegar_painel_missoes(self, interaction: discord.Interaction, delta: int) -> None:
        jogos = list(ranking_missoes_jogos.JOGOS)
        categorias = list(TIPOS)
        footer = interaction.message.embeds[0].footer.text if interaction.message.embeds else ""
        partes = footer.split(":")
        jogo = partes[1] if len(partes) > 1 and partes[1] in jogos else "shigaku"
        categoria = partes[2].split()[0] if len(partes) > 2 else "missao"
        if categoria not in categorias:
            categoria = "missao"
        paginas = [(j, c) for j in jogos for c in categorias]
        atual = paginas.index((jogo, categoria))
        alvo_jogo, alvo_categoria = paginas[(atual + delta) % len(paginas)]
        embed = await self._montar_painel_missoes(interaction.guild, alvo_jogo, alvo_categoria)
        await interaction.response.edit_message(embed=embed, view=NavegacaoMissoesView(self))

    async def _limpar_mensagens_missoes_duplicadas(self, guild: discord.Guild) -> int:
        """Remove mensagens antigas do bot sobre missões no canal central, preservando o painel oficial."""
        canal = await self._resolver_canal(guild, 1563995881315897549)
        if canal is None:
            return 0

        paineis = await ranking_missoes_jogos.obter_paineis(guild.id)
        painel_id = int(paineis.get("missoes") or 0)
        bot_id = self.bot.user.id if self.bot.user else 0
        termos = ("miss", "missão", "missões", "operação", "operações", "catálogo de operações")
        removidas = 0

        try:
            async for mensagem in canal.history(limit=1000):
                if mensagem.id == painel_id or mensagem.author.id != bot_id:
                    continue
                if not mensagem.embeds and not mensagem.content:
                    continue

                partes = [mensagem.content or ""]
                for embed in mensagem.embeds:
                    partes.extend([
                        embed.title or "",
                        embed.description or "",
                        embed.author.name if embed.author else "",
                        embed.footer.text or "",
                    ])
                    partes.extend(campo.name + " " + campo.value for campo in embed.fields)
                texto = " ".join(partes).casefold()
                if not any(termo in texto for termo in termos):
                    continue
                try:
                    await mensagem.delete(reason="Limpeza de mensagens duplicadas do sistema de missões NÊMESIS")
                    removidas += 1
                except discord.NotFound:
                    continue
                except (discord.Forbidden, discord.HTTPException):
                    log.warning("Não foi possível remover a mensagem duplicada de missões %s.", mensagem.id)
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Não foi possível consultar o histórico do canal central de missões.")
        return removidas

    async def _atualizar_painel_missoes(self, guild: discord.Guild) -> None:
        # Canal fixo oficial da Central de Missões da NÊMESIS.
        canal_id = 1563995881315897549
        canal = await self._resolver_canal(guild, canal_id)
        if canal is None:
            log.warning("Canal atual de missões não encontrado; painel não publicado.")
            return
        paineis = await ranking_missoes_jogos.obter_paineis(guild.id)
        mensagem = None
        if paineis.get("missoes"):
            try:
                mensagem = await canal.fetch_message(int(paineis["missoes"]))
            except discord.NotFound:
                mensagem = None
            except (discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível buscar o painel de missões: %s", erro)
                return
        jogo = self._slug_da_mensagem(mensagem, "PÁGINA", "shigaku")
        embed = await self._montar_painel_missoes(guild, jogo)
        try:
            if mensagem is None:
                mensagem = await canal.send(embed=embed, view=NavegacaoMissoesView(self))
                await ranking_missoes_jogos.salvar_painel(guild.id, "missoes", mensagem.id)
                try:
                    await mensagem.pin(reason="Painel de navegação de missões NÊMESIS")
                except discord.HTTPException:
                    pass
            else:
                await mensagem.edit(embed=embed, view=NavegacaoMissoesView(self))
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Não foi possível atualizar o painel de missões.")

    async def _montar_painel_ranking(self, guild: discord.Guild, jogo: str) -> discord.Embed:
        """Classificação competitiva com cartões por jogador e métricas resumidas."""
        jogo = jogo if jogo in ranking_missoes_jogos.JOGOS else "shigaku"
        nome_jogo = ranking_missoes_jogos.JOGOS[jogo]["nome"]
        linhas = await ranking_missoes_jogos.obter_ranking(guild.id, jogo, limite=10)
        pagina = list(ranking_missoes_jogos.JOGOS).index(jogo) + 1
        embed = criar_embed(
            f"🏆 RANKING {nome_jogo.upper()} · CIRCUITO COMPETITIVO",
            f"**JOGO SELECIONADO** · {nome_jogo}\n**QUADRO OFICIAL DE CLASSIFICAÇÃO**\n"
            "A classificação considera o XP obtido em missões aprovadas. "
            "As métricas adicionais ajudam a comparar desempenho, consistência e participação.",
            cor=0x9F2035, rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  DIVISÃO COMPETITIVA")
        aplicar_identidade_servidor(embed, guild, self.bot)
        if not linhas:
            embed.description += "\n\nAinda não há jogadores classificados neste quadro. Conclua missões e atividades oficiais e aguarde a validação das provas. Use os botões abaixo para alternar entre jogos."
            embed.add_field(name="AINDA SEM CLASSIFICADOS", value="Conclua missões e atividades oficiais e aguarde a validação das provas. Use os botões abaixo para alternar entre jogos.", inline=False)
        else:
            estatisticas = await ranking_missoes_jogos.obter_estatisticas_jogadores(
                guild.id, [uid for uid, _, _ in linhas], jogo=jogo
            )
            medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
            for posicao, (uid, nome, pontos) in enumerate(linhas, start=1):
                stats = estatisticas.get(str(uid), {})
                minutos = max(0, int(stats.get("tempo_top", 0))) // 60
                dias, resto = divmod(minutos, 1440)
                horas, minutos = divmod(resto, 60)
                tempo = f"{dias}d {horas}h" if dias else f"{horas}h {minutos}min"
                selo = medalhas.get(posicao, f"#{posicao:02d}")
                embed.description += f"\n\n{selo} <@{uid}> · **{pontos:,} XP**".replace(",", ".")
                embed.add_field(
                    name=f"{selo}  {nome[:70]}  ·  {pontos:,} XP".replace(",", ".")[:256],
                    value=(
                        f"<@{uid}>\n"
                        f"**V / E / D**  `{stats.get('vitorias', 0)} / {stats.get('empates', 0)} / {stats.get('derrotas', 0)}`  ·  "
                        f"**K/D**  `{stats.get('kills', 0)}/{stats.get('deaths', 0)}` ({stats.get('kdr', 0):.2f})\n"
                        f"**XP**  `{int(stats.get('xp', 0)):,}`  ·  **MVP**  `{stats.get('mvps', 0)}`  ·  "
                        f"**Patente**  `{str(stats.get('patente', '—'))[:40]}`\n"
                        f"**Tempo no Top 10**  `{tempo}`  ·  **Sequência**  `{stats.get('sequencia', 0)}/{stats.get('maior_sequencia', 0)}`"
                    ).replace(",", ".")[:1024],
                    inline=False,
                )
        embed.set_footer(text=f"PÁGINA:{jogo} • RANKING {pagina}/{len(ranking_missoes_jogos.JOGOS)}  •  Use os botões para alternar entre jogos")
        return embed

    async def navegar_painel_ranking(self, interaction: discord.Interaction, delta: int) -> None:
        jogos = list(ranking_missoes_jogos.JOGOS)
        atual = self._slug_da_mensagem(interaction.message, "PÁGINA", "shigaku")
        indice = jogos.index(atual) if atual in jogos else 0
        alvo = jogos[(indice + delta) % len(jogos)]
        embed = await self._montar_painel_ranking(interaction.guild, alvo)
        await interaction.response.edit_message(embed=embed, view=NavegacaoRankingJogosView(self))

    async def _atualizar_ranking_jogo(self, guild: discord.Guild, jogo: str) -> None:
        """Atualiza o painel único de ranking sem criar canais por jogo."""
        config = await get_config(guild.id)
        canal_id = config.get("canal_ranking_id") or 1545834182406574241
        canal = await self._resolver_canal(guild, int(canal_id))
        if canal is None:
            log.warning("Canal de ranking atual não encontrado; painel não atualizado.")
            return
        paineis = await ranking_missoes_jogos.obter_paineis(guild.id)
        mensagem = None
        if paineis.get("ranking"):
            try:
                mensagem = await canal.fetch_message(int(paineis["ranking"]))
            except discord.NotFound:
                mensagem = None
            except (discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível buscar o painel de ranking: %s", erro)
                return
        pagina = self._slug_da_mensagem(mensagem, "PÁGINA", jogo)
        embed = await self._montar_painel_ranking(guild, pagina)
        try:
            if mensagem is None:
                mensagem = await canal.send(embed=embed, view=NavegacaoRankingJogosView(self))
                await ranking_missoes_jogos.salvar_painel(guild.id, "ranking", mensagem.id)
                try:
                    await mensagem.pin(reason="Painel de ranking por jogo NÊMESIS")
                except discord.HTTPException:
                    pass
            else:
                await mensagem.edit(embed=embed, view=NavegacaoRankingJogosView(self))
        except (discord.Forbidden, discord.HTTPException) as erro:
            # O Discord rejeita edições após a mensagem atingir o limite de edições
            # (código 30046). Nesse caso, publica uma mensagem nova e troca o ID
            # persistido para que as próximas sincronizações não fiquem presas nela.
            if getattr(erro, "code", None) == 30046 and mensagem is not None:
                try:
                    nova_mensagem = await canal.send(
                        embed=embed,
                        view=NavegacaoRankingJogosView(self),
                    )
                    await ranking_missoes_jogos.salvar_painel(
                        guild.id, "ranking", nova_mensagem.id
                    )
                except Exception:
                    log.exception(
                        "O limite de edições do ranking foi atingido, mas não foi "
                        "possível publicar e registrar o painel substituto."
                    )
                    return

                try:
                    await nova_mensagem.pin(reason="Painel de ranking por jogo NÊMESIS")
                except discord.HTTPException:
                    log.warning("Não foi possível fixar o novo painel de ranking.")

                try:
                    await mensagem.delete(
                        reason="Substituição do painel após limite de edições do Discord"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    log.warning(
                        "O painel antigo de ranking %s não pôde ser removido.",
                        getattr(mensagem, "id", "desconhecido"),
                    )

                log.warning(
                    "Painel de ranking substituído após o limite de edições do Discord "
                    "(mensagem nova: %s).",
                    nova_mensagem.id,
                )
                return

            log.exception("Não foi possível atualizar o painel de ranking.")
    @staticmethod
    def _expandir_catalogo_por_jogo(catalogo: list) -> list:
        """Replica as missões padrão para Shigaku, Gakuran e Fistborn com IDs únicos."""
        resultado = []
        for slug, jogo in ranking_missoes_jogos.JOGOS.items():
            for definicao in catalogo:
                missao = dict(definicao)
                missao["id"] = f"{jogo['prefixo']}-{definicao['id']}"
                missao["jogo"] = slug
                missao["canal_config"] = f"jogo:{slug}"
                resultado.append(missao)
        return resultado

    async def _sincronizar_cartoes_missoes(self, guild: discord.Guild, atividades: list) -> dict:
        """Publica ou edita os cartões individuais, preservando referências existentes."""
        config = await get_config(guild.id)
        canais_por_tipo = {
            "missao": config.get("canal_missoes_missao_id") or CANAIS_PADRAO["canal_missoes_missao_id"],
            "contribuicao": config.get("canal_missoes_contribuicao_id") or CANAIS_PADRAO["canal_missoes_contribuicao_id"],
            "especial": config.get("canal_missoes_especial_id") or CANAIS_PADRAO["canal_missoes_especial_id"],
        }
        resultado = {"publicadas": 0, "atualizadas": 0, "falhas": 0}

        for atividade in atividades:
            missao_id = str(atividade.get("id") or "").strip()
            tipo = str(atividade.get("tipo") or "missao").strip().lower()
            canal_id = canais_por_tipo.get(tipo)
            if not missao_id or not canal_id:
                resultado["falhas"] += 1
                log.error("Missão sem ID ou canal de destino válido: %r", atividade)
                continue

            canal = await self._resolver_canal(guild, int(canal_id))
            if canal is None:
                resultado["falhas"] += 1
                log.error("Canal de publicação da missão %s não encontrado: %s", missao_id, canal_id)
                continue

            embeds = self._montar_embeds(atividade)
            registro = await obter_mensagem_discord(guild.id, missao_id)
            ids_antigos = registro.get("discord_message_ids") or []
            if not ids_antigos and registro.get("discord_message_id"):
                ids_antigos = [registro["discord_message_id"]]
            ids_antigos = [int(valor) for valor in ids_antigos if str(valor).isdigit()]
            canal_antigo_id = registro.get("discord_channel_id")

            try:
                # Se a categoria/canal mudou, cria e registra o novo cartão antes
                # de tentar remover o antigo, evitando perda da publicação.
                mesmo_canal = str(canal_antigo_id or "") == str(canal.id)
                mensagens = []
                if mesmo_canal:
                    for mensagem_id in ids_antigos:
                        try:
                            mensagens.append(await canal.fetch_message(mensagem_id))
                        except discord.NotFound:
                            continue
                    # Não compacta páginas faltantes: isso deslocaria embeds e
                    # poderia atualizar a missão errada. Recria o conjunto inteiro.
                    if len(mensagens) != len(ids_antigos):
                        mensagens = []

                ids_novos = []
                if mensagens:
                    for indice, embed in enumerate(embeds):
                        if indice < len(mensagens):
                            mensagem = mensagens[indice]
                            await mensagem.edit(embed=embed, view=EnviarProvaMissaoView(self) if indice == 0 else None)
                            ids_novos.append(mensagem.id)
                            resultado["atualizadas"] += 1
                        else:
                            mensagem = await canal.send(
                                embed=embed,
                                view=EnviarProvaMissaoView(self) if indice == 0 else None,
                            )
                            ids_novos.append(mensagem.id)
                            resultado["publicadas"] += 1
                    for mensagem_extra in mensagens[len(embeds):]:
                        try:
                            await mensagem_extra.delete(reason="Cartão de missão atualizado pela sincronização NÊMESIS")
                        except (discord.Forbidden, discord.HTTPException):
                            log.warning("Não foi possível remover página excedente da missão %s.", missao_id)
                else:
                    novas = []
                    for indice, embed in enumerate(embeds):
                        mensagem = await canal.send(
                            embed=embed,
                            view=EnviarProvaMissaoView(self) if indice == 0 else None,
                        )
                        novas.append(mensagem)
                        ids_novos.append(mensagem.id)
                        resultado["publicadas"] += 1

                await salvar_mensagem_discord(guild.id, missao_id, canal.id, ids_novos)

                if canal_antigo_id and ids_antigos:
                    canal_limpeza = canal if mesmo_canal else await self._resolver_canal(guild, int(canal_antigo_id))
                    if canal_limpeza is not None:
                        for mensagem_id in ids_antigos:
                            if mesmo_canal and mensagem_id in ids_novos:
                                continue
                            try:
                                antiga = await canal_limpeza.fetch_message(mensagem_id)
                                await antiga.delete(reason="Substituição do cartão pela sincronização oficial NÊMESIS")
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                log.warning("Não foi possível limpar cartão antigo da missão %s (%s).", missao_id, mensagem_id)

            except (discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                resultado["falhas"] += 1
                log.exception("Falha ao sincronizar cartão da missão %s.", missao_id)

        return resultado

    async def _limpar_cartoes_individuais_antigos(self, guild: discord.Guild, atividades: list) -> int:
        """Remove os cartões individuais antigos após a adoção do painel único."""
        removidas = 0
        registros_vistos = set()
        for atividade in atividades:
            missao_id = str(atividade.get("id") or "")
            if not missao_id or missao_id in registros_vistos:
                continue
            registros_vistos.add(missao_id)
            registro = await obter_mensagem_discord(guild.id, missao_id)
            canal_id = registro.get("discord_channel_id")
            ids = registro.get("discord_message_ids") or []
            if not ids and registro.get("discord_message_id"):
                ids = [registro["discord_message_id"]]
            if not canal_id or not ids:
                continue
            canal = await self._resolver_canal(guild, int(canal_id))
            if canal is None:
                continue
            for mensagem_id in ids:
                try:
                    mensagem = await canal.fetch_message(int(mensagem_id))
                    await mensagem.delete(reason="Migração para a central única de missões NÊMESIS")
                    removidas += 1
                except discord.NotFound:
                    continue
                except (discord.Forbidden, discord.HTTPException):
                    log.exception("Não foi possível remover o cartão antigo da missão %s.", missao_id)
        return removidas

    async def sincronizar_missoes_discord(self, guild: discord.Guild) -> dict:
        """Sincroniza o catálogo e mantém painéis navegáveis nos canais existentes."""
        if self._sync_lock.locked():
            return {"atualizadas": 0, "publicadas": 0, "falhas": 0, "ignorada": True}
        async with self._sync_lock:
            catalogo = self._expandir_catalogo_por_jogo(carregar_catalogo())
            atividades = await sincronizar_catalogo(guild.id, catalogo)
            resultado = {"publicadas": 0, "atualizadas": 0, "falhas": 0,
                         "registros_catalogo": len(atividades), "painel_atualizado": False}
            try:
                await self._atualizar_painel_missoes(guild)
                resultado["painel_atualizado"] = True
                resultado["atualizadas"] = 1
                resultado["mensagens_duplicadas_removidas"] = await self._limpar_mensagens_missoes_duplicadas(guild)
                resultado["cartoes_antigos_removidos"] = await self._limpar_cartoes_individuais_antigos(guild, atividades)
            except Exception:
                resultado["falhas"] += 1
                log.exception("Falha ao atualizar o painel único ou limpar mensagens antigas de missões.")
            try:
                await self._atualizar_ranking_jogo(guild, "shigaku")
            except Exception:
                resultado["falhas"] += 1
                log.exception("Falha ao atualizar o ranking de missões.")
            log.info(
                "Central única sincronizada: %s missões no catálogo; painel atualizado=%s; falhas=%s.",
                resultado["registros_catalogo"], resultado["painel_atualizado"], resultado["falhas"],
            )
            return resultado
    @app_commands.command(
        name="missoes-sincronizar",
        description="Publica ou atualiza as missões padrão nos canais oficiais.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def missoes_sincronizar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild is None:
            await interaction.followup.send("Use este comando dentro do servidor.", ephemeral=True)
            return
        try:
            resultado = await self.sincronizar_missoes_discord(interaction.guild)
        except Exception as erro:
            log.exception("Erro na sincronização manual das missões.")
            await interaction.followup.send(f"Falha ao sincronizar as missões: `{type(erro).__name__}`.", ephemeral=True)
            return
        await interaction.followup.send(
            "Sincronização concluída. "
            f"Publicadas: **{resultado.get('publicadas', 0)}** · "
            f"Atualizadas: **{resultado.get('atualizadas', 0)}** · "
            f"Falhas: **{resultado.get('falhas', 0)}** · "
            f"Registros do catálogo: **{resultado.get('registros_catalogo', resultado.get('atualizadas', 0))}** · "
            f"Painel geral: **{'atualizado' if resultado.get('painel_atualizado') else 'não confirmado'}**.",
            ephemeral=True,
        )

    async def processar_aprovacao(self, guild: discord.Guild, revisao: dict) -> str:
        atividade = await missoes.get(guild.id, revisao.get("referencia_id", ""))
        if not atividade:
            return "⚠️ A atividade original não foi encontrada; nenhuma recompensa foi aplicada."

        revisao_id = str(revisao.get("id", "")).strip()
        if not revisao_id:
            return "⚠️ Esta revisão não possui um identificador válido; nenhuma recompensa foi aplicada."

        autor_id = int(revisao.get("autor_id", 0) or 0)
        if not autor_id:
            return "⚠️ Não foi possível identificar o participante."

        try:
            auxiliar_id = int(revisao.get("auxiliar_id") or 0)
        except (TypeError, ValueError):
            auxiliar_id = 0
        if auxiliar_id == autor_id:
            auxiliar_id = 0

        try:
            recompensa = max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
        except (TypeError, ValueError):
            recompensa = 0

        # Sem auxiliar, mantém compatibilidade com o marcador histórico da revisão.
        # Com auxiliar, cada participante recebe um evento próprio e recuperável.
        atividade_ja_aplicada = revisao_id in atividade.get("recompensas_aplicadas", [])
        if auxiliar_id:
            distribuicao = [
                (autor_id, ((recompensa * 60 + 50) // 100)),
                (auxiliar_id, recompensa - ((recompensa * 60 + 50) // 100)),
            ]
        else:
            distribuicao = [(autor_id, recompensa)]

        resultados = []
        async with self._reward_lock:
            for usuario_id, quantidade in distribuicao:
                perfil = await get_perfil(guild.id, usuario_id)
                eventos_aplicados = list(perfil.get("recompensas_missoes_aplicadas", []))
                evento_perfil = (
                    f"{revisao_id}:{usuario_id}"
                    if auxiliar_id
                    else revisao_id
                )
                marcador_novo = evento_perfil not in eventos_aplicados
                recompensa_aplicada = (
                    marcador_novo
                    and (bool(auxiliar_id) or not atividade_ja_aplicada)
                )

                if marcador_novo:
                    eventos_aplicados.append(evento_perfil)
                    perfil["recompensas_missoes_aplicadas"] = eventos_aplicados[-1000:]
                if recompensa_aplicada:
                    perfil["xp"] = int(perfil.get("xp", 0) or 0) + quantidade
                if recompensa_aplicada or marcador_novo:
                    await _salvar_perfil(guild.id, usuario_id, perfil)

                resultados.append({
                    "user_id": usuario_id,
                    "quantidade": quantidade,
                    "perfil": perfil,
                    "aplicada": bool(recompensa_aplicada),
                    "evento_perfil": evento_perfil,
                })

        # Registra XP na progressão interna com chave idempotente por membro.
        progressao = self.bot.get_cog("ProgressaoGangue")
        tipo_progressao = str(atividade.get("tipo", "missao")).lower()
        if tipo_progressao not in {"missao", "contribuicao", "especial"}:
            tipo_progressao = "missao"

        for resultado in resultados:
            usuario_id = resultado["user_id"]
            quantidade = resultado["quantidade"]
            evento_id = (
                f"missao:{revisao_id}:{usuario_id}"
                if auxiliar_id
                else f"missao:{revisao_id}"
            )

            jogo_slug = str(atividade.get("jogo") or "").strip().lower()
            if jogo_slug and resultado["aplicada"] and quantidade > 0:
                membro_ranking = guild.get_member(usuario_id)
                try:
                    await ranking_missoes_jogos.registrar_pontos(
                        guild_id=guild.id,
                        jogo=jogo_slug,
                        user_id=usuario_id,
                        nome=membro_ranking.display_name if membro_ranking else "",
                        pontos=quantidade,
                        evento_id=f"missao:{revisao_id}:{usuario_id}",
                    )
                    await self._atualizar_ranking_jogo(guild, jogo_slug)
                except Exception as erro:
                    log.exception(
                        "Falha ao atualizar ranking de %s para %s: %s",
                        jogo_slug,
                        usuario_id,
                        erro,
                    )

            if progressao is not None and quantidade > 0:
                try:
                    await progressao.registrar_recompensa(
                        guild=guild,
                        user_id=usuario_id,
                        quantidade=quantidade,
                        tipo=tipo_progressao,
                        evento_id=evento_id,
                    )
                except Exception as erro:
                    log.exception(
                        "Falha ao registrar recompensa da missão para %s: %s",
                        usuario_id,
                        erro,
                    )


        dados_guild = await missoes._guild(guild.id)
        alvo = next(
            (
                item for item in dados_guild.get("missoes", [])
                if str(item.get("id")) == str(atividade.get("id"))
            ),
            None,
        )
        if alvo is not None:
            aplicadas = alvo.setdefault("recompensas_aplicadas", [])
            if revisao_id not in aplicadas:
                aplicadas.append(revisao_id)
            await missoes._salvar_guild(guild.id, dados_guild)

        mensagens = []
        for resultado in resultados:
            usuario_id = resultado["user_id"]
            quantidade = resultado["quantidade"]
            perfil = resultado["perfil"]
            membro = guild.get_member(usuario_id)

            if resultado["aplicada"]:
                mensagens.append(
                    f"<@{usuario_id}> recebeu **+{quantidade} XP**"
                )
            else:
                mensagens.append(
                    f"<@{usuario_id}> já tinha a recompensa registrada; nenhum crédito duplicado foi adicionado"
                )

            nova_patente = await calcular_patente_atual(guild.id, perfil["xp"])
            if nova_patente and nova_patente.get("nome") != perfil.get("patente"):
                await definir_patente(guild.id, usuario_id, nova_patente["nome"])
                cargo_id = nova_patente.get("cargo_id")
                cargo = guild.get_role(int(cargo_id)) if cargo_id else None
                if membro and cargo:
                    try:
                        await membro.add_roles(
                            cargo,
                            reason="Promoção automática por conclusão de missão",
                        )
                    except discord.Forbidden:
                        pass
                mensagens[-1] += f" • Nova patente: **{nova_patente['nome']}**"

        if auxiliar_id:
            cabecalho = (
                f"✅ Recompensa dividida: **{((recompensa * 60 + 50) // 100)} XP** para o responsável "
                f"e **{recompensa - ((recompensa * 60 + 50) // 100)} XP** para o auxiliar.\n"
            )
        else:
            cabecalho = "✅ Recompensa da missão aprovada.\n"
        return cabecalho + "\n".join(mensagens)

    @app_commands.command(
        name="missao-enviar-prova",
        description="Envie a prova de uma missão com anexo, sem copiar links ou IDs."
    )
    @app_commands.describe(
        missao_id="Escolha a missão pelo nome ou código",
        prova="Anexe a imagem da prova diretamente aqui",
        auxiliar="Selecione o auxiliar (opcional)"
    )
    async def missao_enviar_prova(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        prova: discord.Attachment,
        auxiliar: discord.Member = None,
    ):
        """Recebe a imagem como anexo e seleciona missão/auxiliar pelo Discord."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        if not (prova.content_type or "").lower().startswith("image/"):
            await interaction.response.send_message(
                "O arquivo precisa ser uma imagem. Anexe PNG, JPG, JPEG, WEBP ou outro formato de imagem.",
                ephemeral=True,
            )
            return

        if prova.size > 10 * 1024 * 1024:
            await interaction.response.send_message(
                "A imagem ultrapassa o limite de 10 MB. Envie uma versão menor.",
                ephemeral=True,
            )
            return

        # O seletor de usuário nativo elimina a necessidade de copiar IDs.
        auxiliar_texto = str(auxiliar.id) if auxiliar else ""
        await self.receber_prova_modal(
            interaction,
            str(missao_id),
            str(prova.url),
            auxiliar_texto,
        )

    @missao_enviar_prova.autocomplete("missao_id")
    async def autocomplete_missao_id(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Sugere missões ativas por título e código para evitar digitação de IDs."""
        if interaction.guild is None:
            return []
        try:
            dados = await missoes._guild(interaction.guild.id)
            atividades = [
                item for item in dados.get("missoes", [])
                if isinstance(item, dict) and item.get("ativa", True) is not False
            ]
            termo = current.casefold().strip()
            atividades = [
                item for item in atividades
                if termo in str(item.get("id", "")).casefold()
                or termo in str(item.get("titulo", "")).casefold()
            ]
            atividades.sort(key=lambda item: (
                str(item.get("jogo", "")).casefold(),
                str(item.get("titulo", "")).casefold(),
            ))
            escolhas = []
            for item in atividades[:25]:
                codigo = str(item.get("id", "")).strip()
                titulo = str(item.get("titulo", "Missão")).strip()
                if not codigo:
                    continue
                label = f"{titulo} — {codigo}"[:100]
                escolhas.append(app_commands.Choice(name=label, value=codigo[:100]))
            return escolhas
        except Exception:
            log.exception("Falha ao carregar sugestões de missões para autocomplete.")
            return []

    async def receber_prova_modal(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        imagem_url: str,
        auxiliar_texto: str = "",
    ):
        """Valida a missão, o auxiliar opcional e encaminha a prova para revisão."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Use este botão dentro do servidor da NÊMESIS.", ephemeral=True)
            return

        auxiliar_id = None
        auxiliar_valor = auxiliar_texto.strip()
        if auxiliar_valor:
            mencao = re.fullmatch(r"<@!?(\d+)>", auxiliar_valor)
            id_direto = re.fullmatch(r"\d{15,22}", auxiliar_valor)
            if mencao:
                auxiliar_id = int(mencao.group(1))
            elif id_direto:
                auxiliar_id = int(auxiliar_valor)
            else:
                await interaction.followup.send(
                    "❌ Auxiliar inválido. Informe uma menção como @membro ou o ID numérico do Discord.",
                    ephemeral=True,
                )
                return

            if auxiliar_id == interaction.user.id:
                await interaction.followup.send(
                    "❌ Você não pode selecionar a si mesmo como auxiliar.",
                    ephemeral=True,
                )
                return

            try:
                auxiliar = await guild.fetch_member(auxiliar_id)
            except discord.NotFound:
                await interaction.followup.send(
                    "❌ Esse auxiliar não é membro deste servidor.",
                    ephemeral=True,
                )
                return
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Não foi possível validar o auxiliar %s no servidor %s.", auxiliar_id, guild.id)
                await interaction.followup.send(
                    "❌ Não consegui validar o auxiliar agora. Tente novamente em instantes.",
                    ephemeral=True,
                )
                return

            if auxiliar.bot:
                await interaction.followup.send(
                    "❌ O auxiliar precisa ser uma pessoa, não um bot.",
                    ephemeral=True,
                )
                return

        atividade = await missoes.get(guild.id, missao_id.strip())
        if not atividade or not atividade.get("ativa", True):
            await interaction.followup.send(
                "❌ Não encontrei uma missão ativa com esse ID. Confira o ID na publicação da missão.",
                ephemeral=True,
            )
            return

        tipo = str(atividade.get("tipo", "missao")).lower()
        if tipo not in TIPOS:
            await interaction.followup.send(
                "❌ O tipo desta atividade está inválido. Avise a staff.",
                ephemeral=True,
            )
            return

        url = imagem_url.strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or host not in {"cdn.discordapp.com", "media.discordapp.net"}
            or not parsed.path
        ):
            await interaction.followup.send(
                "❌ O link precisa ser de uma imagem hospedada no Discord. Envie a imagem em um canal permitido, abra a imagem, copie o link e cole aqui.",
                ephemeral=True,
            )
            return

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.followup.send(
                "❌ O sistema de revisão não está carregado. Avise a staff.",
                ephemeral=True,
            )
            return

        from utils import revisoes

        pendentes = await revisoes.listar(guild.id, status="pendente")
        ja_enviada = any(
            int(item.get("autor_id", 0) or 0) == interaction.user.id
            and str(item.get("referencia_id", "")) == str(atividade["id"])
            and item.get("tipo") == tipo
            for item in pendentes
        )
        if ja_enviada:
            await interaction.followup.send(
                "⏳ Você já tem uma prova pendente para esta missão. Aguarde a análise da staff antes de enviar outra.",
                ephemeral=True,
            )
            return

        info = TIPOS[tipo]
        recompensa = max(
            0,
            int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0),
        )
        if auxiliar_id and recompensa < 2:
            await interaction.followup.send(
                "❌ Esta missão oferece menos de 2 XP; não é possível dividir a recompensa entre duas pessoas.",
                ephemeral=True,
            )
            return

        canal_config = await get_config(guild.id)
        chave_prova = {
            "missao": "canal_provas_missao_id",
            "contribuicao": "canal_provas_contribuicao_id",
            "especial": "canal_provas_especial_id",
        }[tipo]
        canal_id = canal_config.get(chave_prova) or CANAIS_PADRAO.get(chave_prova)
        canal = await self._resolver_canal(guild, canal_id) if canal_id else None
        if canal is None:
            await interaction.followup.send(
                "❌ O canal de provas deste tipo não foi encontrado. Avise a staff.",
                ephemeral=True,
            )
            return

        try:
            await revisoes_cog.abrir_revisao(
                guild,
                canal,
                tipo=tipo,
                autor_id=interaction.user.id,
                referencia_id=str(atividade["id"]),
                print_url=url,
                titulo=f"{info['emoji']} {info['nome']} — {atividade.get('titulo', 'Atividade')}",
                descricao=(
                    f"Prova enviada por {interaction.user.mention}. "
                    f"ID da missão: `{atividade['id']}`. "
                    + (
                        f"Recompensa total: {recompensa} XP, dividida em 60% para o responsável e 40% para o auxiliar "
                        f"<@{auxiliar_id}> após aprovação."
                        if auxiliar_id
                        else f"Recompensa após aprovação: +{recompensa} XP."
                    )
                ),
                auxiliar_id=auxiliar_id,
            )
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao criar revisão da missão %s.", atividade.get("id"))
            await interaction.followup.send(
                "❌ Não consegui publicar a prova para revisão. Verifique se o bot tem permissão para enviar mensagens e Embeds no canal de provas.",
                ephemeral=True,
            )
            return
        except Exception:
            log.exception("Erro inesperado ao receber prova da missão %s.", atividade.get("id"))
            await interaction.followup.send(
                "❌ Ocorreu um erro ao enviar sua prova. Tente novamente mais tarde.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Prova enviada para {canal.mention}. A recompensa será aplicada somente após a aprovação da staff.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Missoes(bot))
