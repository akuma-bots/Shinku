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

ARQUIVO_BANIMENTOS_TEMPORARIOS = "automod_banimentos.json"

JANELA_SPAM = 8
LIMITE_SPAM = 6

JANELA_REPETICAO = 20
LIMITE_REPETICAO = 3

LIMITE_MENCOES = 5

COOLDOWN_PUNICAO = 20

JANELA_REINCIDENCIA = 30 * 24 * 60 * 60


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
# PADRÕES
# ============================================================

URL_REGEX = re.compile(
    r"https?://[^\s]+|www\.[^\s]+",
    re.IGNORECASE,
)

DISCORD_INVITE_REGEX = re.compile(
    r"(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)


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
]


PADROES_MALWARE = [
    r"stealer",
    r"\brat\b",
    r"keylogger",
    r"roubar\s+token",
    r"token\s*(?:logger|grabber)",
    r"roubar\s+conta",
    r"invas[aã]o\s+de\s+conta",
    r"hackear\s+conta",
]


PADROES_DOXXING = [
    r"\bdoxx(?:ing)?\b",
    r"expor\s+(?:seu\s+)?endere[cç]o",
    r"expor\s+dados\s+pessoais",
    r"vazar\s+dados",
    r"vazar\s+informa[cç][oõ]es",
]


PADROES_INVASAO = [
    r"invadir\s+o\s+servidor",
    r"derrubar\s+o\s+servidor",
    r"raidar\s+o\s+servidor",
    r"raidear\s+o\s+servidor",
    r"destruir\s+o\s+servidor",
    r"atacar\s+o\s+servidor",
]


PADROES_AMEACA = [
    r"vou\s+te\s+matar",
    r"vou\s+matar\s+voc[eê]",
    r"vou\s+te\s+machucar",
    r"vou\s+atr[aá]s\s+de\s+voc[eê]",
    r"vou\s+acabar\s+com\s+voc[eê]",
]


PADROES_ASSÉDIO = [
    r"vai\s+se\s+foder",
    r"vai\s+tomar\s+no\s+cu",
    r"seu\s+in[uú]til",
    r"seu\s+lixo",
]


PADROES_CHEATS = [
    r"\bexploit\b",
    r"\bcheat\b",
    r"\bhack\b",
    r"script\s+de\s+hack",
    r"\bexecutor\b",
]


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""

    texto = texto.lower()
    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def porcentagem_maiusculas(texto: str) -> float:
    letras = [c for c in texto if c.isalpha()]

    if not letras:
        return 0.0

    maiusculas = sum(1 for c in letras if c.isupper())

    return maiusculas / len(letras)


def contem_padrao(texto: str, padroes: list[str]) -> bool:
    for padrao in padroes:
        try:
            if re.search(padrao, texto, re.IGNORECASE):
                return True
        except re.error:
            continue

    return False


def possui_url(texto: str) -> bool:
    return bool(URL_REGEX.search(texto))


def possui_convite_discord(texto: str) -> bool:
    return bool(DISCORD_INVITE_REGEX.search(texto))


# ============================================================
# COG
# ============================================================

class AutoMod(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Histórico de mensagens por usuário.
        self.historico_mensagens = defaultdict(
            lambda: deque(maxlen=30)
        )

        # Mensagens recentes usadas para detectar repetição.
        self.ultimas_mensagens = defaultdict(
            lambda: deque(maxlen=20)
        )

        # Cooldown de punição.
        self.cooldowns = {}

        # Cache das regras oficiais.
        self.regras_cache = {}

        self.regras_cache_timestamp = 0

        # Evita duas punições simultâneas para a mesma pessoa.
        self.punicoes_em_andamento = set()

        # Inicia o sistema de banimentos temporários.
        self.verificar_banimentos.start()

        print(
            f"[AUTOMOD] Inicializado | "
            f"Canal de regras: {CANAL_REGRAS_ID}"
        )

    async def cog_load(self):
        print(
            "[AUTOMOD] Cog carregado com sucesso."
        )

    def cog_unload(self):
        self.verificar_banimentos.cancel()

    # ========================================================
    # REGRAS OFICIAIS
    # ========================================================

    async def carregar_regras_oficiais(self):
        agora = time.time()

        if (
            self.regras_cache
            and agora - self.regras_cache_timestamp
            < CACHE_REGRAS_SEGUNDOS
        ):
            return self.regras_cache

        canal = self.bot.get_channel(CANAL_REGRAS_ID)

        if canal is None:
            try:
                canal = await self.bot.fetch_channel(
                    CANAL_REGRAS_ID
                )
            except Exception as erro:
                print(
                    f"[AUTOMOD][ERRO] "
                    f"Não foi possível acessar o canal de regras "
                    f"{CANAL_REGRAS_ID}: {erro}"
                )
                return self.regras_cache

        if not isinstance(canal, discord.TextChannel):
            print(
                "[AUTOMOD][ERRO] "
                "O canal configurado não é um canal de texto."
            )
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
                        partes.append(embed.title)

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
                f"[AUTOMOD][ERRO] "
                f"Falha ao ler regras oficiais: {erro}"
            )
            return self.regras_cache

        texto = "\n".join(partes).strip()

        if not texto:
            print(
                "[AUTOMOD][AVISO] "
                "O canal oficial de regras está vazio "
                "ou não possui conteúdo legível."
            )
            return self.regras_cache

        # Aceita:
        # 01 CONDUTA
        # 01. CONDUTA
        # 01 - CONDUTA
        # 01 — CONDUTA
        # 01: CONDUTA
        padrao_secao = re.compile(
            r"(?:^|\n)"
            r"\s*(?:┃|│|▌|#|\*)*\s*"
            r"(\d{2})"
            r"(?:[.)\-:]\s*|\s+)"
            r"([^\n]+)",
            re.IGNORECASE,
        )

        encontrados = list(
            padrao_secao.finditer(texto)
        )

        secoes = {}

        if encontrados:
            for indice, match in enumerate(encontrados):
                numero = match.group(1)
                titulo = match.group(2).strip()

                inicio = match.end()

                if indice + 1 < len(encontrados):
                    fim = encontrados[indice + 1].start()
                else:
                    fim = len(texto)

                conteudo = texto[inicio:fim].strip()

                secoes[numero] = {
                    "numero": numero,
                    "titulo": titulo,
                    "conteudo": conteudo,
                }

        self.regras_cache = secoes
        self.regras_cache_timestamp = agora

        print(
            f"[AUTOMOD] Regras oficiais atualizadas: "
            f"{len(secoes)} seções encontradas."
        )

        return self.regras_cache

    # ========================================================
    # DETECÇÕES
    # ========================================================

    def detectar_spam(
        self,
        guild_id: int,
        user_id: int,
    ) -> bool:

        chave = (guild_id, user_id)
        agora = time.time()

        fila = self.historico_mensagens[chave]

        while fila and agora - fila[0] > JANELA_SPAM:
            fila.popleft()

        return len(fila) >= LIMITE_SPAM

    def detectar_repeticao(
        self,
        guild_id: int,
        user_id: int,
        texto: str,
    ) -> bool:

        chave = (guild_id, user_id)

        atual = normalizar_texto(texto)

        if not atual:
            return False

        agora = time.time()

        mensagens = self.ultimas_mensagens[chave]

        recentes = [
            item
            for item in mensagens
            if agora - item["tempo"]
            <= JANELA_REPETICAO
        ]

        quantidade = sum(
            1
            for item in recentes
            if item["texto"] == atual
        )

        return quantidade >= LIMITE_REPETICAO

    def detectar_caps_spam(
        self,
        texto: str,
    ) -> bool:

        letras = [
            c for c in texto
            if c.isalpha()
        ]

        if len(letras) < 12:
            return False

        return porcentagem_maiusculas(texto) >= 0.80

    def detectar_mencao_massa(
        self,
        message: discord.Message,
    ) -> bool:

        if "@everyone" in message.content:
            return True

        total = (
            len(message.mentions)
            + len(message.role_mentions)
        )

        return total >= LIMITE_MENCOES

    def detectar_divulgacao(
        self,
        texto: str,
    ) -> bool:

        if possui_convite_discord(texto):
            return True

        if not possui_url(texto):
            return False

        termos = [
            "entre no servidor",
            "entrem no servidor",
            "meu servidor",
            "nosso servidor",
            "entrem",
            "entre aqui",
            "divulgação",
            "divulgaçao",
            "parceria",
            "comunidade",
        ]

        return any(
            termo in texto.lower()
            for termo in termos
        )

    def detectar_phishing(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_PHISHING,
        )

    def detectar_malware(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_MALWARE,
        )

    def detectar_doxxing(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_DOXXING,
        )

    def detectar_invasao(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_INVASAO,
        )

    def detectar_ameaca(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_AMEACA,
        )

    def detectar_assedio(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_ASSÉDIO,
        )

    def detectar_cheat(
        self,
        texto: str,
    ) -> bool:

        return contem_padrao(
            texto,
            PADROES_CHEATS,
        )
    # ========================================================
    # ANÁLISE DA INFRAÇÃO
    # ========================================================

    async def analisar_infracao(
        self,
        message: discord.Message,
    ):

        texto = normalizar_texto(
            message.content
        )

        if not texto:
            return None

        # Tenta atualizar/carregar as regras.
        # A detecção NÃO depende de o canal de regras
        # estar acessível.
        try:
            regras = await self.carregar_regras_oficiais()
        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO] "
                f"Falha ao carregar regras durante análise: {erro}"
            )
            regras = {}

        infracoes = []

        # ----------------------------------------------------
        # NÍVEL 1 — NORMAL
        # ----------------------------------------------------

        if self.detectar_spam(
            message.guild.id,
            message.author.id,
        ):
            infracoes.append({
                "nivel": 1,
                "tipo": "Spam/Flood",
                "regra": "01",
                "motivo": (
                    "Envio excessivo de mensagens "
                    "em curto período."
                ),
            })

        if self.detectar_repeticao(
            message.guild.id,
            message.author.id,
            message.content,
        ):
            infracoes.append({
                "nivel": 1,
                "tipo": "Repetição de mensagens",
                "regra": "02",
                "motivo": (
                    "Repetição excessiva da mesma mensagem."
                ),
            })

        if self.detectar_caps_spam(
            message.content
        ):
            infracoes.append({
                "nivel": 1,
                "tipo": "Excesso de letras maiúsculas",
                "regra": "02",
                "motivo": (
                    "Uso excessivo de letras maiúsculas."
                ),
            })

        if self.detectar_mencao_massa(
            message
        ):
            infracoes.append({
                "nivel": 1,
                "tipo": "Menções em excesso",
                "regra": "02",
                "motivo": (
                    "Uso excessivo de menções."
                ),
            })

        # ----------------------------------------------------
        # NÍVEL 2 — MÉDIO
        # ----------------------------------------------------

        if self.detectar_divulgacao(
            texto
        ):
            infracoes.append({
                "nivel": 2,
                "tipo": "Divulgação não autorizada",
                "regra": "05",
                "motivo": (
                    "Identificação de divulgação "
                    "ou convite externo."
                ),
            })

        if self.detectar_assedio(
            texto
        ):
            infracoes.append({
                "nivel": 2,
                "tipo": "Desrespeito/Assédio",
                "regra": "01",
                "motivo": (
                    "Linguagem potencialmente ofensiva "
                    "ou direcionada a outro membro."
                ),
            })

        # ----------------------------------------------------
        # NÍVEL 3 — GRAVE
        # ----------------------------------------------------

        if self.detectar_ameaca(
            texto
        ):
            infracoes.append({
                "nivel": 3,
                "tipo": "Ameaça",
                "regra": "01",
                "motivo": (
                    "Mensagem contendo ameaça direta."
                ),
            })

        if self.detectar_invasao(
            texto
        ):
            infracoes.append({
                "nivel": 3,
                "tipo": "Ameaça de invasão/sabotagem",
                "regra": "04",
                "motivo": (
                    "Intenção declarada de atacar, "
                    "derrubar ou sabotar o servidor."
                ),
            })

        # ----------------------------------------------------
        # NÍVEL 4 — MUITO GRAVE
        # ----------------------------------------------------

        if self.detectar_phishing(
            texto
        ):
            infracoes.append({
                "nivel": 4,
                "tipo": "Phishing",
                "regra": "04",
                "motivo": (
                    "Possível tentativa de enganar "
                    "usuários para obter acesso ou dados."
                ),
            })

        if self.detectar_malware(
            texto
        ):
            infracoes.append({
                "nivel": 4,
                "tipo": "Malware/Stealer",
                "regra": "04",
                "motivo": (
                    "Referência a ferramentas ou métodos "
                    "destinados a roubar contas, tokens ou dados."
                ),
            })

        if self.detectar_doxxing(
            texto
        ):
            infracoes.append({
                "nivel": 4,
                "tipo": "Doxxing",
                "regra": "04",
                "motivo": (
                    "Possível exposição ou ameaça de exposição "
                    "de dados pessoais."
                ),
            })

        # ----------------------------------------------------
        # NÍVEL 5 — CRÍTICO
        # ----------------------------------------------------

        # Aqui deixamos a classificação crítica restrita.
        # Não basta aparecer uma palavra isolada.
        texto_critico = (
            ("invadir" in texto or "derrubar" in texto)
            and (
                "servidor" in texto
                or "sistema" in texto
                or "bot" in texto
            )
            and (
                "vou" in texto
                or "vamos" in texto
                or "pretendo" in texto
                or "pretendemos" in texto
            )
        )

        if texto_critico:
            infracoes.append({
                "nivel": 5,
                "tipo": "Tentativa deliberada de comprometimento",
                "regra": "04",
                "motivo": (
                    "Indício textual de intenção deliberada "
                    "de comprometer servidor ou sistema."
                ),
            })

        if not infracoes:
            return None

        # A maior gravidade prevalece.
        infracao = max(
            infracoes,
            key=lambda item: item["nivel"],
        )

        # ----------------------------------------------------
        # REINCIDÊNCIA
        # ----------------------------------------------------

        nivel_original = infracao["nivel"]

        try:
            aumento = await self.calcular_nivel_reincidencia(
                message.author.id,
                infracao["tipo"],
            )
        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO] "
                f"Falha ao calcular reincidência: {erro}"
            )
            aumento = 0

        infracao["nivel_original"] = nivel_original

        infracao["nivel"] = min(
            5,
            nivel_original + aumento,
        )

        infracao["reincidencia"] = aumento

        # ----------------------------------------------------
        # REGRA OFICIAL ASSOCIADA
        # ----------------------------------------------------

        numero_regra = infracao.get("regra")

        if numero_regra:
            regra_encontrada = regras.get(
                numero_regra
            )

            if regra_encontrada:
                infracao["regra_titulo"] = (
                    regra_encontrada["titulo"]
                )
            else:
                infracao["regra_titulo"] = (
                    f"Seção {numero_regra}"
                )
        else:
            infracao["regra_titulo"] = (
                "Regras oficiais"
            )

        return infracao

    # ========================================================
    # REINCIDÊNCIA
    # ========================================================

    async def calcular_nivel_reincidencia(
        self,
        user_id: int,
        tipo_atual: str,
    ) -> int:

        try:
            historico = historico_punicoes()
        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO] "
                f"Não foi possível acessar histórico: {erro}"
            )
            return 0

        if not historico:
            return 0

        agora = time.time()

        quantidade = 0

        for registro in historico:

            if str(
                registro.get("usuario_id")
            ) != str(user_id):
                continue

            data = registro.get("data")

            if data is None:
                data = registro.get(
                    "timestamp"
                )

            if data is None:
                continue

            timestamp = None

            try:
                if isinstance(data, (int, float)):
                    timestamp = float(data)

                elif isinstance(data, str):
                    try:
                        timestamp = float(data)
                    except ValueError:
                        dt = datetime.datetime.fromisoformat(
                            data.replace(
                                "Z",
                                "+00:00",
                            )
                        )

                        if dt.tzinfo is None:
                            dt = dt.replace(
                                tzinfo=datetime.timezone.utc
                            )

                        timestamp = dt.timestamp()

            except Exception:
                continue

            if timestamp is None:
                continue

            if agora - timestamp > JANELA_REINCIDENCIA:
                continue

            quantidade += 1

        if quantidade >= 4:
            return 2

        if quantidade >= 2:
            return 1

        return 0

    # ========================================================
    # COOLDOWN
    # ========================================================

    def em_cooldown(
        self,
        guild_id: int,
        user_id: int,
    ) -> bool:

        chave = (
            guild_id,
            user_id,
        )

        ultimo = self.cooldowns.get(
            chave
        )

        if ultimo is None:
            return False

        return (
            time.time() - ultimo
            < COOLDOWN_PUNICAO
        )

    def registrar_cooldown(
        self,
        guild_id: int,
        user_id: int,
    ):
        self.cooldowns[
            (guild_id, user_id)
        ] = time.time()

    # ========================================================
    # HISTÓRICO
    # ========================================================

    async def registrar_historico(
        self,
        message: discord.Message,
        infracao: dict,
    ):

        try:
            registrar_punicao(
                usuario_id=message.author.id,
                usuario_nome=str(
                    message.author
                ),
                tipo=infracao["tipo"],
                motivo=infracao["motivo"],
                aplicado_por_id=None,
            )

        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO] "
                f"Falha ao registrar punição: {erro}"
            )

    # ========================================================
    # AVISO
    # ========================================================

    async def enviar_aviso_automod(
        self,
        message: discord.Message,
        infracao: dict,
    ):

        nivel = infracao["nivel"]

        dados_nivel = NIVEIS.get(
            nivel,
            NIVEIS[1],
        )

        regra = infracao.get(
            "regra_titulo",
            "Regras oficiais",
        )

        embed = discord.Embed(
            title="⚠️ Moderação automática",
            description=(
                f"{message.author.mention}, sua mensagem "
                f"foi identificada pelo sistema automático.\n\n"
                f"**Infração:** {infracao['tipo']}\n"
                f"**Nível:** {nivel} — "
                f"{dados_nivel['nome']}\n"
                f"**Regra:** {regra}\n"
                f"**Medida:** {dados_nivel['punicao']}"
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
                f"[AUTOMOD][ERRO] "
                f"Não foi possível enviar aviso: {erro}"
            )
    # ========================================================
    # APLICAÇÃO DA PUNIÇÃO
    # ========================================================

    async def aplicar_punicao(
        self,
        message: discord.Message,
        infracao: dict,
    ):

        membro = message.author
        nivel = infracao["nivel"]

        print(
            f"[AUTOMOD] INFRAÇÃO DETECTADA | "
            f"Servidor={message.guild.id} | "
            f"Usuário={membro} ({membro.id}) | "
            f"Nível={nivel} "
            f"({NIVEIS[nivel]['nome']}) | "
            f"Tipo={infracao['tipo']} | "
            f"Regra={infracao.get('regra_titulo', 'N/A')}"
        )

        await self.registrar_historico(
            message,
            infracao,
        )

        try:
            # ================================================
            # NÍVEL 1 — ADVERTÊNCIA
            # ================================================

            if nivel == 1:

                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                await self.enviar_aviso_automod(
                    message,
                    infracao,
                )

                return

            # ================================================
            # NÍVEL 2 — SILENCIAMENTO
            # ================================================

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
                        duracao = datetime.timedelta(
                            minutes=10
                        )

                        await membro.timeout(
                            duracao,
                            reason=(
                                f"AutoMod: "
                                f"{infracao['tipo']}"
                            ),
                        )

                    except discord.Forbidden:
                        print(
                            "[AUTOMOD][ERRO] "
                            "Não tenho permissão para aplicar timeout."
                        )

                    except discord.HTTPException as erro:
                        print(
                            f"[AUTOMOD][ERRO] "
                            f"Falha no timeout: {erro}"
                        )

                await self.enviar_aviso_automod(
                    message,
                    infracao,
                )

                return

            # ================================================
            # NÍVEL 3 — EXPULSÃO
            # ================================================

            if nivel == 3:

                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                if isinstance(
                    membro,
                    discord.Member,
                ):
                    try:
                        await membro.kick(
                            reason=(
                                f"AutoMod: "
                                f"{infracao['tipo']}"
                            )
                        )

                    except discord.Forbidden:
                        print(
                            "[AUTOMOD][ERRO] "
                            "Não tenho permissão para expulsar "
                            f"{membro}."
                        )

                    except discord.HTTPException as erro:
                        print(
                            f"[AUTOMOD][ERRO] "
                            f"Falha ao expulsar: {erro}"
                        )

                return

            # ================================================
            # NÍVEL 4 — BANIMENTO TEMPORÁRIO
            # ================================================

            if nivel == 4:

                if isinstance(
                    membro,
                    discord.Member,
                ):
                    try:
                        await membro.ban(
                            reason=(
                                f"AutoMod: "
                                f"{infracao['tipo']}"
                            ),
                            delete_message_days=1,
                        )

                        self.registrar_banimento_temporario(
                            message.guild.id,
                            membro.id,
                            24 * 60 * 60,
                        )

                    except discord.Forbidden:
                        print(
                            "[AUTOMOD][ERRO] "
                            "Não tenho permissão para banir "
                            f"{membro}."
                        )

                    except discord.HTTPException as erro:
                        print(
                            f"[AUTOMOD][ERRO] "
                            f"Falha no banimento temporário: "
                            f"{erro}"
                        )

                return

            # ================================================
            # NÍVEL 5 — BANIMENTO PERMANENTE
            # ================================================

            if nivel == 5:

                if isinstance(
                    membro,
                    discord.Member,
                ):
                    try:
                        await membro.ban(
                            reason=(
                                f"AutoMod: "
                                f"{infracao['tipo']}"
                            ),
                            delete_message_days=1,
                        )

                    except discord.Forbidden:
                        print(
                            "[AUTOMOD][ERRO] "
                            "Não tenho permissão para banir "
                            f"{membro}."
                        )

                    except discord.HTTPException as erro:
                        print(
                            f"[AUTOMOD][ERRO] "
                            f"Falha no banimento permanente: "
                            f"{erro}"
                        )

                return

        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO CRÍTICO] "
                f"Falha ao aplicar punição: {erro}"
            )

            try:
                await self.enviar_aviso_automod(
                    message,
                    infracao,
                )
            except Exception as erro_aviso:
                print(
                    f"[AUTOMOD][ERRO] "
                    f"Falha no aviso de fallback: "
                    f"{erro_aviso}"
                )

    # ========================================================
    # BANIMENTOS TEMPORÁRIOS
    # ========================================================

    def carregar_banimentos_temporarios(self):
        try:
            dados = carregar(
                ARQUIVO_BANIMENTOS_TEMPORARIOS
            )

            if not isinstance(dados, dict):
                return {}

            return dados

        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO] "
                f"Falha ao carregar banimentos temporários: "
                f"{erro}"
            )
            return {}

    def salvar_banimentos_temporarios(
        self,
        dados,
    ):
        try:
            salvar(
                ARQUIVO_BANIMENTOS_TEMPORARIOS,
                dados,
            )

        except Exception as erro:
            print(
                f"[AUTOMOD][ERRO] "
                f"Falha ao salvar banimentos temporários: "
                f"{erro}"
            )

    def registrar_banimento_temporario(
        self,
        guild_id: int,
        user_id: int,
        duracao: int,
    ):

        dados = (
            self.carregar_banimentos_temporarios()
        )

        chave = f"{guild_id}:{user_id}"

        dados[chave] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "expira_em": time.time() + duracao,
        }

        self.salvar_banimentos_temporarios(
            dados
        )

    @tasks.loop(seconds=30)
    async def verificar_banimentos(self):

        await self.bot.wait_until_ready()

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
                expira_em = float(
                    registro["expira_em"]
                )

                if agora < expira_em:
                    continue

                guild_id = int(
                    registro["guild_id"]
                )

                user_id = int(
                    registro["user_id"]
                )

                guild = self.bot.get_guild(
                    guild_id
                )

                if guild is not None:
                    try:
                        await guild.unban(
                            discord.Object(
                                id=user_id
                            ),
                            reason=(
                                "Fim do banimento "
                                "temporário do AutoMod"
                            ),
                        )

                    except discord.NotFound:
                        pass

                    except discord.Forbidden:
                        print(
                            "[AUTOMOD][ERRO] "
                            f"Sem permissão para remover "
                            f"ban de {user_id}."
                        )

                    except discord.HTTPException as erro:
                        print(
                            f"[AUTOMOD][ERRO] "
                            f"Falha ao remover ban temporário: "
                            f"{erro}"
                        )

                del dados[chave]
                alterado = True

            except Exception as erro:
                print(
                    f"[AUTOMOD][ERRO] "
                    f"Falha ao processar banimento temporário: "
                    f"{erro}"
                )

        if alterado:
            self.salvar_banimentos_temporarios(
                dados
            )

    @verificar_banimentos.before_loop
    async def antes_verificar_banimentos(self):
        await self.bot.wait_until_ready()

    # ========================================================
    # EVENTO PRINCIPAL
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):

        # DMs não entram no AutoMod.
        if message.guild is None:
            return

        # Bots não são analisados.
        if message.author.bot:
            return

        # O canal oficial de regras não é analisado.
        if message.channel.id == CANAL_REGRAS_ID:
            return

        membro = message.author

        # Administradores e membros com permissões
        # de gerenciamento ficam fora do AutoMod.
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

        # Guarda a mensagem para spam.
        self.historico_mensagens[chave].append(
            agora
        )

        # Remove mensagens antigas.
        fila = self.historico_mensagens[chave]

        while fila and (
            agora - fila[0] > JANELA_SPAM
        ):
            fila.popleft()

        # Guarda texto para repetição.
        texto_normalizado = normalizar_texto(
            message.content
        )

        if texto_normalizado:
            self.ultimas_mensagens[chave].append({
                "texto": texto_normalizado,
                "tempo": agora,
            })

        # Limpa mensagens antigas.
        recentes = self.ultimas_mensagens[chave]

        while recentes and (
            agora - recentes[0]["tempo"]
            > JANELA_REPETICAO
        ):
            recentes.popleft()

        # Evita punições duplicadas.
        if self.em_cooldown(
            message.guild.id,
            membro.id,
        ):
            return

        if membro.id in self.punicoes_em_andamento:
            return

        # ----------------------------------------------------
        # ANÁLISE
        # ----------------------------------------------------

        self.punicoes_em_andamento.add(
            membro.id
        )

        try:

            try:
                infracao = (
                    await self.analisar_infracao(
                        message
                    )
                )

            except Exception as erro:
                print(
                    f"[AUTOMOD][ERRO] "
                    f"Falha durante análise da mensagem "
                    f"de {membro} ({membro.id}): "
                    f"{erro}"
                )
                return

            if infracao is None:
                return

            self.registrar_cooldown(
                message.guild.id,
                membro.id,
            )

            await self.aplicar_punicao(
                message,
                infracao,
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
            "Mostra as regras que o AutoMod está utilizando."
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
                "Não foi possível carregar as regras "
                "do canal oficial.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="⚙️ AutoMod — Regras oficiais",
            description=(
                f"Fonte: <#{CANAL_REGRAS_ID}>\n"
                f"Seções carregadas: **{len(regras)}**"
            ),
            color=discord.Color.blurple(),
        )

        for numero, regra in list(
            regras.items()
        )[:25]:

            conteudo = regra["conteudo"]

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
                value=conteudo or "Sem conteúdo.",
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
            "Atualiza manualmente as regras utilizadas "
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
                "Regras do AutoMod atualizadas.\n"
                f"**Seções encontradas:** {len(regras)}\n"
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
            "Verifica o estado do sistema de AutoMod."
        ),
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def automod_status(
        self,
        interaction: discord.Interaction,
    ):

        message_content = getattr(
            self.bot.intents,
            "message_content",
            False,
        )

        canal = self.bot.get_channel(
            CANAL_REGRAS_ID
        )

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
                if message_content
                else "🔴 Desativado"
            ),
            inline=False,
        )

        embed.add_field(
            name="Canal de regras",
            value=(
                f"🟢 <#{CANAL_REGRAS_ID}>"
                if canal
                else "🔴 Canal não encontrado"
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

        embed.add_field(
            name="Spam",
            value=(
                f"{LIMITE_SPAM} mensagens/"
                f"{JANELA_SPAM}s"
            ),
            inline=True,
        )

        embed.add_field(
            name="Repetição",
            value=(
                f"{LIMITE_REPETICAO} vezes/"
                f"{JANELA_REPETICAO}s"
            ),
            inline=True,
        )

        embed.add_field(
            name="Menções",
            value=f"{LIMITE_MENCOES}+",
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


# ============================================================
# SETUP
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(
        AutoMod(bot)
    )

    print(
        "[AUTOMOD] Cog registrado no bot."
    )