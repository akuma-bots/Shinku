import datetime
import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.auditoria import registrar
from utils.punicoes import (
    historico_punicoes,
    registrar_punicao,
)
from utils.storage import (
    carregar,
    salvar,
)


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
CATEGORIA_CONDUTA = "CONDUTA"
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
    r"(?:discord\.gg|discord\.com/invite|"
    r"discordapp\.com/invite)/"
    r"[A-Za-z0-9-]+",
    re.IGNORECASE,
)


PHISHING_PATTERNS = [
    re.compile(r"nitro\s+gratis", re.I),
    re.compile(r"discord\s+nitro\s+gratis", re.I),
    re.compile(
        r"clique\s+aqui\s+para\s+ganhar",
        re.I,
    ),
    re.compile(
        r"resgate\s+seu\s+nitro",
        re.I,
    ),
    re.compile(r"gift\s+nitro", re.I),
    re.compile(r"free\s+nitro", re.I),
    re.compile(
        r"steam\s+gift\s+free",
        re.I,
    ),
    re.compile(
        r"robux\s+gratis",
        re.I,
    ),
    re.compile(
        r"robux\s+free",
        re.I,
    ),
    re.compile(
        r"verifique\s+sua\s+conta",
        re.I,
    ),
    re.compile(
        r"confirme\s+sua\s+conta",
        re.I,
    ),
    re.compile(
        r"login\s+para\s+receber",
        re.I,
    ),
]


MALWARE_PATTERNS = [
    re.compile(r"\bstealer\b", re.I),
    re.compile(r"\brat\b", re.I),
    re.compile(r"keylogger", re.I),
    re.compile(
        r"roubar\s+token",
        re.I,
    ),
    re.compile(
        r"token\s+logger",
        re.I,
    ),
    re.compile(
        r"token\s+grabber",
        re.I,
    ),
    re.compile(
        r"roubar\s+conta",
        re.I,
    ),
    re.compile(
        r"invas[aã]o\s+de\s+conta",
        re.I,
    ),
    re.compile(
        r"hackear\s+conta",
        re.I,
    ),
]


DOXXING_PATTERNS = [
    re.compile(r"doxx", re.I),
    re.compile(r"doxing", re.I),
    re.compile(
        r"expor\s+o\s+endereço",
        re.I,
    ),
    re.compile(
        r"expor\s+endereco",
        re.I,
    ),
    re.compile(
        r"expor\s+dados\s+pessoais",
        re.I,
    ),
    re.compile(
        r"vazar\s+dados",
        re.I,
    ),
    re.compile(
        r"vazar\s+informações",
        re.I,
    ),
    re.compile(
        r"vazar\s+informacoes",
        re.I,
    ),
]


INVASION_PATTERNS = [
    re.compile(
        r"invadir\s+o\s+servidor",
        re.I,
    ),
    re.compile(
        r"derrubar\s+o\s+servidor",
        re.I,
    ),
    re.compile(
        r"raidar\s+o\s+servidor",
        re.I,
    ),
    re.compile(
        r"raidear\s+o\s+servidor",
        re.I,
    ),
    re.compile(
        r"destruir\s+o\s+servidor",
        re.I,
    ),
    re.compile(
        r"atacar\s+o\s+servidor",
        re.I,
    ),
]


THREAT_PATTERNS = [
    re.compile(
        r"vou\s+te\s+matar",
        re.I,
    ),
    re.compile(
        r"vou\s+matar\s+voc[eê]",
        re.I,
    ),
    re.compile(
        r"vou\s+te\s+machucar",
        re.I,
    ),
    re.compile(
        r"vou\s+atr[aá]s\s+de\s+voc[eê]",
        re.I,
    ),
    re.compile(
        r"vou\s+acabar\s+com\s+voc[eê]",
        re.I,
    ),
]


HARASSMENT_PATTERNS = [
    re.compile(
        r"vai\s+se\s+foder",
        re.I,
    ),
    re.compile(
        r"vai\s+tomar\s+no\s+cu",
        re.I,
    ),
    re.compile(
        r"seu\s+in[uú]til",
        re.I,
    ),
    re.compile(
        r"seu\s+lixo",
        re.I,
    ),
]


CHEAT_PATTERNS = [
    re.compile(
        r"\bexploit\b",
        re.I,
    ),
    re.compile(
        r"\bcheat\b",
        re.I,
    ),
    re.compile(
        r"\bhack\b",
        re.I,
    ),
    re.compile(
        r"\bscript\s+de\s+hack",
        re.I,
    ),
    re.compile(
        r"\bexecutor\b",
        re.I,
    ),
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


def porcentagem_maiusculas(
    texto: str,
) -> float:

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


def possui_url(
    texto: str,
) -> bool:

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
            lambda: deque(
                maxlen=30
            )
        )

        self.ultimas_mensagens = defaultdict(
            lambda: deque(
                maxlen=10
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
            return self.regras_cache[
                guild.id
            ]

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

            titulo = (
                match.group(2)
                .strip()
            )

            inicio = match.end()

            if i + 1 < len(
                encontrados
            ):
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
    # =========================================================
    # DETECÇÕES BÁSICAS
    # =========================================================

    def detectar_spam(self, message: discord.Message) -> bool:
        """Detecta excesso de mensagens enviadas em pouco tempo."""
        chave = (message.guild.id, message.author.id)
        agora = time.monotonic()

        fila = self.historico_mensagens[chave]

        while fila and agora - fila[0] > JANELA_SPAM:
            fila.popleft()

        return len(fila) >= LIMITE_SPAM

    def detectar_repeticao(self, message: discord.Message) -> bool:
        """Detecta repetição excessiva do mesmo conteúdo."""
        chave = (message.guild.id, message.author.id)

        texto_atual = normalizar_texto(message.content)

        if not texto_atual:
            return False

        mensagens = self.ultimas_mensagens[chave]

        repeticoes = sum(
            1
            for texto, _ in mensagens
            if texto == texto_atual
        )

        # A mensagem atual já foi adicionada antes da análise.
        return repeticoes >= LIMITE_REPETICAO

    def detectar_caps_spam(self, message: discord.Message) -> bool:
        """Detecta mensagens excessivamente escritas em CAPS LOCK."""
        texto = message.content

        letras = [char for char in texto if char.isalpha()]

        if len(letras) < 12:
            return False

        return porcentagem_maiusculas(texto) >= 0.80

    def detectar_mencao_massa(self, message: discord.Message) -> bool:
        """Detecta excesso de menções ou @everyone/@here."""
        if message.mention_everyone:
            return True

        total = len(message.mentions) + len(message.role_mentions)

        return total >= LIMITE_MENCOES

    def detectar_divulgacao(self, message: discord.Message) -> bool:
        """
        Detecta divulgação potencialmente não autorizada.

        A detecção é propositalmente conservadora:
        apenas URLs, convites Discord e padrões explícitos de divulgação.
        """
        texto = normalizar_texto(message.content)

        if not texto:
            return False

        if possui_convite_discord(texto):
            return True

        if "clique aqui" in texto and possui_url(texto):
            return True

        termos = (
            "entre no meu servidor",
            "entrem no meu servidor",
            "entrem no servidor",
            "meu servidor",
            "nosso servidor",
            "divulga meu servidor",
            "divulguem meu servidor",
            "acesse meu servidor",
            "acessem meu servidor",
            "link do servidor",
        )

        return possui_url(texto) and any(
            termo in texto for termo in termos
        )

    # =========================================================
    # DETECÇÕES DE SEGURANÇA
    # =========================================================

    def detectar_phishing(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            PHISHING_PATTERNS,
        )

    def detectar_malware(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            MALWARE_PATTERNS,
        )

    def detectar_doxxing(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            DOXXING_PATTERNS,
        )

    def detectar_invasao(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            INVASION_PATTERNS,
        )

    def detectar_ameaca(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            THREAT_PATTERNS,
        )

    def detectar_assedio(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            HARASSMENT_PATTERNS,
        )

    def detectar_exploit(self, message: discord.Message) -> bool:
        return contem_padrao(
            message.content,
            CHEAT_PATTERNS,
        )

    # =========================================================
    # ANÁLISE DA INFRAÇÃO
    # =========================================================

    async def analisar_infracao(
        self,
        message: discord.Message,
    ) -> dict | None:
        """
        Analisa a mensagem e determina:

        - categoria;
        - nível;
        - nome da infração;
        - punição sugerida;
        - regra relacionada.

        O sistema não pune apenas por uma palavra isolada.
        """

        regras = await self.carregar_regras_oficiais(
            message.guild
        )

        infracoes = []

        # -----------------------------------------------------
        # NÍVEL 5 — CRÍTICO
        # -----------------------------------------------------

        if self.detectar_invasao(message):
            infracoes.append({
                "categoria": CATEGORIA_SEGURANCA,
                "nivel": 5,
                "infracao": "Tentativa de invasão ou comprometimento de sistemas",
                "regra": "04",
            })

        # -----------------------------------------------------
        # NÍVEL 4 — MUITO GRAVE
        # -----------------------------------------------------

        if self.detectar_phishing(message):
            infracoes.append({
                "categoria": CATEGORIA_SEGURANCA,
                "nivel": 4,
                "infracao": "Possível tentativa de phishing",
                "regra": "04",
            })

        if self.detectar_malware(message):
            infracoes.append({
                "categoria": CATEGORIA_SEGURANCA,
                "nivel": 4,
                "infracao": "Possível distribuição de malware",
                "regra": "04",
            })

        if self.detectar_doxxing(message):
            infracoes.append({
                "categoria": CATEGORIA_SEGURANCA,
                "nivel": 4,
                "infracao": "Exposição de informações pessoais",
                "regra": "04",
            })

        # -----------------------------------------------------
        # NÍVEL 3 — GRAVE
        # -----------------------------------------------------

        if self.detectar_ameaca(message):
            infracoes.append({
                "categoria": CATEGORIA_CONDUTA,
                "nivel": 3,
                "infracao": "Ameaça",
                "regra": "01",
            })

        if self.detectar_assedio(message):
            infracoes.append({
                "categoria": CATEGORIA_CONDUTA,
                "nivel": 3,
                "infracao": "Assédio ou perseguição",
                "regra": "01",
            })

        # -----------------------------------------------------
        # NÍVEL 2 — MÉDIO
        # -----------------------------------------------------

        if self.detectar_divulgacao(message):
            infracoes.append({
                "categoria": CATEGORIA_DIVULGACAO,
                "nivel": 2,
                "infracao": "Divulgação não autorizada",
                "regra": "05",
            })

        if self.detectar_exploit(message):
            infracoes.append({
                "categoria": CATEGORIA_JOGOS,
                "nivel": 2,
                "infracao": "Uso ou divulgação de exploit/cheat",
                "regra": "08",
            })

        # -----------------------------------------------------
        # NÍVEL 1 — NORMAL
        # -----------------------------------------------------

        if self.detectar_spam(message):
            infracoes.append({
                "categoria": CATEGORIA_COMUNICACAO,
                "nivel": 1,
                "infracao": "Spam ou flood",
                "regra": "02",
            })

        if self.detectar_repeticao(message):
            infracoes.append({
                "categoria": CATEGORIA_COMUNICACAO,
                "nivel": 1,
                "infracao": "Repetição excessiva de mensagens",
                "regra": "02",
            })

        if self.detectar_caps_spam(message):
            infracoes.append({
                "categoria": CATEGORIA_COMUNICACAO,
                "nivel": 1,
                "infracao": "Uso excessivo de CAPS LOCK",
                "regra": "02",
            })

        if self.detectar_mencao_massa(message):
            infracoes.append({
                "categoria": CATEGORIA_COMUNICACAO,
                "nivel": 1,
                "infracao": "Excesso de menções",
                "regra": "02",
            })

        if not infracoes:
            return None

        # Pega sempre a infração de maior gravidade.
        infracao = max(
            infracoes,
            key=lambda item: item["nivel"],
        )

        # Verifica se a seção correspondente realmente existe
        # no canal oficial de regras.
        if not self.regra_existe(
            regras,
            infracao["regra"],
        ):
            infracao["regra"] = None

        nivel = await self.calcular_nivel_reincidencia(
            message.guild.id,
            message.author.id,
            infracao["nivel"],
        )

        infracao["nivel_original"] = infracao["nivel"]
        infracao["nivel"] = nivel
        infracao["nivel_info"] = NIVEIS[nivel]
        infracao["reincidencia"] = nivel > infracao["nivel_original"]

        return infracao

    # =========================================================
    # REINCIDÊNCIA
    # =========================================================

    async def calcular_nivel_reincidencia(
        self,
        guild_id: int,
        membro_id: int,
        nivel_atual: int,
    ) -> int:
        """
        Eleva progressivamente a punição quando o usuário possui
        histórico recente de infrações automáticas.
        """

        try:
            historico = await historico_punicoes(
                guild_id,
                membro_id,
            )
        except Exception:
            return nivel_atual

        if not historico:
            return nivel_atual

        agora = datetime.datetime.now(
            datetime.timezone.utc
        ).timestamp()

        recentes = []

        for registro in historico:
            data = registro.get("data")

            if not data:
                continue

            try:
                if isinstance(data, str):
                    data_obj = datetime.datetime.fromisoformat(
                        data.replace("Z", "+00:00")
                    )
                    timestamp = data_obj.timestamp()
                else:
                    timestamp = float(data)
            except (ValueError, TypeError):
                continue

            if agora - timestamp <= JANELA_REINCIDENCIA:
                recentes.append(registro)

        if not recentes:
            return nivel_atual

        # Cada punição automática recente pode elevar o nível.
        quantidade = sum(
            1
            for registro in recentes
            if registro.get("tipo") in {
                "aviso_automatico",
                "warn",
                "mute",
                "kick",
                "ban",
                "ban_temp",
            }
        )

        if quantidade >= 4:
            return min(5, nivel_atual + 2)

        if quantidade >= 2:
            return min(5, nivel_atual + 1)

        return nivel_atual

    # =========================================================
    # COOLDOWN
    # =========================================================

    def em_cooldown(
        self,
        guild_id: int,
        membro_id: int,
    ) -> bool:
        chave = (guild_id, membro_id)
        agora = time.monotonic()

        ultimo = self.cooldowns.get(chave)

        if ultimo is None:
            return False

        return (
            agora - ultimo
        ) < COOLDOWN_PUNICAO

    def registrar_cooldown(
        self,
        guild_id: int,
        membro_id: int,
    ):
        self.cooldowns[
            (guild_id, membro_id)
        ] = time.monotonic()

    # =========================================================
    # REGISTRO DO HISTÓRICO
    # =========================================================

    async def registrar_historico(
        self,
        message: discord.Message,
        infracao: dict,
        tipo_punicao: str,
    ):
        """Registra a punição automática no histórico do bot."""

        motivo = (
            f"AutoMod | "
            f"Nível {infracao['nivel']} — "
            f"{infracao['nivel_info']['nome']} | "
            f"{infracao['infracao']}"
        )

        try:
            await registrar_punicao(
                guild_id=message.guild.id,
                membro_id=message.author.id,
                tipo=tipo_punicao,
                motivo=motivo,
                aplicado_por_id=None,
            )
        except Exception:
            pass

    # =========================================================
    # PUNIÇÃO — DEFINIÇÃO
    # =========================================================

    def obter_punicao(
        self,
        nivel: int,
    ) -> str:
        return NIVEIS.get(
            nivel,
            NIVEIS[1],
        )["punicao"]

    # =========================================================
    # MENSAGEM DE MODERAÇÃO
    # =========================================================

    async def enviar_aviso_automod(
        self,
        message: discord.Message,
        infracao: dict,
        punicao: str,
    ):
        """
        Envia uma mensagem curta informando que a mensagem
        foi moderada.
        """

        try:
            await message.channel.send(
                (
                    f"⚠️・{message.author.mention}, sua mensagem foi "
                    f"moderada automaticamente.\n"
                    f"**Motivo:** {infracao['infracao']}\n"
                    f"**Medida:** {punicao}"
                ),
                delete_after=8,
            )
        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            pass
    # =========================================================
    # APLICAÇÃO DAS PUNIÇÕES
    # =========================================================

    async def aplicar_punicao(
        self,
        message: discord.Message,
        infracao: dict,
    ):
        membro = message.author
        guild = message.guild
        nivel = infracao["nivel"]

        # Impede duas punições simultâneas para o mesmo usuário.
        chave = (guild.id, membro.id)

        if chave in self.punicoes_em_andamento:
            return

        self.punicoes_em_andamento.add(chave)

        try:
            # Remove a mensagem infratora primeiro.
            try:
                await message.delete()
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException,
            ):
                pass

            if nivel == 1:
                # =============================================
                # NÍVEL 1 — ADVERTÊNCIA
                # =============================================

                await self.registrar_historico(
                    message,
                    infracao,
                    "aviso_automatico",
                )

                await self.enviar_aviso_automod(
                    message,
                    infracao,
                    "Advertência",
                )

            elif nivel == 2:
                # =============================================
                # NÍVEL 2 — SILENCIAMENTO
                # =============================================

                try:
                    duracao = datetime.timedelta(minutes=10)

                    await membro.timeout(
                        duracao,
                        reason=(
                            f"AutoMod: "
                            f"{infracao['infracao']}"
                        ),
                    )

                    tipo = "mute"

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    tipo = "aviso_automatico"

                await self.registrar_historico(
                    message,
                    infracao,
                    tipo,
                )

                await self.enviar_aviso_automod(
                    message,
                    infracao,
                    "Silenciamento por 10 minutos",
                )

            elif nivel == 3:
                # =============================================
                # NÍVEL 3 — EXPULSÃO
                # =============================================

                try:
                    await membro.kick(
                        reason=(
                            f"AutoMod: "
                            f"{infracao['infracao']}"
                        ),
                    )

                    tipo = "kick"

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    tipo = "aviso_automatico"

                await self.registrar_historico(
                    message,
                    infracao,
                    tipo,
                )

            elif nivel == 4:
                # =============================================
                # NÍVEL 4 — BANIMENTO TEMPORÁRIO
                # =============================================

                duracao = 24 * 60 * 60

                try:
                    await guild.ban(
                        membro,
                        reason=(
                            f"AutoMod: "
                            f"{infracao['infracao']}"
                        ),
                    )

                    await self.registrar_banimento_temporario(
                        guild.id,
                        membro.id,
                        duracao,
                    )

                    tipo = "ban_temp"

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    tipo = "aviso_automatico"

                await self.registrar_historico(
                    message,
                    infracao,
                    tipo,
                )

            elif nivel >= 5:
                # =============================================
                # NÍVEL 5 — BANIMENTO PERMANENTE
                # =============================================

                try:
                    await guild.ban(
                        membro,
                        reason=(
                            f"AutoMod: "
                            f"{infracao['infracao']}"
                        ),
                    )

                    tipo = "ban"

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    tipo = "aviso_automatico"

                await self.registrar_historico(
                    message,
                    infracao,
                    tipo,
                )

        finally:
            self.punicoes_em_andamento.discard(chave)

    # =========================================================
    # BANIMENTOS TEMPORÁRIOS
    # =========================================================

    async def registrar_banimento_temporario(
        self,
        guild_id: int,
        membro_id: int,
        duracao: int,
    ):
        dados = await carregar(
            ARQUIVO_BANIMENTOS_TEMPORARIOS,
            {},
        )

        if not isinstance(dados, dict):
            dados = {}

        agora = datetime.datetime.now(
            datetime.timezone.utc
        ).timestamp()

        chave = f"{guild_id}:{membro_id}"

        dados[chave] = {
            "guild_id": guild_id,
            "membro_id": membro_id,
            "expira_em": agora + duracao,
        }

        await salvar(
            ARQUIVO_BANIMENTOS_TEMPORARIOS,
            dados,
        )

    @tasks.loop(seconds=30)
    async def verificar_banimentos(self):
        dados = await carregar(
            ARQUIVO_BANIMENTOS_TEMPORARIOS,
            {},
        )

        if not isinstance(dados, dict) or not dados:
            return

        agora = datetime.datetime.now(
            datetime.timezone.utc
        ).timestamp()

        alterado = False

        for chave, registro in list(dados.items()):
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
                ValueError,
            ):
                dados.pop(chave, None)
                alterado = True
                continue

            if agora < expira_em:
                continue

            guild = self.bot.get_guild(guild_id)

            if guild is None:
                continue

            try:
                await guild.unban(
                    discord.Object(id=membro_id),
                    reason="Fim do banimento temporário do AutoMod",
                )
            except discord.NotFound:
                pass
            except (
                discord.Forbidden,
                discord.HTTPException,
            ):
                continue

            dados.pop(chave, None)
            alterado = True

        if alterado:
            await salvar(
                ARQUIVO_BANIMENTOS_TEMPORARIOS,
                dados,
            )

    @verificar_banimentos.before_loop
    async def antes_de_verificar_banimentos(self):
        await self.bot.wait_until_ready()

    # =========================================================
    # EVENTO PRINCIPAL DO AUTOMOD
    # =========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):
        # Ignora mensagens sem servidor.
        if message.guild is None:
            return

        # Ignora bots.
        if message.author.bot:
            return

        # O próprio canal de regras é somente leitura.
        # Não executamos AutoMod nele.
        if message.channel.id == CANAL_REGRAS_ID:
            return

        membro = message.author

        # -----------------------------------------------------
        # REGISTRO PARA DETECÇÃO DE SPAM
        # -----------------------------------------------------

        chave = (
            message.guild.id,
            membro.id,
        )

        agora = time.monotonic()

        self.historico_mensagens[
            chave
        ].append(agora)

        self.ultimas_mensagens[
            chave
        ].append(
            (
                normalizar_texto(
                    message.content
                ),
                agora,
            )
        )

        # Limpa mensagens antigas.
        while (
            self.historico_mensagens[chave]
            and agora
            - self.historico_mensagens[chave][0]
            > JANELA_SPAM
        ):
            self.historico_mensagens[chave].popleft()

        while (
            self.ultimas_mensagens[chave]
            and agora
            - self.ultimas_mensagens[chave][0][1]
            > JANELA_REPETICAO
        ):
            self.ultimas_mensagens[chave].popleft()

        # -----------------------------------------------------
        # IGNORA EQUIPE DE MODERAÇÃO
        # -----------------------------------------------------

        permissoes = membro.guild_permissions

        if (
            permissoes.administrator
            or permissoes.manage_guild
            or permissoes.manage_messages
        ):
            return

        # -----------------------------------------------------
        # COOLDOWN
        # -----------------------------------------------------

        if self.em_cooldown(
            message.guild.id,
            membro.id,
        ):
            return

        # -----------------------------------------------------
        # ANÁLISE
        # -----------------------------------------------------

        try:
            infracao = await self.analisar_infracao(
                message
            )
        except Exception:
            return

        if infracao is None:
            return

        # -----------------------------------------------------
        # COOLDOWN
        # -----------------------------------------------------

        self.registrar_cooldown(
            message.guild.id,
            membro.id,
        )

        # -----------------------------------------------------
        # PUNIÇÃO
        # -----------------------------------------------------

        await self.aplicar_punicao(
            message,
            infracao,
        )

    # =========================================================
    # COMANDO — VER REGRAS OFICIAIS
    # =========================================================

    @app_commands.command(
        name="automod-regras",
        description="Verifica as regras oficiais usadas pelo AutoMod.",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def automod_regras(
        self,
        interaction: discord.Interaction,
    ):
        regras = await self.carregar_regras_oficiais(
            interaction.guild,
            forcar=True,
        )

        if not regras:
            await interaction.response.send_message(
                (
                    "❌ Não foi possível carregar as regras "
                    "oficiais do servidor."
                ),
                ephemeral=True,
            )
            return

        secoes = regras.get(
            "secoes",
            {},
        )

        embed = discord.Embed(
            title="NÊMESIS — AutoMod",
            description=(
                "O AutoMod utiliza o canal oficial de regras "
                f"<#{CANAL_REGRAS_ID}> como fonte de referência."
            ),
            color=discord.Color.blurple(),
        )

        if secoes:
            lista = "\n".join(
                f"**{numero}.** {titulo}"
                for numero, titulo in secoes.items()
            )

            embed.add_field(
                name="Seções encontradas",
                value=lista[:1024],
                inline=False,
            )

        embed.add_field(
            name="Status",
            value="🟢 Regras carregadas com sucesso.",
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # =========================================================
    # COMANDO — ATUALIZAR REGRAS
    # =========================================================

    @app_commands.command(
        name="automod-atualizar",
        description="Atualiza manualmente as regras do AutoMod.",
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def automod_atualizar(
        self,
        interaction: discord.Interaction,
    ):
        regras = await self.carregar_regras_oficiais(
            interaction.guild,
            forcar=True,
        )

        if not regras:
            await interaction.response.send_message(
                (
                    "❌ Não consegui atualizar as regras. "
                    f"Verifique se tenho acesso ao canal <#{CANAL_REGRAS_ID}>."
                ),
                ephemeral=True,
            )
            return

        quantidade = len(
            regras.get(
                "secoes",
                {},
            )
        )

        await interaction.response.send_message(
            (
                "✅ **Regras atualizadas.**\n\n"
                f"Seções encontradas: **{quantidade}**\n"
                f"Fonte: <#{CANAL_REGRAS_ID}>"
            ),
            ephemeral=True,
        )


# =============================================================
# SETUP
# =============================================================

async def setup(bot):
    await bot.add_cog(
        AutoMod(bot)
    )