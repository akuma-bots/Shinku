import asyncio
import datetime
import re
import time
from collections import defaultdict, deque
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.auditoria import registrar
from utils.punicoes import historico_punicoes, registrar_punicao
from utils.storage import carregar, salvar


# ============================================================
# CONFIGURAÇÃO
# ============================================================

CANAL_REGRAS_ID = 1545831172796583987

CACHE_REGRAS_SEGUNDOS = 60

ARQUIVO_BANIMENTOS_TEMPORARIOS = (
    "automod_banimentos.json"
)

JANELA_SPAM = 8
LIMITE_SPAM = 6

JANELA_REPETICAO = 20
LIMITE_REPETICAO = 3

LIMITE_MENCOES = 5

COOLDOWN_PUNICAO = 20

JANELA_REINCIDENCIA = (
    30 * 24 * 60 * 60
)


# ============================================================
# NÍVEIS DE INFRAÇÃO
# ============================================================

NIVEIS = {
    1: {
        "nome": "NORMAL",
        "punicao": "Advertência",
    },
    2: {
        "nome": "MÉDIO",
        "punicao": "Silenciamento",
    },
    3: {
        "nome": "GRAVE",
        "punicao": "Expulsão",
    },
    4: {
        "nome": "MUITO GRAVE",
        "punicao": "Banimento temporário",
    },
    5: {
        "nome": "CRÍTICO",
        "punicao": "Banimento permanente",
    },
}


# ============================================================
# CATEGORIAS
# ============================================================

CATEGORIA_COMUNICACAO = "COMUNICACAO"
CATEGORIA_DIVULGACAO = "DIVULGACAO"
CATEGORIA_CONTEUDO = "CONTEUDO"
CATEGORIA_SEGURANCA = "SEGURANCA"
CATEGORIA_JOGOS = "JOGOS"


# ============================================================
# PADRÕES DE DETECÇÃO
# ============================================================

URL_REGEX = re.compile(
    r"https?://[^\s<>]+",
    re.IGNORECASE,
)

DISCORD_INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:discord\.gg|discord\.com/invite|discordapp\.com/invite)/"
    r"[A-Za-z0-9-]+",
    re.IGNORECASE,
)


PHISHING_PATTERNS = [
    re.compile(r"nitro\s+gratis", re.I),
    re.compile(r"discord\s+nitro\s+gratis", re.I),
    re.compile(r"clique\s+aqui\s+para\s+ganhar", re.I),
    re.compile(r"resgate\s+seu\s+nitro", re.I),
    re.compile(r"gift\s+nitro", re.I),
    re.compile(r"free\s+nitro", re.I),
    re.compile(r"steam\s+gift\s+free", re.I),
    re.compile(r"robux\s+gratis", re.I),
    re.compile(r"robux\s+free", re.I),
    re.compile(r"verifique\s+sua\s+conta", re.I),
    re.compile(r"confirme\s+sua\s+conta", re.I),
    re.compile(r"login\s+para\s+receber", re.I),
]


MALWARE_PATTERNS = [
    re.compile(r"\bstealer\b", re.I),
    re.compile(r"\brat\b", re.I),
    re.compile(r"keylogger", re.I),
    re.compile(r"roubar\s+token", re.I),
    re.compile(r"token\s+logger", re.I),
    re.compile(r"token\s+grabber", re.I),
    re.compile(r"roubar\s+conta", re.I),
    re.compile(r"invas[aã]o\s+de\s+conta", re.I),
    re.compile(r"hackear\s+conta", re.I),
]


DOXXING_PATTERNS = [
    re.compile(r"doxx", re.I),
    re.compile(r"doxing", re.I),
    re.compile(r"expor\s+o\s+endereço", re.I),
    re.compile(r"expor\s+endereco", re.I),
    re.compile(r"expor\s+dados\s+pessoais", re.I),
    re.compile(r"vazar\s+dados", re.I),
    re.compile(r"vazar\s+informações", re.I),
    re.compile(r"vazar\s+informacoes", re.I),
]


INVASION_PATTERNS = [
    re.compile(r"invadir\s+o\s+servidor", re.I),
    re.compile(r"derrubar\s+o\s+servidor", re.I),
    re.compile(r"raidar\s+o\s+servidor", re.I),
    re.compile(r"raidear\s+o\s+servidor", re.I),
    re.compile(r"destruir\s+o\s+servidor", re.I),
    re.compile(r"atacar\s+o\s+servidor", re.I),
]


THREAT_PATTERNS = [
    re.compile(r"vou\s+te\s+matar", re.I),
    re.compile(r"vou\s+matar\s+voc[eê]", re.I),
    re.compile(r"vou\s+te\s+machucar", re.I),
    re.compile(r"vou\s+atr[aá]s\s+de\s+voc[eê]", re.I),
    re.compile(r"vou\s+acabar\s+com\s+voc[eê]", re.I),
]


HARASSMENT_PATTERNS = [
    re.compile(r"vai\s+se\s+foder", re.I),
    re.compile(r"vai\s+tomar\s+no\s+cu", re.I),
    re.compile(r"seu\s+in[uú]til", re.I),
    re.compile(r"seu\s+lixo", re.I),
]


CHEAT_PATTERNS = [
    re.compile(r"\bexploit\b", re.I),
    re.compile(r"\bcheat\b", re.I),
    re.compile(r"\bhack\b", re.I),
    re.compile(r"\bscript\s+de\s+hack", re.I),
    re.compile(r"\bexecutor\b", re.I),
]


CONTEXTUAL_TERMS = [
    "ameaça",
    "ameaca",
    "matar",
    "doxx",
    "doxxing",
    "hack",
    "invadir",
    "exploit",
    "cheat",
    "malware",
    "porn",
    "nude",
]


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_texto(texto: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        texto,
    ).strip()


def porcentagem_maiusculas(texto: str) -> float:
    letras = [
        c
        for c in texto
        if c.isalpha()
    ]

    if not letras:
        return 0.0

    maiusculas = sum(
        1
        for c in letras
        if c.isupper()
    )

    return maiusculas / len(letras)


def contem_padrao(
    texto: str,
    padroes: list[re.Pattern],
) -> bool:
    return any(
        padrao.search(texto)
        for padrao in padroes
    )


def possui_url(texto: str) -> bool:
    return bool(
        URL_REGEX.search(texto)
    )


def possui_convite_discord(
    texto: str,
) -> bool:
    return bool(
        DISCORD_INVITE_REGEX.search(texto)
    )


# ============================================================
# COG
# ============================================================

class AutoMod(commands.Cog):

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

        self.historico_mensagens = defaultdict(
            lambda: defaultdict(
                lambda: deque(maxlen=20)
            )
        )

        self.ultimas_mensagens = defaultdict(
            lambda: defaultdict(
                lambda: deque(maxlen=10)
            )
        )

        self.cooldowns = {}

        self.regras_cache = {}

        self.regras_cache_timestamp = {}

        self.punicoes_em_andamento = set()

        self.verificar_banimentos.start()

    def cog_unload(self):
        self.verificar_banimentos.cancel()

    # ========================================================
    # LEITURA DAS REGRAS OFICIAIS
    # ========================================================

    async def carregar_regras_oficiais(
        self,
        guild: discord.Guild,
        forcar: bool = False,
    ) -> dict:

        agora = time.time()

        if (
            not forcar
            and guild.id in self.regras_cache
            and (
                agora
                - self.regras_cache_timestamp.get(
                    guild.id,
                    0,
                )
            )
            < CACHE_REGRAS_SEGUNDOS
        ):
            return self.regras_cache[guild.id]

        canal = guild.get_channel(
            CANAL_REGRAS_ID
        )

        if canal is None:
            try:
                canal = await self.bot.fetch_channel(
                    CANAL_REGRAS_ID
                )
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                return {}

        if not isinstance(
            canal,
            discord.TextChannel,
        ):
            return {}

        mensagens = []

        try:
            async for mensagem in canal.history(
                limit=200,
                oldest_first=True,
            ):
                if mensagem.content:
                    mensagens.append(
                        mensagem.content
                    )

        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            return {}

        texto_completo = "\n".join(
            mensagens
        )

        secoes = {}

        padrao_secao = re.compile(
            r"(?:^|\n)\s*(?:┃\s*)?"
            r"(\d{2})\.\s*([^\n]+)",
            re.IGNORECASE,
        )

        encontrados = list(
            padrao_secao.finditer(
                texto_completo
            )
        )

        for i, match in enumerate(
            encontrados
        ):
            numero = match.group(1)
            titulo = match.group(2).strip()

            inicio = match.end()

            if i + 1 < len(encontrados):
                fim = encontrados[
                    i + 1
                ].start()
            else:
                fim = len(
                    texto_completo
                )

            conteudo = (
                texto_completo[
                    inicio:fim
                ].strip()
            )

            secoes[numero] = {
                "numero": numero,
                "titulo": titulo,
                "conteudo": conteudo,
            }

        regras = {
            "canal_id": CANAL_REGRAS_ID,
            "texto": texto_completo,
            "secoes": secoes,
            "atualizado_em": agora,
        }

        self.regras_cache[
            guild.id
        ] = regras

        self.regras_cache_timestamp[
            guild.id
        ] = agora

        return regras

    def regra_existe(
        self,
        regras: dict,
        numero: str,
    ) -> bool:
        return numero in regras.get(
            "secoes",
            {},
        )
    # ============================================================
    # DETECÇÕES BÁSICAS
    # ============================================================

    def detectar_spam(self, guild_id, membro_id):
        chave = (guild_id, membro_id)
        fila = self.historico_mensagens.get(chave)

        if not fila:
            return False

        agora = time.time()

        mensagens_recentes = [
            timestamp
            for timestamp in fila
            if agora - timestamp <= JANELA_SPAM
        ]

        return len(mensagens_recentes) >= LIMITE_SPAM

    def detectar_repeticao(self, guild_id, membro_id, texto):
        chave = (guild_id, membro_id)
        mensagens = self.ultimas_mensagens.get(chave)

        if not mensagens:
            return False

        texto_normalizado = normalizar_texto(texto)

        quantidade = sum(
            1
            for mensagem in mensagens
            if normalizar_texto(mensagem) == texto_normalizado
        )

        return quantidade >= LIMITE_REPETICAO

    def detectar_caps_spam(self, texto):
        if len(texto) < 12:
            return False

        percentual = porcentagem_maiusculas(texto)

        return percentual >= 0.85

    def detectar_mencao_massa(self, message):
        quantidade = (
            len(message.mentions)
            + len(message.role_mentions)
        )

        if message.mention_everyone:
            return True

        return quantidade >= LIMITE_MENCOES

    # ============================================================
    # DETECÇÕES DE DIVULGAÇÃO
    # ============================================================

    def detectar_divulgacao(self, texto):
        if not possui_url(texto):
            return False

        return possui_convite_discord(texto)

    # ============================================================
    # DETECÇÕES DE SEGURANÇA
    # ============================================================

    def detectar_phishing(self, texto):
        return contem_padrao(
            texto,
            PADROES_PHISHING
        )

    def detectar_malware(self, texto):
        return contem_padrao(
            texto,
            PADROES_MALWARE
        )

    def detectar_doxxing(self, texto):
        return contem_padrao(
            texto,
            PADROES_DOXXING
        )

    def detectar_invasao(self, texto):
        return contem_padrao(
            texto,
            PADROES_INVASAO
        )

    # ============================================================
    # DETECÇÕES DE CONDUTA
    # ============================================================

    def detectar_ameaca(self, texto):
        return contem_padrao(
            texto,
            PADROES_AMENCA
        )

    def detectar_assedio(self, texto):
        return contem_padrao(
            texto,
            PADROES_ASSEDIO
        )

    # ============================================================
    # DETECÇÕES RELACIONADAS A JOGOS
    # ============================================================

    def detectar_exploit(self, texto):
        return contem_padrao(
            texto,
            PADROES_EXPLOIT
        )

    # ============================================================
    # ANÁLISE DA INFRAÇÃO
    # ============================================================

    async def analisar_infracao(self, message):
        """
        Analisa a mensagem e retorna:

        {
            "nivel": int,
            "categoria": str,
            "motivo": str,
            "confianca": str
        }

        Nivel 0 = revisão manual.
        """

        texto = message.content.strip()

        if not texto:
            return None

        guild_id = message.guild.id
        membro_id = message.author.id

        # --------------------------------------------------------
        # NÍVEL 5 — CRÍTICO
        # --------------------------------------------------------

        if (
            self.detectar_invasao(texto)
            and possui_url(texto)
        ):
            return {
                "nivel": 5,
                "categoria": CATEGORIA_SEGURANCA,
                "motivo": (
                    "Tentativa identificada de comprometimento "
                    "ou invasão associada a conteúdo externo."
                ),
                "confianca": "alta"
            }

        # --------------------------------------------------------
        # NÍVEL 4 — MUITO GRAVE
        # --------------------------------------------------------

        if self.detectar_phishing(texto):
            return {
                "nivel": 4,
                "categoria": CATEGORIA_SEGURANCA,
                "motivo": (
                    "Possível tentativa de phishing ou obtenção "
                    "fraudulenta de informações."
                ),
                "confianca": "alta"
            }

        if self.detectar_malware(texto):
            return {
                "nivel": 4,
                "categoria": CATEGORIA_SEGURANCA,
                "motivo": (
                    "Possível distribuição ou divulgação de "
                    "conteúdo malicioso."
                ),
                "confianca": "alta"
            }

        if self.detectar_doxxing(texto):
            return {
                "nivel": 4,
                "categoria": CATEGORIA_SEGURANCA,
                "motivo": (
                    "Possível exposição ou divulgação de "
                    "informações pessoais."
                ),
                "confianca": "alta"
            }

        # --------------------------------------------------------
        # NÍVEL 3 — GRAVE
        # --------------------------------------------------------

        if self.detectar_ameaca(texto):
            return {
                "nivel": 3,
                "categoria": CATEGORIA_COMUNICACAO,
                "motivo": (
                    "Ameaça identificada em contexto de "
                    "hostilidade ou intimidação."
                ),
                "confianca": "alta"
            }

        if self.detectar_assedio(texto):
            return {
                "nivel": 3,
                "categoria": CATEGORIA_CONDUTA,
                "motivo": (
                    "Comportamento de assédio ou perseguição "
                    "identificado."
                ),
                "confianca": "alta"
            }

        # --------------------------------------------------------
        # NÍVEL 2 — MÉDIO
        # --------------------------------------------------------

        if self.detectar_divulgacao(texto):
            return {
                "nivel": 2,
                "categoria": CATEGORIA_DIVULGACAO,
                "motivo": (
                    "Divulgação externa não autorizada "
                    "identificada."
                ),
                "confianca": "alta"
            }

        if self.detectar_exploit(texto):
            return {
                "nivel": 2,
                "categoria": CATEGORIA_JOGOS,
                "motivo": (
                    "Divulgação ou incentivo ao uso de "
                    "exploit, cheat ou vantagem indevida."
                ),
                "confianca": "alta"
            }

        # --------------------------------------------------------
        # NÍVEL 1 — NORMAL
        # --------------------------------------------------------

        if self.detectar_mencao_massa(message):
            return {
                "nivel": 1,
                "categoria": CATEGORIA_COMUNICACAO,
                "motivo": (
                    "Uso excessivo de menções ou notificações."
                ),
                "confianca": "alta"
            }

        if self.detectar_spam(guild_id, membro_id):
            return {
                "nivel": 1,
                "categoria": CATEGORIA_COMUNICACAO,
                "motivo": (
                    "Envio excessivo de mensagens em curto "
                    "período de tempo."
                ),
                "confianca": "alta"
            }

        if self.detectar_repeticao(
            guild_id,
            membro_id,
            texto
        ):
            return {
                "nivel": 1,
                "categoria": CATEGORIA_COMUNICACAO,
                "motivo": (
                    "Repetição excessiva da mesma mensagem."
                ),
                "confianca": "alta"
            }

        if self.detectar_caps_spam(texto):
            return {
                "nivel": 1,
                "categoria": CATEGORIA_COMUNICACAO,
                "motivo": (
                    "Uso excessivo de letras maiúsculas."
                ),
                "confianca": "alta"
            }

        # --------------------------------------------------------
        # REVISÃO MANUAL
        # --------------------------------------------------------

        texto_normalizado = normalizar_texto(texto)

        termos_contextuais = [
            "mata",
            "matar",
            "vou atrás",
            "vai morrer",
            "vou te pegar",
            "hackear",
            "hack",
            "invadir",
            "expor",
            "vazar",
            "denunciar",
            "ameaçar",
        ]

        encontrou_contexto = any(
            termo in texto_normalizado
            for termo in termos_contextuais
        )

        if encontrou_contexto:
            return {
                "nivel": 0,
                "categoria": CATEGORIA_COMUNICACAO,
                "motivo": (
                    "Mensagem contém linguagem que pode exigir "
                    "avaliação contextual da Staff."
                ),
                "confianca": "baixa"
            }

        return None

    # ============================================================
    # REINCIDÊNCIA
    # ============================================================

    def calcular_nivel_reincidencia(
        self,
        guild_id,
        membro_id,
        categoria,
        nivel_atual
    ):
        """
        A reincidência aumenta o nível gradualmente.

        Exemplo:

        Normal
          ↓
        Médio
          ↓
        Grave
          ↓
        Muito grave
          ↓
        Crítico
        """

        try:
            historico = historico_punicoes(
                guild_id,
                membro_id
            )
        except Exception:
            historico = []

        agora = time.time()

        reincidencias = 0

        for registro in historico:
            try:
                timestamp = float(
                    registro.get(
                        "timestamp",
                        0
                    )
                )
            except (TypeError, ValueError):
                continue

            if agora - timestamp > JANELA_REINCIDENCIA:
                continue

            motivo = str(
                registro.get(
                    "motivo",
                    ""
                )
            ).lower()

            if f"categoria={categoria.lower()}" in motivo:
                reincidencias += 1

        novo_nivel = min(
            5,
            nivel_atual + reincidencias
        )

        return novo_nivel

    # ============================================================
    # COOLDOWN
    # ============================================================

    def em_cooldown(
        self,
        guild_id,
        membro_id
    ):
        chave = (
            guild_id,
            membro_id
        )

        ultimo = self.cooldowns.get(chave)

        if ultimo is None:
            return False

        return (
            time.time() - ultimo
            < COOLDOWN_PUNICAO
        )

    def registrar_cooldown(
        self,
        guild_id,
        membro_id
    ):
        self.cooldowns[
            (guild_id, membro_id)
        ] = time.time()

    # ============================================================
    # REGISTRO DE BANIMENTOS TEMPORÁRIOS
    # ============================================================

    def carregar_banimentos_temporarios(self):
        try:
            dados = carregar(
                ARQUIVO_BANIMENTOS_TEMPORARIOS,
                {}
            )

            if isinstance(dados, dict):
                return dados

        except Exception:
            pass

        return {}

    def salvar_banimentos_temporarios(
        self,
        dados
    ):
        salvar(
            ARQUIVO_BANIMENTOS_TEMPORARIOS,
            dados
        )

    def registrar_banimento_temporario(
        self,
        guild_id,
        membro_id,
        duracao
    ):
        dados = (
            self.carregar_banimentos_temporarios()
        )

        chave = f"{guild_id}:{membro_id}"

        dados[chave] = {
            "guild_id": guild_id,
            "membro_id": membro_id,
            "expira_em": (
                time.time() + duracao
            )
        }

        self.salvar_banimentos_temporarios(
            dados
        )

    # ============================================================
    # LOG DA INFRAÇÃO
    # ============================================================

    async def registrar_log_infracao(
        self,
        message,
        resultado,
        nivel_final
    ):
        try:
            guild = message.guild

            titulo = (
                f"AutoMod — Nível "
                f"{nivel_final}"
            )

            descricao = (
                f"**Usuário:** {message.author.mention}\n"
                f"**ID:** `{message.author.id}`\n"
                f"**Canal:** {message.channel.mention}\n"
                f"**Categoria:** "
                f"`{resultado['categoria']}`\n"
                f"**Motivo:** "
                f"{resultado['motivo']}\n"
                f"**Confiança:** "
                f"`{resultado['confianca']}`"
            )

            await registrar(
                guild,
                titulo,
                descricao
            )

        except Exception:
            pass

    # ============================================================
    # APLICAÇÃO DA PUNIÇÃO
    # ============================================================

    async def aplicar_punicao(
        self,
        message,
        resultado
    ):
        guild = message.guild
        membro = message.author

        nivel_original = resultado["nivel"]

        nivel = self.calcular_nivel_reincidencia(
            guild.id,
            membro.id,
            resultado["categoria"],
            nivel_original
        )

        if nivel <= 0:
            return False

        if self.em_cooldown(
            guild.id,
            membro.id
        ):
            return False

        self.registrar_cooldown(
            guild.id,
            membro.id
        )

        # ========================================================
        # VERIFICAÇÃO DO BOT
        # ========================================================

        eu = guild.me

        if eu is None:
            return False

        if membro.id == eu.id:
            return False

        if membro == guild.owner:
            return False

        if (
            membro.top_role >= eu.top_role
            and nivel >= 2
        ):
            return False

        # ========================================================
        # NÍVEL 1 — ADVERTÊNCIA
        # ========================================================

        if nivel == 1:
            try:
                await membro.send(
                    f"⚠️ **Advertência — {guild.name}**\n\n"
                    f"Uma infração foi identificada "
                    f"automaticamente.\n\n"
                    f"**Motivo:** "
                    f"{resultado['motivo']}\n\n"
                    f"Evite reincidência."
                )
            except Exception:
                pass

            registrar_punicao(
                guild.id,
                membro.id,
                "aviso_automatico",
                (
                    f"categoria="
                    f"{resultado['categoria']} | "
                    f"{resultado['motivo']}"
                ),
                None
            )

            await registrar_log_infracao(
                message,
                resultado,
                nivel
            )

            return True

        # ========================================================
        # NÍVEL 2 — SILENCIAMENTO
        # ========================================================

        if nivel == 2:
            duracao = 10

            historico = historico_punicoes(
                guild.id,
                membro.id
            )

            reincidencias = len([
                item
                for item in historico
                if (
                    f"categoria="
                    f"{resultado['categoria'].lower()}"
                    in str(
                        item.get(
                            "motivo",
                            ""
                        )
                    ).lower()
                )
            ])

            if reincidencias >= 2:
                duracao = 30
            elif reincidencias >= 1:
                duracao = 20

            try:
                await membro.timeout(
                    datetime.timedelta(
                        minutes=duracao
                    ),
                    reason=(
                        f"AutoMod: "
                        f"{resultado['motivo']}"
                    )
                )
            except Exception:
                return False

            registrar_punicao(
                guild.id,
                membro.id,
                "mute",
                (
                    f"categoria="
                    f"{resultado['categoria']} | "
                    f"{resultado['motivo']} | "
                    f"duração={duracao}min"
                ),
                None
            )

            await registrar_log_infracao(
                message,
                resultado,
                nivel
            )

            return True

        # ========================================================
        # NÍVEL 3 — EXPULSÃO
        # ========================================================

        if nivel == 3:
            try:
                await membro.kick(
                    reason=(
                        f"AutoMod: "
                        f"{resultado['motivo']}"
                    )
                )
            except Exception:
                return False

            registrar_punicao(
                guild.id,
                membro.id,
                "kick",
                (
                    f"categoria="
                    f"{resultado['categoria']} | "
                    f"{resultado['motivo']}"
                ),
                None
            )

            await registrar_log_infracao(
                message,
                resultado,
                nivel
            )

            return True

        # ========================================================
        # NÍVEL 4 — BANIMENTO TEMPORÁRIO
        # ========================================================

        if nivel == 4:
            historico = historico_punicoes(
                guild.id,
                membro.id
            )

            reincidencias = len([
                item
                for item in historico
                if (
                    f"categoria="
                    f"{resultado['categoria'].lower()}"
                    in str(
                        item.get(
                            "motivo",
                            ""
                        )
                    ).lower()
                )
            ])

            duracao_horas = 24

            if reincidencias >= 1:
                duracao_horas = 72

            try:
                await guild.ban(
                    membro,
                    reason=(
                        f"AutoMod: "
                        f"{resultado['motivo']}"
                    ),
                    delete_message_seconds=0
                )
            except Exception:
                return False

            self.registrar_banimento_temporario(
                guild.id,
                membro.id,
                duracao_horas * 60 * 60
            )

            registrar_punicao(
                guild.id,
                membro.id,
                "ban_temp",
                (
                    f"categoria="
                    f"{resultado['categoria']} | "
                    f"{resultado['motivo']} | "
                    f"duração="
                    f"{duracao_horas}h"
                ),
                None
            )

            await registrar_log_infracao(
                message,
                resultado,
                nivel
            )

            return True

        # ========================================================
        # NÍVEL 5 — BANIMENTO PERMANENTE
        # ========================================================

        if nivel >= 5:
            try:
                await guild.ban(
                    membro,
                    reason=(
                        f"AutoMod: "
                        f"{resultado['motivo']}"
                    ),
                    delete_message_seconds=0
                )
            except Exception:
                return False

            registrar_punicao(
                guild.id,
                membro.id,
                "ban",
                (
                    f"categoria="
                    f"{resultado['categoria']} | "
                    f"{resultado['motivo']}"
                ),
                None
            )

            await registrar_log_infracao(
                message,
                resultado,
                nivel
            )

            return True

        return False
    # ============================================================
    # EVENTO PRINCIPAL
    # ============================================================

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignora mensagens sem servidor
        if message.guild is None:
            return

        # Ignora bots
        if message.author.bot:
            return

        # Ignora o canal oficial das regras
        if message.channel.id == CANAL_REGRAS_ID:
            return

        guild = message.guild
        membro = message.author

        # ========================================================
        # EXCEÇÕES DE STAFF
        # ========================================================

        try:
            permissao = membro.guild_permissions

            if (
                permissao.administrator
                or permissao.manage_guild
                or permissao.manage_messages
            ):
                return

        except Exception:
            pass

        # ========================================================
        # REGISTRO DE ATIVIDADE
        # ========================================================

        chave = (
            guild.id,
            membro.id
        )

        if chave not in self.historico_mensagens:
            self.historico_mensagens[chave] = deque(
                maxlen=30
            )

        if chave not in self.ultimas_mensagens:
            self.ultimas_mensagens[chave] = deque(
                maxlen=10
            )

        agora = time.time()

        self.historico_mensagens[chave].append(
            agora
        )

        self.ultimas_mensagens[chave].append(
            message.content
        )

        # ========================================================
        # ANÁLISE
        # ========================================================

        try:
            resultado = await self.analisar_infracao(
                message
            )
        except Exception as erro:
            print(
                f"[AutoMod] Erro ao analisar mensagem: {erro}"
            )
            return

        if not resultado:
            return

        # Nível 0 significa que precisa de análise humana
        if resultado["nivel"] <= 0:
            await self.registrar_log_infracao(
                message,
                resultado,
                0
            )
            return

        # ========================================================
        # TENTA APAGAR A MENSAGEM
        # ========================================================

        try:
            await message.delete()
        except discord.Forbidden:
            pass
        except discord.NotFound:
            pass
        except Exception as erro:
            print(
                f"[AutoMod] Não foi possível apagar "
                f"a mensagem: {erro}"
            )

        # ========================================================
        # APLICA PUNIÇÃO
        # ========================================================

        try:
            aplicado = await self.aplicar_punicao(
                message,
                resultado
            )

            if aplicado:
                print(
                    "[AutoMod] Infração aplicada: "
                    f"{message.author} | "
                    f"Nível {resultado['nivel']} | "
                    f"{resultado['categoria']}"
                )

        except Exception as erro:
            print(
                f"[AutoMod] Erro ao aplicar punição: {erro}"
            )

    # ============================================================
    # VERIFICAÇÃO DE BANIMENTOS TEMPORÁRIOS
    # ============================================================

    @tasks.loop(seconds=30)
    async def verificar_banimentos(self):
        dados = (
            self.carregar_banimentos_temporarios()
        )

        if not dados:
            return

        agora = time.time()

        alterado = False

        for chave, registro in list(
            dados.items()
        ):
            try:
                guild_id = int(
                    registro["guild_id"]
                )

                membro_id = int(
                    registro["membro_id"]
                )

                expira_em = float(
                    registro["expira_em"]
                )

            except (
                KeyError,
                TypeError,
                ValueError
            ):
                del dados[chave]
                alterado = True
                continue

            if agora < expira_em:
                continue

            guild = self.bot.get_guild(
                guild_id
            )

            if guild is None:
                continue

            try:
                usuario = await self.bot.fetch_user(
                    membro_id
                )

                await guild.unban(
                    usuario,
                    reason="Fim do banimento temporário do AutoMod"
                )

                print(
                    "[AutoMod] Banimento temporário "
                    f"finalizado: {membro_id}"
                )

            except discord.NotFound:
                pass

            except discord.Forbidden:
                print(
                    "[AutoMod] Sem permissão para "
                    f"desbanir {membro_id} em {guild_id}"
                )

            except Exception as erro:
                print(
                    "[AutoMod] Erro ao finalizar "
                    f"banimento temporário: {erro}"
                )
                continue

            del dados[chave]
            alterado = True

        if alterado:
            self.salvar_banimentos_temporarios(
                dados
            )

    @verificar_banimentos.before_loop
    async def antes_verificar_banimentos(self):
        await self.bot.wait_until_ready()

    # ============================================================
    # COMANDO — VISUALIZAR REGRAS LIDAS PELO AUTOMOD
    # ============================================================

    @app_commands.command(
        name="automod-regras",
        description=(
            "Mostra as regras que o AutoMod "
            "está utilizando como referência."
        )
    )
    async def automod_regras(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        regras = await self.carregar_regras_oficiais(
            forcar=True
        )

        if not regras:
            await interaction.followup.send(
                "Não foi possível carregar as regras "
                "do canal oficial.",
                ephemeral=True
            )
            return

        secoes = regras.get(
            "secoes",
            {}
        )

        if not secoes:
            await interaction.followup.send(
                "O canal oficial foi encontrado, mas "
                "nenhuma seção numerada foi identificada.",
                ephemeral=True
            )
            return

        linhas = []

        for numero in sorted(
            secoes.keys()
        ):
            titulo = secoes[numero].get(
                "titulo",
                "Sem título"
            )

            linhas.append(
                f"**{numero:02d} — {titulo}**"
            )

        embed = discord.Embed(
            title="AutoMod — Regras Oficiais",
            description=(
                "Fonte oficial:\n"
                f"<#{CANAL_REGRAS_ID}>\n\n"
                "Seções identificadas:\n\n"
                + "\n".join(linhas)
            ),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text=(
                "As regras são lidas diretamente "
                "do canal oficial."
            )
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    # ============================================================
    # COMANDO — ATUALIZAR REGRAS
    # ============================================================

    @app_commands.command(
        name="automod-atualizar",
        description=(
            "Atualiza imediatamente a leitura "
            "das regras oficiais."
        )
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def automod_atualizar(
        self,
        interaction: discord.Interaction
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Você precisa ter permissão de "
                "Administrador para utilizar este comando.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        regras = await self.carregar_regras_oficiais(
            forcar=True
        )

        if not regras:
            await interaction.followup.send(
                "Não foi possível atualizar as regras.",
                ephemeral=True
            )
            return

        quantidade = len(
            regras.get(
                "secoes",
                {}
            )
        )

        await interaction.followup.send(
            (
                "As regras oficiais foram atualizadas.\n\n"
                f"**Seções identificadas:** `{quantidade}`\n"
                f"**Canal fonte:** <#{CANAL_REGRAS_ID}>"
            ),
            ephemeral=True
        )


# ================================================================
# SETUP DO COG
# ================================================================

async def setup(bot):
    await bot.add_cog(
        AutoMod(bot)
    )