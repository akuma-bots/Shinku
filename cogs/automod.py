import datetime
import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.punicoes import historico_punicoes, registrar_punicao
from utils.storage import carregar, salvar


CANAL_REGRAS_ID = 1545831172796583987
CACHE_REGRAS_SEGUNDOS = 1
ARQUIVO_BANIMENTOS_TEMPORARIOS = "automod_banimentos.json"

JANELA_SPAM, LIMITE_SPAM = 8, 6
JANELA_REPETICAO, LIMITE_REPETICAO = 20, 3
LIMITE_MENCOES = 5
COOLDOWN_PUNICAO = 1
JANELA_REINCIDENCIA = 30 * 24 * 60 * 60


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


URL_REGEX = re.compile(
    r"https?://[^\s]+|www\.[^\s]+",
    re.I,
)

DISCORD_INVITE_REGEX = re.compile(
    r"(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+",
    re.I,
)


# ============================================================
# PHISHING
# ============================================================

PADROES_PHISHING = [
    r"nitro\s+gr[aá]tis",
    r"discord\s+nitro\s+gr[aá]tis",
    r"clique\s+aqui\s+para\s+ganhar",
    r"resgate\s+(?:seu|o)\s+nitro",
    r"gift\s+nitro",
    r"free\s+nitro",
    r"steam\s+gift\s+free",
    r"robux\s+(?:gr[aá]tis|free)",
    r"verifique\s+sua\s+conta",
    r"confirme\s+sua\s+conta",
    r"login\s+para\s+receber",
    r"acesse\s+para\s+receber",
]


# ============================================================
# MALWARE
# ============================================================

PADROES_MALWARE = [
    r"\bstealer\b",
    r"\bkeylogger\b",
    r"\brat\b",
    r"token\s*(?:logger|grabber)",
    r"roubar\s+token",
    r"roubar\s+conta",
    r"roubo\s+de\s+token",
    r"roubo\s+de\s+conta",
    r"invas[aã]o\s+de\s+conta",
    r"hackear\s+conta",
]


# ============================================================
# DOXXING
# ============================================================

PADROES_DOXXING = [
    r"\bdoxx(?:ing)?\b",
    r"expor\s+(?:seu\s+)?endere[cç]o",
    r"expor\s+dados\s+pessoais",
    r"vazar\s+dados",
    r"vazar\s+informa[cç][oõ]es",
    r"expor\s+ip",
    r"vazar\s+ip",
    r"expor\s+telefone",
    r"expor\s+cpf",
]


# ============================================================
# INVASÃO / SABOTAGEM
# ============================================================

PADROES_INVASAO = [
    r"invadir\s+o\s+servidor",
    r"invadir\s+o\s+sistema",
    r"derrubar\s+o\s+servidor",
    r"derrubar\s+o\s+sistema",
    r"raidar\s+o\s+servidor",
    r"raidear\s+o\s+servidor",
    r"destruir\s+o\s+servidor",
    r"atacar\s+o\s+servidor",
    r"sabotar\s+o\s+servidor",
]


# ============================================================
# AMEAÇAS
# ============================================================

PADROES_AMEACA = [
    r"vou\s+te\s+matar",
    r"vou\s+matar\s+voc[eê]",
    r"vou\s+te\s+machucar",
    r"vou\s+atr[aá]s\s+de\s+voc[eê]",
    r"vou\s+acabar\s+com\s+voc[eê]",
    r"vai\s+morrer",
    r"voc[eê]\s+vai\s+morrer",
    r"voc[eê]\s+e\s+sua\s+fam[ií]lia\s+v[aã]o\s+morrer",
    r"sua\s+m[aã]e\s+tem\s+(?:que|q)\s+morrer",
    r"sua\s+m[aã]e\s+vai\s+morrer",
    r"sua\s+fam[ií]lia\s+vai\s+morrer",
    r"que\s+sua\s+m[aã]e\s+morra",
    r"que\s+voc[eê]\s+morra",
]


# ============================================================
# OFENSAS / ASSÉDIO
# ============================================================

PADROES_ASSÉDIO = [
    r"vai\s+se\s+foder",
    r"vai\s+se\s+fude",
    r"vai\s+se\s+fuder",
    r"vai\s+tomar\s+no\s+cu",
    r"toma\s+no\s+cu",

    r"filh[oa]\s+da\s+puta",
    r"\bfdp\b",
    r"\bputa\b",
    r"\bputo\b",

    r"\barrombado\b",
    r"\barrombada\b",
    r"\bpau\s+no\s+cu\b",

    r"\bfudido\b",
    r"\bfudida\b",

    r"\bcaralho\b",
    r"\bporra\b",
    r"\bcacete\b",
    r"\bbuceta\b",
    r"\bmerda\b",

    r"\bot[aá]rio\b",
    r"\bot[aá]ria\b",
    r"\bidiota\b",
    r"\bimbecil\b",
    r"\bin[uú]til\b",
    r"\bbabaca\b",
    r"\btrouxa\b",
    r"\bpalha[cç]o\b",
    r"\bburro\b",
    r"\bburra\b",
    r"\banimal\b",
    r"\bescr[oó]to\b",
    r"\bnojento\b",
    r"\bnojenta\b",
    r"\bcanalha\b",
    r"\bcretino\b",
    r"\bcretina\b",
    r"\bdesgra[cç]ad[oa]\b",
    r"\bmaldit[oa]\b",
    r"\bmiser[aá]vel\b",

    r"seu\s+merda",
    r"seu\s+lixo",
    r"seu\s+idiota",
    r"seu\s+imbecil",
    r"seu\s+ot[aá]rio",

    r"\bmerda\s+desgra[cç]ad[oa]\b",
    r"cala\s+a\s+boca",

    r"\bf0da-se\b",
    r"\bf0d4-se\b",
    r"\bc4r4lho\b",
    r"\bp0rr4\b",
    r"\bvsf\b",
    r"\bvtnc\b",
    r"\btnc\b",
    r"\bpqp\b",
]


# ============================================================
# DISCRIMINAÇÃO
# ============================================================

PADROES_DISCRIMINACAO = [
    r"\bracista\b",
    r"\bracismo\b",
    r"\bhomofob",
    r"\btransfob",
    r"\bxenofob",
    r"\bnazista\b",
]


# ============================================================
# CHEATS / EXPLOITS
# ============================================================

PADROES_CHEATS = [
    r"\bexploit\b",
    r"\bcheat\b",
    r"\bhack\b",
    r"script\s+de\s+hack",
    r"\bexecutor\b",
    r"usar\s+exploit",
    r"usar\s+cheat",
    r"usar\s+hack",
]


# ============================================================
# FALSA IDENTIDADE
# ============================================================

PADROES_IDENTIDADE = [
    r"sou\s+o\s+adm",
    r"eu\s+sou\s+staff",
    r"sou\s+moderador",
    r"sou\s+administrador",
    r"finjo\s+ser\s+staff",
    r"me\s+passar\s+por\s+staff",
]


# ============================================================
# CREDENCIAIS
# ============================================================

PADROES_CREDENCIAIS = [
    r"me\s+manda\s+sua\s+senha",
    r"mande\s+sua\s+senha",
    r"envie\s+sua\s+senha",

    r"me\s+manda\s+seu\s+token",
    r"mande\s+seu\s+token",
    r"envie\s+seu\s+token",

    r"manda\s+seu\s+c[oó]digo",
    r"mande\s+seu\s+c[oó]igo",
]


# ============================================================
# CONTEÚDO SEXUAL
# ============================================================

PADROES_SEXUAL = [
    r"\bporn[oô]\b",
    r"\bpornografia\b",
    r"\bporno\b",
    r"\bnudes?\b",
    r"\bnude\b",
    r"\bsexo\b",
    r"\bsexuais?\b",
    r"\bnsfw\b",
]


# ============================================================
# CONTEÚDO GRÁFICO
# ============================================================

PADROES_GRAFICO = [
    r"\bgore\b",
    r"\bdecapita",
    r"\bdese?mb?rar",
    r"\bcad[aá]ver\b",
    r"\bsangue\s+real\b",
    r"\bviol[eê]ncia\s+gr[aá]fica\b",
]


# ============================================================
# AUXILIARES
# ============================================================

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""

    return re.sub(
        r"\s+",
        " ",
        texto.lower(),
    ).strip()


def contem_padrao(
    texto: str,
    padroes: list[str],
) -> bool:

    return any(
        re.search(
            padrao,
            texto,
            re.I,
        )
        for padrao in padroes
    )


def porcentagem_maiusculas(
    texto: str,
) -> float:

    letras = [
        caractere
        for caractere in texto
        if caractere.isalpha()
    ]

    if not letras:
        return 0.0

    return (
        sum(
            caractere.isupper()
            for caractere in letras
        )
        / len(letras)
    )


# ============================================================
# AUTOMOD
# ============================================================

class AutoMod(commands.Cog):

    def __init__(
        self,
        bot: commands.Bot,
    ):

        self.bot = bot

        self.historico_mensagens = defaultdict(
            lambda: deque(maxlen=30)
        )

        self.ultimas_mensagens = defaultdict(
            lambda: deque(maxlen=20)
        )

        self.cooldowns = {}

        self.regras_cache = {}

        self.regras_cache_timestamp = 0

        self.punicoes_em_andamento = set()

        self.verificar_banimentos.start()

        print(
            "[AUTOMOD] Inicializado | "
            f"Canal de regras: {CANAL_REGRAS_ID}"
        )

    async def cog_load(self):

        print(
            "[AUTOMOD] Cog carregado com sucesso."
        )

    def cog_unload(self):

        self.verificar_banimentos.cancel()

    def em_cooldown(
        self,
        guild_id,
        user_id,
    ):
        """Retorna True enquanto o usuário estiver no cooldown de punição."""

        chave = (
            guild_id,
            user_id,
        )

        ultimo = self.cooldowns.get(chave)

        if ultimo is None:
            return False

        if time.time() - ultimo >= COOLDOWN_PUNICAO:
            self.cooldowns.pop(chave, None)
            return False

        return True

    # ========================================================
    # CARREGAR REGRAS OFICIAIS
    # ========================================================

    async def carregar_regras_oficiais(
        self,
    ):

        agora = time.time()

        if (
            self.regras_cache
            and (
                agora
                - self.regras_cache_timestamp
            )
            < CACHE_REGRAS_SEGUNDOS
        ):
            return self.regras_cache

        canal = self.bot.get_channel(
            CANAL_REGRAS_ID
        )

        if canal is None:

            try:

                canal = (
                    await self.bot.fetch_channel(
                        CANAL_REGRAS_ID
                    )
                )

            except Exception as erro:

                print(
                    "[AUTOMOD][ERRO] "
                    f"Canal de regras inacessível: "
                    f"{erro}"
                )

                return self.regras_cache

        if not isinstance(
            canal,
            discord.TextChannel,
        ):

            return self.regras_cache

        partes = []

        try:

            async for mensagem in canal.history(
                limit=200,
                oldest_first=True,
            ):

                if mensagem.content:
                    partes.append(
                        mensagem.content
                    )

                for embed in mensagem.embeds:

                    if embed.title:
                        partes.append(
                            embed.title
                        )

                    if embed.description:
                        partes.append(
                            embed.description
                        )

                    for field in embed.fields:

                        if field.name:
                            partes.append(
                                field.name
                            )

                        if field.value:
                            partes.append(
                                field.value
                            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                f"Falha ao ler regras: {erro}"
            )

            return self.regras_cache

        texto = "\n".join(
            partes
        ).strip()

        if not texto:
            return self.regras_cache

        padrao = re.compile(
            r"(?:^|\n)\s*"
            r"(?:┃|│|▌|#|\*)*\s*"
            r"(\d{2})"
            r"(?:[.)\-:]\s*|\s+)"
            r"([^\n]+)",
            re.I,
        )

        encontrados = list(
            padrao.finditer(texto)
        )

        secoes = {}

        for indice, match in enumerate(
            encontrados
        ):

            fim = (
                encontrados[indice + 1].start()
                if indice + 1 < len(encontrados)
                else len(texto)
            )

            secoes[
                match.group(1)
            ] = {
                "numero": match.group(1),
                "titulo": match.group(2).strip(),
                "conteudo": texto[
                    match.end():fim
                ].strip(),
            }

        self.regras_cache = secoes

        self.regras_cache_timestamp = agora

        print(
            "[AUTOMOD] Regras oficiais "
            "atualizadas: "
            f"{len(secoes)} seções encontradas."
        )

        return secoes
    # ========================================================
    # DETECÇÕES
    # ========================================================

    def detectar_spam(
        self,
        guild_id,
        user_id,
    ):

        chave = (
            guild_id,
            user_id,
        )

        agora = time.time()

        fila = (
            self.historico_mensagens[
                chave
            ]
        )

        while (
            fila
            and agora - fila[0]
            > JANELA_SPAM
        ):

            fila.popleft()

        return (
            len(fila)
            >= LIMITE_SPAM
        )

    def detectar_repeticao(
        self,
        guild_id,
        user_id,
        texto,
    ):

        chave = (
            guild_id,
            user_id,
        )

        atual = normalizar_texto(
            texto
        )

        if not atual:
            return False

        agora = time.time()

        quantidade = sum(
            item["texto"] == atual
            and (
                agora
                - item["tempo"]
                <= JANELA_REPETICAO
            )
            for item
            in self.ultimas_mensagens[
                chave
            ]
        )

        return (
            quantidade
            >= LIMITE_REPETICAO
        )

    def detectar_divulgacao(
        self,
        texto,
    ):

        if DISCORD_INVITE_REGEX.search(
            texto
        ):
            return True

        if not URL_REGEX.search(
            texto
        ):
            return False

        termos = (
            "entre no servidor",
            "entrem no servidor",
            "meu servidor",
            "nosso servidor",
            "entrem",
            "entre aqui",
            "divulgação",
            "divulgacao",
            "parceria",
            "comunidade",
        )

        return any(
            termo in texto
            for termo in termos
        )

    def detectar_mencao_massa(
        self,
        message,
    ):

        if "@everyone" in message.content:
            return True

        total = (
            len(message.mentions)
            + len(message.role_mentions)
        )

        return (
            total
            >= LIMITE_MENCOES
        )

    # ========================================================
    # ANÁLISE DA INFRAÇÃO
    # ========================================================

    async def analisar_infracao(
        self,
        message,
    ):

        texto = normalizar_texto(
            message.content
        )

        if not texto:
            return None

        regras = (
            await self.carregar_regras_oficiais()
        )

        infracoes = []

        # ----------------------------------------------------
        # NÍVEL 1
        # ----------------------------------------------------

        if self.detectar_spam(
            message.guild.id,
            message.author.id,
        ):

            infracoes.append(
                (
                    1,
                    "Spam/Flood",
                    "02",
                    (
                        "Envio excessivo de "
                        "mensagens em curto período."
                    ),
                )
            )

        if self.detectar_repeticao(
            message.guild.id,
            message.author.id,
            message.content,
        ):

            infracoes.append(
                (
                    1,
                    "Repetição de mensagens",
                    "02",
                    (
                        "Repetição excessiva "
                        "da mesma mensagem."
                    ),
                )
            )

        letras = [
            caractere
            for caractere
            in message.content
            if caractere.isalpha()
        ]

        if (
            len(letras) >= 12
            and porcentagem_maiusculas(
                message.content
            ) >= 0.80
        ):

            infracoes.append(
                (
                    1,
                    "Excesso de letras maiúsculas",
                    "02",
                    (
                        "Uso excessivo de "
                        "letras maiúsculas."
                    ),
                )
            )

        if self.detectar_mencao_massa(
            message
        ):

            infracoes.append(
                (
                    1,
                    "Menções em excesso",
                    "02",
                    "Uso excessivo de menções.",
                )
            )

        # ----------------------------------------------------
        # NÍVEL 2
        # ----------------------------------------------------

        if self.detectar_divulgacao(
            texto
        ):

            infracoes.append(
                (
                    2,
                    "Divulgação não autorizada",
                    "05",
                    (
                        "Identificação de divulgação "
                        "ou convite externo."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_ASSÉDIO,
        ):

            infracoes.append(
                (
                    2,
                    "Desrespeito/Assédio",
                    "01",
                    (
                        "Linguagem ofensiva ou "
                        "direcionada a outro membro."
                    ),
                )
            )

        # ----------------------------------------------------
        # NÍVEL 3
        # ----------------------------------------------------

        if contem_padrao(
            texto,
            PADROES_AMEACA,
        ):

            infracoes.append(
                (
                    3,
                    "Ameaça",
                    "01",
                    "Mensagem contendo ameaça direta.",
                )
            )

        if contem_padrao(
            texto,
            PADROES_INVASAO,
        ):

            infracoes.append(
                (
                    3,
                    "Invasão/Sabotagem",
                    "04",
                    (
                        "Intenção de atacar, derrubar "
                        "ou sabotar servidor/sistema."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_DISCRIMINACAO,
        ):

            infracoes.append(
                (
                    3,
                    "Discriminação",
                    "01",
                    (
                        "Conteúdo potencialmente "
                        "discriminatório."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_CHEATS,
        ):

            infracoes.append(
                (
                    3,
                    "Cheat/Exploit",
                    "08",
                    (
                        "Referência a cheats, exploits "
                        "ou vantagem indevida."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_IDENTIDADE,
        ):

            infracoes.append(
                (
                    3,
                    "Falsa identidade",
                    "04",
                    (
                        "Possível tentativa de se "
                        "passar por Staff ou outro membro."
                    ),
                )
            )

        # ----------------------------------------------------
        # NÍVEL 4
        # ----------------------------------------------------

        if contem_padrao(
            texto,
            PADROES_PHISHING,
        ):

            infracoes.append(
                (
                    4,
                    "Phishing/Golpe",
                    "03",
                    (
                        "Possível tentativa de enganar "
                        "usuários para obter dados ou acesso."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_MALWARE,
        ):

            infracoes.append(
                (
                    4,
                    "Malware/Stealer",
                    "03",
                    (
                        "Referência a malware ou ferramentas "
                        "destinadas ao roubo de dados."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_DOXXING,
        ):

            infracoes.append(
                (
                    4,
                    "Doxxing",
                    "04",
                    (
                        "Possível exposição ou ameaça "
                        "de exposição de dados pessoais."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_CREDENCIAIS,
        ):

            infracoes.append(
                (
                    4,
                    "Solicitação de credenciais",
                    "04",
                    (
                        "Solicitação de senha, token "
                        "ou código de autenticação."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_SEXUAL,
        ):

            infracoes.append(
                (
                    4,
                    "Conteúdo sexual proibido",
                    "03",
                    (
                        "Identificação de possível "
                        "conteúdo sexual ou pornográfico."
                    ),
                )
            )

        if contem_padrao(
            texto,
            PADROES_GRAFICO,
        ):

            infracoes.append(
                (
                    4,
                    "Conteúdo extremamente gráfico",
                    "03",
                    (
                        "Identificação de possível "
                        "conteúdo extremamente gráfico."
                    ),
                )
            )

        # ----------------------------------------------------
        # NÍVEL 5
        # ----------------------------------------------------

        if (
            (
                "invadir" in texto
                or "derrubar" in texto
                or "destruir" in texto
            )
            and any(
                termo in texto
                for termo in (
                    "servidor",
                    "sistema",
                    "bot",
                )
            )
            and any(
                termo in texto
                for termo in (
                    "vou",
                    "vamos",
                    "pretendo",
                    "pretendemos",
                )
            )
        ):

            infracoes.append(
                (
                    5,
                    "Tentativa deliberada de comprometimento",
                    "04",
                    (
                        "Indício textual de intenção "
                        "deliberada de comprometer "
                        "servidor ou sistema."
                    ),
                )
            )

        if not infracoes:
            return None

        nivel_original = max(
            infracoes,
            key=lambda item: item[0],
        )[0]

        nivel, tipo, regra, motivo = max(
            infracoes,
            key=lambda item: item[0],
        )

        # ----------------------------------------------------
        # REINCIDÊNCIA
        # ----------------------------------------------------

        try:

            historico = (
                await historico_punicoes(
                    message.guild.id,
                    message.author.id,
                    limite=50,
                )
            )

            agora = time.time()

            recentes = [
                registro
                for registro in historico
                if isinstance(
                    registro.get(
                        "timestamp"
                    ),
                    (
                        int,
                        float,
                    ),
                )
                and (
                    agora
                    - registro["timestamp"]
                    <= JANELA_REINCIDENCIA
                )
            ]

            aumento = (
                2
                if len(recentes) >= 4
                else 1
                if len(recentes) >= 2
                else 0
            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                "Falha ao calcular reincidência: "
                f"{erro}"
            )

            aumento = 0

        nivel = min(
            5,
            nivel + aumento,
        )

        return {
            "nivel": nivel,
            "nivel_original": nivel_original,
            "reincidencia": aumento,
            "tipo": tipo,
            "regra": regra,
            "regra_titulo": regras.get(
                regra,
                {},
            ).get(
                "titulo",
                f"Seção {regra}",
            ),
            "motivo": motivo,
        }

    # ========================================================
    # HISTÓRICO
    # ========================================================

    async def registrar_historico(
        self,
        message,
        infracao,
    ):

        try:

            tipo = {
                1: "warn",
                2: "mute",
                3: "kick",
                4: "ban",
                5: "ban",
            }.get(
                infracao["nivel"],
                "aviso_automatico",
            )

            await registrar_punicao(
                message.guild.id,
                message.author.id,
                tipo,
                infracao["motivo"],
                None,
            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                "Falha ao registrar punição: "
                f"{erro}"
            )

    # ========================================================
    # AVISO
    # ========================================================

    async def aviso(
        self,
        message,
        infracao,
    ):

        nivel = infracao["nivel"]

        embed = discord.Embed(
            title="⚠️ AutoMod — Infração detectada",
            description=(
                f"**Usuário:** "
                f"{message.author.mention}\n"
                f"**Infração:** "
                f"{infracao['tipo']}\n"
                f"**Nível:** "
                f"{nivel} — "
                f"{NIVEIS[nivel]['nome']}\n"
                f"**Regra:** "
                f"{infracao['regra_titulo']}\n"
                f"**Medida:** "
                f"{NIVEIS[nivel]['punicao']}"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(
                datetime.timezone.utc
            ),
        )

        try:

            await message.channel.send(
                embed=embed,
                delete_after=8,
            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                "Falha ao enviar aviso: "
                f"{erro}"
            )
    # ========================================================
    # PUNIÇÕES
    # ========================================================

    async def aplicar_punicao(
        self,
        message,
        infracao,
    ):

        membro = message.author

        nivel = infracao["nivel"]

        print(
            "[AUTOMOD] INFRAÇÃO DETECTADA | "
            f"Servidor={message.guild.id} | "
            f"Usuário={membro} ({membro.id}) | "
            f"Nível={nivel} "
            f"({NIVEIS[nivel]['nome']}) | "
            f"Tipo={infracao['tipo']} | "
            f"Regra={infracao['regra_titulo']}"
        )

        await self.registrar_historico(
            message,
            infracao,
        )

        try:

            # ------------------------------------------------
            # NÍVEL 1
            # ------------------------------------------------

            if nivel == 1:

                try:
                    await message.delete()

                except discord.HTTPException:
                    pass

                await self.aviso(
                    message,
                    infracao,
                )

                return

            # ------------------------------------------------
            # NÍVEL 2
            # ------------------------------------------------

            if nivel == 2:

                try:
                    await message.delete()

                except discord.HTTPException:
                    pass

                if isinstance(
                    membro,
                    discord.Member,
                ):

                    try:

                        await membro.timeout(
                            datetime.timedelta(
                                minutes=10
                            ),
                            reason=(
                                "AutoMod: "
                                f"{infracao['tipo']}"
                            ),
                        )

                    except (
                        discord.Forbidden,
                        discord.HTTPException,
                    ) as erro:

                        print(
                            "[AUTOMOD][ERRO] "
                            f"Timeout: {erro}"
                        )

                await self.aviso(
                    message,
                    infracao,
                )

                return

            # ------------------------------------------------
            # NÍVEL 3
            # ------------------------------------------------

            if (
                nivel == 3
                and isinstance(
                    membro,
                    discord.Member,
                )
            ):

                try:
                    await message.delete()

                except discord.HTTPException:
                    pass

                try:

                    await membro.kick(
                        reason=(
                            "AutoMod: "
                            f"{infracao['tipo']}"
                        )
                    )

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ) as erro:

                    print(
                        "[AUTOMOD][ERRO] "
                        f"Expulsão: {erro}"
                    )

                return

            # ------------------------------------------------
            # NÍVEL 4 E 5
            # ------------------------------------------------

            if (
                nivel in (4, 5)
                and isinstance(
                    membro,
                    discord.Member,
                )
            ):

                try:

                    await membro.ban(
                        reason=(
                            "AutoMod: "
                            f"{infracao['tipo']}"
                        ),
                        delete_message_days=1,
                    )

                    if nivel == 4:

                        await self.registrar_banimento_temporario(
                            message.guild.id,
                            membro.id,
                            86400,
                        )

                except (
                    discord.Forbidden,
                    discord.HTTPException,
                ) as erro:

                    print(
                        "[AUTOMOD][ERRO] "
                        f"Banimento: {erro}"
                    )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO CRÍTICO] "
                "Falha ao aplicar punição: "
                f"{erro}"
            )

    # ========================================================
    # BANIMENTOS TEMPORÁRIOS
    # ========================================================

    async def carregar_banimentos_temporarios(
        self,
    ):

        try:

            dados = await carregar(
                ARQUIVO_BANIMENTOS_TEMPORARIOS,
                {},
            )

            return (
                dados
                if isinstance(
                    dados,
                    dict,
                )
                else {}
            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                "Falha ao carregar banimentos "
                f"temporários: {erro}"
            )

            return {}

    async def salvar_banimentos_temporarios(
        self,
        dados,
    ):

        try:

            await salvar(
                ARQUIVO_BANIMENTOS_TEMPORARIOS,
                dados,
            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                "Falha ao salvar banimentos "
                f"temporários: {erro}"
            )

    async def registrar_banimento_temporario(
        self,
        guild_id,
        user_id,
        duracao,
    ):

        dados = (
            await self.carregar_banimentos_temporarios()
        )

        dados[
            f"{guild_id}:{user_id}"
        ] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "expira_em": (
                time.time()
                + duracao
            ),
        }

        await self.salvar_banimentos_temporarios(
            dados
        )

    @tasks.loop(
        seconds=30
    )
    async def verificar_banimentos(
        self,
    ):

        await self.bot.wait_until_ready()

        dados = (
            await self.carregar_banimentos_temporarios()
        )

        alterado = False

        agora = time.time()

        for chave, registro in list(
            dados.items()
        ):

            try:

                if (
                    agora
                    < float(
                        registro["expira_em"]
                    )
                ):
                    continue

                guild = self.bot.get_guild(
                    int(
                        registro["guild_id"]
                    )
                )

                if guild:

                    try:

                        await guild.unban(
                            discord.Object(
                                id=int(
                                    registro[
                                        "user_id"
                                    ]
                                )
                            ),
                            reason=(
                                "Fim do banimento "
                                "temporário do AutoMod"
                            ),
                        )

                    except discord.NotFound:
                        pass

                    except (
                        discord.Forbidden,
                        discord.HTTPException,
                    ) as erro:

                        print(
                            "[AUTOMOD][ERRO] "
                            f"Unban: {erro}"
                        )

                del dados[chave]

                alterado = True

            except Exception as erro:

                print(
                    "[AUTOMOD][ERRO] "
                    "Ban temporário: "
                    f"{erro}"
                )

        if alterado:

            await self.salvar_banimentos_temporarios(
                dados
            )

    @verificar_banimentos.before_loop
    async def antes_verificar_banimentos(
        self,
    ):

        await self.bot.wait_until_ready()

    # ========================================================
    # EVENTO PRINCIPAL
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):

        if (
            message.guild is None
            or message.author.bot
            or message.channel.id
            == CANAL_REGRAS_ID
        ):

            return

        membro = message.author

        if isinstance(
            membro,
            discord.Member,
        ):

            if (
                membro.guild_permissions.administrator
                or membro.guild_permissions.manage_guild
                or membro.guild_permissions.manage_messages
            ):

                return

        chave = (
            message.guild.id,
            membro.id,
        )

        agora = time.time()

        self.historico_mensagens[
            chave
        ].append(
            agora
        )

        fila = (
            self.historico_mensagens[
                chave
            ]
        )

        while (
            fila
            and agora - fila[0]
            > JANELA_SPAM
        ):

            fila.popleft()

        texto = normalizar_texto(
            message.content
        )

        if texto:

            self.ultimas_mensagens[
                chave
            ].append(
                {
                    "texto": texto,
                    "tempo": agora,
                }
            )

        recentes = (
            self.ultimas_mensagens[
                chave
            ]
        )

        while (
            recentes
            and agora
            - recentes[0]["tempo"]
            > JANELA_REPETICAO
        ):

            recentes.popleft()

        if (
            self.em_cooldown(
                message.guild.id,
                membro.id,
            )
            or membro.id
            in self.punicoes_em_andamento
        ):

            return

        self.punicoes_em_andamento.add(
            membro.id
        )

        try:

            infracao = (
                await self.analisar_infracao(
                    message
                )
            )

            if infracao is None:
                return

            self.cooldowns[
                (
                    message.guild.id,
                    membro.id,
                )
            ] = time.time()

            await self.aplicar_punicao(
                message,
                infracao,
            )

        except Exception as erro:

            print(
                "[AUTOMOD][ERRO] "
                "Falha durante análise: "
                f"{erro}"
            )

        finally:

            self.punicoes_em_andamento.discard(
                membro.id
            )

    # ========================================================
    # COMANDO — REGRAS
    # ========================================================

    @app_commands.command(
        name="automod-regras",
        description=(
            "Mostra as regras utilizadas "
            "pelo AutoMod."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def automod_regras(
        self,
        interaction: discord.Interaction,
    ):

        regras = (
            await self.carregar_regras_oficiais()
        )

        if not regras:

            await interaction.response.send_message(
                (
                    "Não foi possível carregar "
                    "as regras do canal oficial."
                ),
                ephemeral=True,
            )

            return

        embed = discord.Embed(
            title="⚙️ AutoMod — Regras oficiais",
            description=(
                f"Fonte: <#{CANAL_REGRAS_ID}>\n"
                f"Seções: **{len(regras)}**"
            ),
            color=discord.Color.blurple(),
        )

        for numero, regra in list(
            regras.items()
        )[:25]:

            conteudo = (
                regra["conteudo"]
            )

            if len(conteudo) > 900:

                conteudo = (
                    conteudo[:897]
                    + "..."
                )

            embed.add_field(
                name=(
                    f"{numero} — "
                    f"{regra['titulo']}"
                ),
                value=(
                    conteudo
                    or "Sem conteúdo."
                ),
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # ========================================================
    # COMANDO — ATUALIZAR
    # ========================================================

    @app_commands.command(
        name="automod-atualizar",
        description=(
            "Atualiza as regras utilizadas "
            "pelo AutoMod."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def automod_atualizar(
        self,
        interaction: discord.Interaction,
    ):

        self.regras_cache = {}

        self.regras_cache_timestamp = 0

        regras = (
            await self.carregar_regras_oficiais()
        )

        await interaction.response.send_message(
            (
                "Regras atualizadas.\n"
                f"**Seções:** {len(regras)}\n"
                f"**Canal:** <#{CANAL_REGRAS_ID}>"
            ),
            ephemeral=True,
        )

    # ========================================================
    # COMANDO — STATUS
    # ========================================================

    @app_commands.command(
        name="automod-status",
        description=(
            "Verifica o estado do AutoMod."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def automod_status(
        self,
        interaction: discord.Interaction,
    ):

        regras = (
            await self.carregar_regras_oficiais()
        )

        embed = discord.Embed(
            title="⚙️ AutoMod — Status",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="Sistema",
            value="🟢 Ativo",
            inline=False,
        )

        embed.add_field(
            name="Message Content Intent",
            value=(
                "🟢 Ativado"
                if self.bot.intents.message_content
                else "🔴 Desativado"
            ),
            inline=False,
        )

        embed.add_field(
            name="Canal de regras",
            value=(
                f"<#{CANAL_REGRAS_ID}>"
            ),
            inline=False,
        )

        embed.add_field(
            name="Regras carregadas",
            value=str(
                len(regras)
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


# ============================================================
# SETUP
# ============================================================

async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        AutoMod(bot)
    )

    print(
        "[AUTOMOD] Cog registrado no bot."
    )