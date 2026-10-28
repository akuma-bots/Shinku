import asyncio
import datetime
import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.punicoes import historico_punicoes, registrar_punicao
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config


CANAL_REGRAS_ID = 1563995880833421508
CANAL_INFRACOES_ID = 1545838433229082655
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
    r"\bcu\b",
    r"\bpinto\b",
    r"\bpenis\b",
    r"\bfdpt\b",
    r"\bfilh[oa]s?\s+da\s+puta\b",
    r"\bmerd[a4]\b",
    r"\bidiot[a4]\b",
    r"\bbitch\b",
    r"\basshole\b",
    r"\bshit\b",
    r"\bfuck(?:er|ing)?\b",
    r"\bmotherfucker\b",
    r"\bson\s+of\s+a\s+bitch\b",
    r"\bbastard\b",
    r"\bdamn\b",
    r"\bkurwa\b",
    r"\bchuj\b",
    r"\bpierd\w*\b",
    r"\bput[a4]\b",
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
# DADOS PESSOAIS E ARQUIVOS POTENCIALMENTE PERIGOSOS
# ============================================================

PADROES_DADOS_PESSOAIS = [
    # CPF em formato comum; não tenta validar o dígito verificador.
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
    # Endereço IPv4 público/privado em formato textual.
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    # Telefones brasileiros com DDD.
    r"(?<!\d)(?:\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-\s]?\d{4}(?!\d)",
]

EXTENSOES_PERIGOSAS = (
    ".exe", ".scr", ".bat", ".cmd", ".ps1", ".msi",
    ".dll", ".com", ".jar", ".apk", ".vbs", ".hta",
    ".reg", ".pif", ".iso",
)

PADROES_LINK_SUSPEITO = [
    r"discord(?:-)?nitro\.[a-z]{2,}",
    r"steamcommun[i1]ty\.",
    r"disc[o0]rdapp\.",
    r"free[-_]?nitro",
    r"nitro[-_]?gift",
    r"login.{0,20}(?:discord|roblox|steam)",
    r"(?:discord|roblox|steam).{0,20}verify.{0,10}account",
]


# ============================================================
# AUXILIARES
# ============================================================

def normalizar_texto(texto: str) -> str:
    """Normaliza texto para detectar ofensas com acentos e separadores alterados."""
    if not texto:
        return ""

    import unicodedata

    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    # Reduz separadores repetidos entre letras: f.d.p, f-d-p, f d p.
    texto = re.sub(r"(?<=\w)[._*~|\-]+(?=\w)", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


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



def membro_pode_moderar(membro, canal=None) -> bool:
    """Fail-safe: isenta liderança/administração antes de qualquer análise ou ação.

    Permissões efetivas e cargos confiáveis são tratados como proteção. A
    normalização evita falhas por acentos, caixa, separadores ou caracteres
    decorativos em nomes de cargos.
    """
    import unicodedata

    if not isinstance(membro, discord.Member):
        return False

    guild = membro.guild
    if membro.id == guild.owner_id:
        return True

    def normalizar_nome(valor: str) -> str:
        valor = unicodedata.normalize("NFKD", valor or "")
        valor = "".join(c for c in valor if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]+", "", valor.casefold())

    nomes_protegidos = (
        "admin", "administr", "staff", "moder", "octogono",
        "lider", "diretor", "gerencia", "suporte", "equipe",
    )
    for cargo in membro.roles:
        nome = normalizar_nome(cargo.name)
        if nome and any(fragmento in nome for fragmento in nomes_protegidos):
            return True
        # Um cargo com permissão de administrador é sempre isento,
        # mesmo que seu nome não indique função administrativa.
        if cargo.permissions.administrator:
            return True

    permissoes = membro.guild_permissions
    flags_protegidas = (
        "administrator", "manage_guild", "manage_messages",
        "manage_channels", "manage_roles", "manage_webhooks",
        "view_audit_log", "kick_members", "ban_members",
        "moderate_members", "manage_threads",
    )
    if any(bool(getattr(permissoes, flag, False)) for flag in flags_protegidas):
        return True

    if canal is not None:
        try:
            efetivas = canal.permissions_for(membro)
        except (AttributeError, TypeError, discord.HTTPException):
            # Não concluir que a pessoa é comum se a validação falhar.
            # Em caso de erro, bloquear o AutoMod para este membro.
            return True
        if any(bool(getattr(efetivas, flag, False)) for flag in flags_protegidas):
            return True

    return False


class ModalMotivoDecisao(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, nivel: int, guild_id: int, channel_id: int, message_id: int, alvo_id: int):
        super().__init__(title="Justificar decisão da moderação", timeout=300)
        self.bot = bot
        self.nivel = nivel
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.alvo_id = alvo_id
        self.motivo = discord.ui.TextInput(
            label="Motivo da decisão",
            placeholder="Descreva por que a punição será aplicada ou dispensada...",
            min_length=5,
            max_length=700,
            required=True,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        if not membro_pode_moderar(interaction.user):
            await interaction.response.send_message("Você não tem permissão para decidir sobre esta infração.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Confirme a decisão abaixo. A ação só será aplicada após a confirmação.",
            view=ConfirmarDecisaoView(
                self.bot, self.guild_id, self.channel_id, self.message_id,
                self.alvo_id, self.nivel, str(self.motivo.value).strip(),
            ),
            ephemeral=True,
        )


class ConfirmarDecisaoView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, channel_id: int, message_id: int, alvo_id: int, nivel: int, motivo: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id
        self.alvo_id = alvo_id
        self.nivel = nivel
        self.motivo = motivo

    @discord.ui.button(label="Confirmar decisão", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not membro_pode_moderar(interaction.user):
            await interaction.response.send_message("Você não tem permissão para confirmar esta decisão.", ephemeral=True)
            return
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            await interaction.response.send_message("Servidor não encontrado.", ephemeral=True)
            return
        canal = guild.get_channel(self.channel_id)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(self.channel_id)
            except discord.HTTPException:
                canal = None
        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message("Canal da infração não encontrado.", ephemeral=True)
            return
        try:
            mensagem = await canal.fetch_message(self.message_id)
        except discord.HTTPException:
            await interaction.response.send_message("O registro da infração não está mais acessível.", ephemeral=True)
            return
        if not mensagem.embeds:
            await interaction.response.send_message("O registro não contém os dados da infração.", ephemeral=True)
            return
        embed = mensagem.embeds[0]
        if any(field.name == "Decisão da moderação" for field in embed.fields):
            await interaction.response.send_message("Esta infração já foi analisada pela moderação.", ephemeral=True)
            return
        cog = self.bot.get_cog("AutoMod")
        if cog is None:
            await interaction.response.send_message("O AutoMod não está disponível.", ephemeral=True)
            return
        chave_decisao = (self.guild_id, self.message_id)
        if chave_decisao in cog.decisoes_em_andamento:
            await interaction.response.send_message("Já existe uma decisão em andamento para esta infração.", ephemeral=True)
            return
        cog.decisoes_em_andamento.add(chave_decisao)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if self.nivel == 0:
                await cog.registrar_nao_punir(interaction, self.alvo_id, self.motivo, embed, mensagem)
                resultado = "Decisão registrada: não punir."
            else:
                await cog.punir_por_nivel(interaction, self.alvo_id, self.nivel, self.motivo, embed, mensagem)
                resultado = f"Decisão confirmada: nível {self.nivel} — {NIVEIS[self.nivel]['nome']}."
            for item in self.children:
                item.disabled = True
            try:
                await interaction.message.edit(content=resultado, view=self)
            except (discord.HTTPException, AttributeError):
                pass
            await interaction.delete_original_response()
        except Exception as erro:
            print(f"[AUTOMOD][ERRO] Falha na decisão confirmada: {erro}")
            try:
                await interaction.edit_original_response(
                    content="Não foi possível concluir a decisão. Confira permissões, hierarquia de cargos e configuração.",
                    view=None,
                )
            except discord.HTTPException:
                pass
        finally:
            cog.decisoes_em_andamento.discard(chave_decisao)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Decisão cancelada. Nenhuma punição foi aplicada.", view=self)


class PainelPunicao(discord.ui.View):
    """Painel persistente: toda decisão abre justificativa e confirmação."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def iniciar_decisao(self, interaction: discord.Interaction, nivel: int):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("Este painel só pode ser usado dentro do servidor.", ephemeral=True)
            return
        if not membro_pode_moderar(interaction.user):
            await interaction.response.send_message("Você não tem permissão para decidir sobre esta infração.", ephemeral=True)
            return
        if not interaction.message.embeds:
            await interaction.response.send_message("Não foi possível localizar os dados desta infração.", ephemeral=True)
            return
        embed = interaction.message.embeds[0]
        if any(field.name == "Decisão da moderação" for field in embed.fields):
            await interaction.response.send_message("Esta infração já foi analisada pela moderação.", ephemeral=True)
            return
        alvo_match = re.search(r"\*\*Usuário:\*\*\s*<@!?(\d+)>", embed.description or "")
        if not alvo_match:
            await interaction.response.send_message("Não consegui identificar o infrator neste registro.", ephemeral=True)
            return
        await interaction.response.send_modal(
            ModalMotivoDecisao(
                self.bot, nivel, interaction.guild.id, interaction.channel_id,
                interaction.message.id, int(alvo_match.group(1)),
            )
        )

    @discord.ui.button(label="Nível 1", style=discord.ButtonStyle.secondary, custom_id="nemesis_automod_punir_nivel_1")
    async def nivel_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_decisao(interaction, 1)

    @discord.ui.button(label="Nível 2", style=discord.ButtonStyle.primary, custom_id="nemesis_automod_punir_nivel_2")
    async def nivel_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_decisao(interaction, 2)

    @discord.ui.button(label="Nível 3", style=discord.ButtonStyle.primary, custom_id="nemesis_automod_punir_nivel_3")
    async def nivel_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_decisao(interaction, 3)

    @discord.ui.button(label="Nível 4", style=discord.ButtonStyle.danger, custom_id="nemesis_automod_punir_nivel_4")
    async def nivel_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_decisao(interaction, 4)

    @discord.ui.button(label="Nível 5", style=discord.ButtonStyle.danger, custom_id="nemesis_automod_punir_nivel_5")
    async def nivel_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_decisao(interaction, 5)

    @discord.ui.button(label="Não punir", emoji="✅", style=discord.ButtonStyle.success, custom_id="nemesis_automod_nao_punir", row=1)
    async def nao_punir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_decisao(interaction, 0)


# ============================================================
# AUTOMOD
# ============================================================

class AutoMod(commands.GroupCog, group_name="automod", group_description="Configuração e consulta do AutoMod da NÊMESIS."):

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
        self.decisoes_em_andamento = set()
        self._banimentos_lock = asyncio.Lock()

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

        anexos = list(getattr(message, "attachments", []) or [])
        if not texto and not anexos:
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

        # Arquivos executáveis e formatos frequentemente usados para
        # distribuir malware são bloqueados pela extensão do nome.
        for anexo in anexos:
            nome = str(getattr(anexo, "filename", "") or "").casefold()
            if nome.endswith(EXTENSOES_PERIGOSAS):
                infracoes.append((
                    4,
                    "Arquivo potencialmente perigoso",
                    "03",
                    f"Anexo com extensão de risco: {nome[:100]}",
                ))
                break

        # Detecta tentativas conhecidas de phishing mesmo quando não usam
        # exatamente as frases listadas nos padrões iniciais.
        if contem_padrao(texto, PADROES_LINK_SUSPEITO):
            infracoes.append((
                4,
                "Link suspeito/Phishing",
                "03",
                "A mensagem contém um padrão de link associado a phishing ou fraude.",
            ))

        # Dados pessoais numéricos publicados no chat podem configurar doxxing.
        # A detecção é heurística e a equipe deve considerar o contexto no painel.
        if contem_padrao(texto, PADROES_DADOS_PESSOAIS):
            infracoes.append((
                4,
                "Possível exposição de dados pessoais",
                "04",
                "A mensagem contém um padrão semelhante a CPF, IP ou telefone.",
            ))

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
        medida_exibida = NIVEIS[nivel]["punicao"]
        try:
            config = await get_config(message.guild.id)
            custom = (config.get("automod_niveis") or {}).get(str(nivel), {})
            medida = custom.get("medida")
            duracao = int(custom.get("duracao") or (10 if nivel == 2 else 24 if nivel == 4 else 0))
            nomes_medidas = {
                "warn": "Advertência",
                "timeout": f"Timeout ({duracao} minuto(s))",
                "kick": "Expulsão",
                "ban_temp": f"Banimento temporário ({duracao} hora(s))",
                "ban_permanente": "Banimento permanente",
            }
            if medida in nomes_medidas:
                medida_exibida = nomes_medidas[medida]
        except Exception as erro:
            print(f"[AUTOMOD][CONFIG] Não foi possível ler a medida configurada: {erro}")

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
                f"{medida_exibida}\n"
                f"**Canal da ocorrência:** "
                f"<#{message.channel.id}>\n"
                f"**Mensagem:** "
                f"{discord.utils.escape_markdown(message.content[:700] or '[sem texto]')}"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(
                datetime.timezone.utc
            ),
        )

        try:

            canal = message.guild.get_channel(
                CANAL_INFRACOES_ID
            )

            if canal is None:
                canal = await self.bot.fetch_channel(
                    CANAL_INFRACOES_ID
                )

            if not isinstance(canal, discord.TextChannel):
                print(
                    "[AUTOMOD][ERRO] "
                    f"Canal de infrações inválido: {CANAL_INFRACOES_ID}"
                )
                return

            await canal.send(embed=embed, view=PainelPunicao(self.bot))

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
        message: discord.Message,
        infracao: dict,
    ):
        """Aplica automaticamente a medida configurada para o nível detectado."""
        guild = message.guild
        membro = message.author
        if guild is None:
            return
        if not isinstance(membro, discord.Member):
            membro = guild.get_member(message.author.id)
            if membro is None:
                try:
                    membro = await guild.fetch_member(message.author.id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    return

        # Reconsulta o membro na API imediatamente antes de qualquer ação.
        # Se não for possível confirmar cargos/permissões atuais, a ação é cancelada.
        try:
            membro_atual = await guild.fetch_member(message.author.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "AutoMod cancelado: não foi possível validar o membro antes da ação "
                "(guild=%s, member=%s, message=%s).",
                guild.id, message.author.id, message.id,
            )
            return
        membro = membro_atual

        # Barreira final redundante e explícita: qualquer permissão administrativa
        # ou de moderação concede bypass integral, inclusive permissões efetivas
        # do canal. A mensagem não é apagada e nenhuma punição é aplicada.
        permissoes = membro.guild_permissions
        if (
            membro.id == guild.owner_id
            or permissoes.administrator
            or permissoes.manage_messages
            or permissoes.manage_guild
            or membro_pode_moderar(membro, message.channel)
        ):
            return

        nivel = int(infracao["nivel"])
        config = await get_config(guild.id)
        custom = (config.get("automod_niveis") or {}).get(str(nivel), {})
        medida = custom.get("medida") or {
            1: "warn", 2: "timeout", 3: "kick",
            4: "ban_temp", 5: "ban_permanente",
        }[nivel]
        duracao = int(custom.get("duracao") or (10 if medida == "timeout" else 24 if medida == "ban_temp" else 0))
        motivo = f"AutoMod NÊMESIS | Nível {nivel} — {infracao['tipo']}: {infracao['motivo']}"
        nomes = {
            "warn": "Advertência automática",
            "timeout": f"Timeout por {max(1, duracao)} minuto(s)",
            "kick": "Expulsão automática",
            "ban_temp": f"Banimento temporário por {max(1, duracao)} hora(s)",
            "ban_permanente": "Banimento permanente",
        }
        if medida not in nomes:
            medida = {1: "warn", 2: "timeout", 3: "kick", 4: "ban_temp", 5: "ban_permanente"}[nivel]

        # Última barreira imediatamente antes da exclusão. Não depender apenas
        # da validação feita no início do listener: cargos/permissões podem mudar.
        permissoes_finais = membro.guild_permissions
        if (
            membro.id == guild.owner_id
            or permissoes_finais.administrator
            or permissoes_finais.manage_messages
            or permissoes_finais.manage_guild
            or membro_pode_moderar(membro, message.channel)
        ):
            logger = __import__("logging").getLogger(__name__)
            logger.info(
                "AutoMod ignorou ação por isenção administrativa (guild=%s, member=%s, message=%s).",
                guild.id, membro.id, message.id,
            )
            return

        # Remoção da mensagem primeiro reduz a exposição do conteúdo nocivo.
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        try:
            if medida == "warn":
                tipo_historico = "warn"
            elif medida == "timeout":
                minutos = max(1, min(duracao or 10, 40320))
                await membro.timeout(datetime.timedelta(minutes=minutos), reason=motivo)
                duracao = minutos
                tipo_historico = "mute"
                nomes[medida] = f"Timeout por {minutos} minuto(s)"
            elif medida == "kick":
                await membro.kick(reason=motivo)
                tipo_historico = "kick"
            elif medida == "ban_temp":
                horas = max(1, min(duracao or 24, 8760))
                await guild.ban(membro, reason=motivo, delete_message_seconds=0)
                persistido = await self.registrar_banimento_temporario(
                    guild.id, membro.id, horas * 3600
                )
                if not persistido:
                    # Sem registro de expiração, não deixamos um ban temporário
                    # virar permanente silenciosamente.
                    try:
                        await guild.unban(
                            discord.Object(id=membro.id),
                            reason="Rollback: falha ao persistir expiração do AutoMod",
                        )
                    except discord.NotFound:
                        pass
                    except (discord.Forbidden, discord.HTTPException) as erro_rollback:
                        print(
                            f"[AUTOMOD][CRÍTICO] Falha ao reverter ban temporário de {membro.id}: {erro_rollback}"
                        )
                    await self.aviso_falha_punicao(
                        message,
                        infracao,
                        "O ban temporário não pôde ser salvo no armazenamento. O bot tentou reverter o banimento; confira o log de auditoria.",
                    )
                    return
                duracao = horas
                tipo_historico = "ban"
                nomes[medida] = f"Banimento temporário por {horas} hora(s)"
            else:
                await guild.ban(membro, reason=motivo, delete_message_seconds=0)
                tipo_historico = "ban"
        except (discord.Forbidden, discord.HTTPException) as erro:
            print(f"[AUTOMOD][ERRO] Não foi possível aplicar {medida} em {membro.id}: {erro}")
            await self.aviso_falha_punicao(message, infracao, str(erro))
            return

        await registrar_punicao(guild.id, membro.id, tipo_historico, motivo, None)
        await self.registrar_decisao(
            guild.id, membro.id, "punido", nivel, infracao["motivo"], 0, infracao["tipo"]
        )

        embed = discord.Embed(
            title="🛡️ AutoMod — Punição automática aplicada",
            description=(
                f"**Usuário:** <@{membro.id}> ({membro.id})\n"
                f"**Infração:** {infracao['tipo']}\n"
                f"**Nível:** {nivel} — {NIVEIS[nivel]['nome']}\n"
                f"**Diretriz:** {infracao.get('regra_titulo', 'Regra oficial')}\n"
                f"**Medida aplicada:** {nomes[medida]}\n"
                f"**Canal:** <#{message.channel.id}>\n"
                f"**Motivo:** {discord.utils.escape_markdown(infracao['motivo'][:500])}"
            ),
            color=discord.Color.red() if nivel >= 3 else discord.Color.gold(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        try:
            canal = guild.get_channel(CANAL_INFRACOES_ID) or await self.bot.fetch_channel(CANAL_INFRACOES_ID)
            if isinstance(canal, discord.TextChannel):
                await canal.send(embed=embed)
        except discord.HTTPException as erro:
            print(f"[AUTOMOD][ERRO] Falha ao publicar registro automático: {erro}")

        try:
            detalhe_duracao = (
                f"\nDuração: {duracao} hora(s)." if medida == "ban_temp"
                else f"\nDuração: {duracao} minuto(s)." if medida == "timeout"
                else ""
            )
            await membro.send(
                f"**NÊMESIS — Punição automática**\n"
                f"Infração: {infracao['tipo']}\n"
                f"Nível: {nivel} — {NIVEIS[nivel]['nome']}\n"
                f"Medida: {nomes[medida]}\nMotivo: {infracao['motivo']}{detalhe_duracao}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        auditoria = discord.Embed(
            title="🛡️ Auditoria — AutoMod automático",
            description=(
                f"**Resultado:** Punição aplicada\n**Membro:** <@{membro.id}> ({membro.id})\n"
                f"**Infração:** {infracao['tipo']}\n**Nível:** {nivel}\n"
                f"**Medida:** {nomes[medida]}\n**Responsável:** Sistema AutoMod\n"
                f"**Motivo:** {discord.utils.escape_markdown(infracao['motivo'][:500])}"
            ),
            color=discord.Color.red() if nivel >= 3 else discord.Color.gold(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        await self.enviar_auditoria(guild, auditoria)

    async def aviso_falha_punicao(self, message: discord.Message, infracao: dict, erro: str):
        """Registra uma falha de aplicação para que a equipe possa corrigi-la."""
        embed = discord.Embed(
            title="⚠️ AutoMod — Punição não aplicada",
            description=(
                f"**Usuário:** {message.author.mention}\n"
                f"**Infração:** {infracao.get('tipo', 'Não identificada')}\n"
                f"**Nível:** {infracao.get('nivel', '?')}\n"
                f"**Motivo:** {infracao.get('motivo', 'Não informado')}\n"
                "A ação foi detectada, mas o Discord recusou a punição. "
                "Verifique as permissões e a hierarquia de cargos."
            ),
            color=discord.Color.orange(),
        )
        try:
            canal = message.guild.get_channel(CANAL_INFRACOES_ID) or await self.bot.fetch_channel(CANAL_INFRACOES_ID)
            if isinstance(canal, discord.TextChannel):
                await canal.send(embed=embed)
        except discord.HTTPException:
            pass

    async def enviar_auditoria(self, guild: discord.Guild, embed: discord.Embed):
        try:
            config = await get_config(guild.id)
            canal_id = int(config.get("canal_auditoria_id") or 1545837705609617428)
            canal = guild.get_channel(canal_id)
            if canal is None:
                canal = await self.bot.fetch_channel(canal_id)
            if isinstance(canal, discord.TextChannel):
                await canal.send(embed=embed)
        except Exception as erro:
            print(f"[AUTOMOD][AUDITORIA] Não foi possível enviar log: {erro}")

    async def registrar_decisao(self, guild_id: int, alvo_id: int, tipo: str, nivel: int, motivo: str, moderador_id: int, infracao: str):
        arquivo = "automod_decisoes.json"
        dados = await carregar(arquivo, {})
        lista = dados.setdefault(str(guild_id), [])
        lista.append({
            "guild_id": guild_id, "membro_id": alvo_id, "tipo": tipo,
            "nivel": nivel, "motivo": motivo[:700], "moderador_id": moderador_id,
            "infracao": infracao[:200], "timestamp": time.time(),
        })
        dados[str(guild_id)] = lista[-5000:]
        await salvar(arquivo, dados)

    async def punir_por_nivel(
        self,
        interaction: discord.Interaction,
        alvo_id: int,
        nivel: int,
        motivo: str,
        embed: discord.Embed,
        mensagem: discord.Message,
    ):
        guild = interaction.guild
        if guild is None:
            raise ValueError("Servidor não encontrado.")
        if nivel not in NIVEIS:
            raise ValueError("Nível de punição inválido.")

        config = await get_config(guild.id)
        custom = (config.get("automod_niveis") or {}).get(str(nivel), {})
        medida = custom.get("medida") or {1: "warn", 2: "timeout", 3: "kick", 4: "ban_temp", 5: "ban_permanente"}[nivel]
        duracao = int(custom.get("duracao") or (10 if nivel == 2 else 24 if nivel == 4 else 0))
        alvo = guild.get_member(alvo_id)
        if alvo is None:
            try:
                alvo = await guild.fetch_member(alvo_id)
            except discord.NotFound:
                alvo = None

        infracao_match = re.search(r"\*\*Infração:\*\*\s*([^\n]+)", embed.description or "")
        infracao_nome = infracao_match.group(1).strip() if infracao_match else "Infração AutoMod"
        justificativa = f"NÊMESIS | Nível {nivel} | {motivo}"

        if medida == "warn":
            tipo_historico = "warn"
            medida_texto = "Advertência"
        elif medida == "timeout":
            if not isinstance(alvo, discord.Member):
                raise ValueError("O infrator não está no servidor para receber timeout.")
            duracao = max(1, min(duracao or 10, 40320))
            await alvo.timeout(datetime.timedelta(minutes=duracao), reason=justificativa)
            tipo_historico = "mute"
            medida_texto = f"Timeout por {duracao} minuto(s)"
        elif medida == "kick":
            if not isinstance(alvo, discord.Member):
                raise ValueError("O infrator não está no servidor para ser expulso.")
            await alvo.kick(reason=justificativa)
            tipo_historico = "kick"
            medida_texto = "Expulsão do servidor"
        elif medida == "ban_temp":
            duracao = max(1, min(duracao or 24, 8760))
            await guild.ban(alvo if alvo is not None else discord.Object(id=alvo_id), reason=justificativa, delete_message_seconds=0)
            await self.registrar_banimento_temporario(guild.id, alvo_id, duracao * 3600)
            tipo_historico = "ban"
            medida_texto = f"Banimento temporário de {duracao} hora(s)"
        elif medida == "ban_permanente":
            await guild.ban(alvo if alvo is not None else discord.Object(id=alvo_id), reason=justificativa, delete_message_seconds=0)
            tipo_historico = "ban"
            medida_texto = "Banimento permanente"
        else:
            raise ValueError("A medida configurada para este nível é inválida.")

        await registrar_punicao(guild.id, alvo_id, tipo_historico, motivo, interaction.user.id)
        await self.registrar_decisao(guild.id, alvo_id, "punido", nivel, motivo, interaction.user.id, infracao_nome)

        embed.add_field(
            name="Decisão da moderação",
            value=(
                f"**Resultado:** Punido — {medida_texto}\n"
                f"**Nível escolhido:** {nivel} — {NIVEIS[nivel]['nome']}\n"
                f"**Responsável:** {interaction.user.mention}\n"
                f"**Motivo:** {discord.utils.escape_markdown(motivo[:700])}"
            ),
            inline=False,
        )
        embed.color = discord.Color.red() if nivel >= 3 else discord.Color.gold()
        await mensagem.edit(embed=embed, view=None)

        try:
            if alvo is not None:
                extra = f"\nDuração: {duracao} hora(s)." if medida == "ban_temp" else f"\nDuração: {duracao} minuto(s)." if medida == "timeout" else ""
                await alvo.send(
                    f"**NÊMESIS — Decisão de moderação**\n"
                    f"Infração: {infracao_nome}\nMedida: {medida_texto}\nMotivo: {motivo[:700]}{extra}"
                )
        except (discord.Forbidden, discord.HTTPException):
            pass

        log = discord.Embed(
            title="🛡️ Auditoria — AutoMod",
            description=(
                f"**Resultado:** Punido\n**Membro:** <@{alvo_id}> ({alvo_id})\n"
                f"**Infração:** {infracao_nome}\n**Nível:** {nivel}\n"
                f"**Medida:** {medida_texto}\n**Moderador:** {interaction.user.mention}\n"
                f"**Motivo:** {discord.utils.escape_markdown(motivo[:700])}\n"
                f"**Registro:** [Abrir infração]({mensagem.jump_url})"
            ),
            color=discord.Color.red() if nivel >= 3 else discord.Color.gold(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        await self.enviar_auditoria(guild, log)

    async def registrar_nao_punir(self, interaction: discord.Interaction, alvo_id: int, motivo: str, embed: discord.Embed, mensagem: discord.Message):
        guild = interaction.guild
        if guild is None:
            raise ValueError("Servidor não encontrado.")
        infracao_match = re.search(r"\*\*Infração:\*\*\s*([^\n]+)", embed.description or "")
        infracao_nome = infracao_match.group(1).strip() if infracao_match else "Infração AutoMod"
        await self.registrar_decisao(guild.id, alvo_id, "nao_punido", 0, motivo, interaction.user.id, infracao_nome)
        embed.add_field(
            name="Decisão da moderação",
            value=(
                "**Resultado:** Não punido\n"
                f"**Responsável:** {interaction.user.mention}\n"
                f"**Motivo:** {discord.utils.escape_markdown(motivo[:700])}"
            ),
            inline=False,
        )
        embed.color = discord.Color.green()
        await mensagem.edit(embed=embed, view=None)
        log = discord.Embed(
            title="🛡️ Auditoria — AutoMod",
            description=(
                f"**Resultado:** Não punido\n**Membro:** <@{alvo_id}> ({alvo_id})\n"
                f"**Infração:** {infracao_nome}\n**Moderador:** {interaction.user.mention}\n"
                f"**Motivo:** {discord.utils.escape_markdown(motivo[:700])}\n"
                f"**Registro:** [Abrir infração]({mensagem.jump_url})"
            ),
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        await self.enviar_auditoria(guild, log)

    # ========================================================
    # BANIMENTOS TEMPORÁRIOS
    # ========================================================

    async def carregar_banimentos_temporarios(self):
        """Retorna None em falha de storage para não confundir erro com arquivo vazio."""
        try:
            dados = await carregar(ARQUIVO_BANIMENTOS_TEMPORARIOS, {})
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Falha ao carregar banimentos temporários; nenhuma expiração será descartada."
            )
            return None
        if not isinstance(dados, dict):
            import logging
            logging.getLogger(__name__).error(
                "Armazenamento de banimentos temporários possui formato inválido."
            )
            return None
        return dados

    async def salvar_banimentos_temporarios(self, dados) -> bool:
        if not isinstance(dados, dict):
            return False
        try:
            await salvar(ARQUIVO_BANIMENTOS_TEMPORARIOS, dados)
            return True
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Falha ao salvar banimentos temporários; a operação não será considerada persistida."
            )
            return False

    async def registrar_banimento_temporario(self, guild_id, user_id, duracao) -> bool:
        async with self._banimentos_lock:
            dados = await self.carregar_banimentos_temporarios()
            if not isinstance(dados, dict):
                return False
            try:
                duracao = max(1, int(duracao))
            except (TypeError, ValueError, OverflowError):
                return False

            dados[f"{int(guild_id)}:{int(user_id)}"] = {
                "guild_id": int(guild_id),
                "user_id": int(user_id),
                "expira_em": time.time() + duracao,
            }
            return await self.salvar_banimentos_temporarios(dados)

    @tasks.loop(seconds=30)
    async def verificar_banimentos(self):
        await self.bot.wait_until_ready()

        async with self._banimentos_lock:
            dados = await self.carregar_banimentos_temporarios()
            if not isinstance(dados, dict):
                # Não apagamos registros quando o storage está indisponível/corrompido.
                return

            alterado = False
            agora = time.time()
            for chave, registro in list(dados.items()):
                if not isinstance(registro, dict):
                    continue
                try:
                    expira_em = float(registro["expira_em"])
                    guild_id = int(registro["guild_id"])
                    user_id = int(registro["user_id"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue

                if agora < expira_em:
                    continue

                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    # A guild pode ainda não estar no cache; tenta novamente no próximo ciclo.
                    continue

                try:
                    await guild.unban(
                        discord.Object(id=user_id),
                        reason="Fim do banimento temporário do AutoMod",
                    )
                except discord.NotFound:
                    # Já está desbanido; é seguro remover o registro expirado.
                    pass
                except (discord.Forbidden, discord.HTTPException) as erro:
                    print(
                        "[AUTOMOD][ERRO] "
                        f"Falha ao expirar ban temporário (guild={guild_id}, user={user_id}): {erro}"
                    )
                    # Mantém o registro para tentar novamente no próximo ciclo.
                    continue

                dados.pop(chave, None)
                alterado = True

            if alterado and not await self.salvar_banimentos_temporarios(dados):
                print("[AUTOMOD][ERRO] Não consegui persistir a remoção de banimentos expirados; será reavaliado no próximo ciclo.")

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

        # Prioriza o Member anexado à própria mensagem: ele pode conter
        # cargos/permissões mais recentes que uma entrada antiga no cache do guild.
        # Só consulta o cache/API se o evento realmente trouxer apenas User.
        membro = message.author if isinstance(message.author, discord.Member) else message.guild.get_member(message.author.id)
        if membro is None:
            try:
                membro = await message.guild.fetch_member(message.author.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Fail-safe: sem confirmar identidade/permissões, não analisar nem apagar.
                return

        # Atualiza a referência caso o autor do evento seja Member, evitando que
        # uma cópia desatualizada do cache sobrescreva os cargos do evento.

        # Isenção administrativa executada antes de qualquer histórico/detecção.
        # Os administradores e responsáveis pela moderação têm bypass integral.
        permissoes = membro.guild_permissions
        if (
            membro.id == message.guild.owner_id
            or permissoes.administrator
            or permissoes.manage_messages
            or permissoes.manage_guild
            or membro_pode_moderar(membro, message.channel)
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
    # ESTATÍSTICAS DE MODERAÇÃO
    # ========================================================

    @app_commands.command(name="estatisticas", description="Mostra as estatísticas de moderação da NÊMESIS.")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_estatisticas(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        decisoes = await carregar("automod_decisoes.json", {})
        registros = decisoes.get(str(interaction.guild.id), [])
        agora = time.time()
        ultimos_7 = [r for r in registros if agora - float(r.get("timestamp", 0)) <= 7 * 86400]
        ultimos_30 = [r for r in registros if agora - float(r.get("timestamp", 0)) <= 30 * 86400]
        punidos = sum(1 for r in ultimos_30 if r.get("tipo") == "punido")
        nao_punidos = sum(1 for r in ultimos_30 if r.get("tipo") == "nao_punido")
        niveis = {n: sum(1 for r in ultimos_30 if r.get("tipo") == "punido" and int(r.get("nivel", 0)) == n) for n in range(1, 6)}
        reincidentes = {}
        for r in ultimos_30:
            if r.get("tipo") == "punido":
                uid = str(r.get("membro_id"))
                reincidentes[uid] = reincidentes.get(uid, 0) + 1
        repetidos = sum(1 for total in reincidentes.values() if total >= 2)
        embed = discord.Embed(title="📊 NÊMESIS — Estatísticas da moderação", color=discord.Color.blurple())
        embed.add_field(name="Últimos 7 dias", value=f"Decisões: **{len(ultimos_7)}**", inline=True)
        embed.add_field(name="Últimos 30 dias", value=f"Decisões: **{len(ultimos_30)}**", inline=True)
        embed.add_field(name="Punições / Não punidos", value=f"**{punidos}** / **{nao_punidos}**", inline=True)
        embed.add_field(name="Níveis aplicados (30 dias)", value="\n".join(f"Nível {n}: **{niveis[n]}**" for n in range(1, 6)), inline=True)
        embed.add_field(name="Membros punidos 2+ vezes", value=f"**{repetidos}**", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ========================================================
    # CONFIGURAÇÃO DOS NÍVEIS
    # ========================================================

    @app_commands.command(name="configurar-nivel", description="Configura a medida e duração de um nível do AutoMod.")
    @app_commands.describe(nivel="Nível entre 1 e 5", medida="Medida a aplicar nesse nível", duracao="Minutos para timeout ou horas para banimento temporário")
    @app_commands.choices(medida=[
        app_commands.Choice(name="Advertência", value="warn"),
        app_commands.Choice(name="Timeout", value="timeout"),
        app_commands.Choice(name="Expulsão", value="kick"),
        app_commands.Choice(name="Banimento temporário", value="ban_temp"),
        app_commands.Choice(name="Banimento permanente", value="ban_permanente"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def automod_configurar_nivel(self, interaction: discord.Interaction, nivel: app_commands.Range[int, 1, 5], medida: app_commands.Choice[str], duracao: app_commands.Range[int, 0, 8760] = 0):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if not duracao:
            duracao = 24 if medida.value == "ban_temp" else 10 if medida.value == "timeout" else 0
        config = await get_config(interaction.guild.id)
        niveis = dict(config.get("automod_niveis") or {})
        niveis[str(nivel)] = {"medida": medida.value, "duracao": int(duracao)}
        await set_config(interaction.guild.id, automod_niveis=niveis)
        unidade = "hora(s)" if medida.value == "ban_temp" else "minuto(s)" if medida.value == "timeout" else "não aplicável"
        duracao_texto = f"{duracao} {unidade}" if medida.value in {"ban_temp", "timeout"} else "sem duração"
        await interaction.response.send_message(
            f"Configuração salva para o nível {nivel} — **{NIVEIS[nivel]['nome']}**.\n"
            f"**Medida:** {medida.name}\n**Duração:** {duracao_texto}.\n"
            "A configuração é persistida no armazenamento compartilhado.",
            ephemeral=True,
        )

    # ========================================================
    # HISTÓRICO POR MEMBRO
    # ========================================================

    @app_commands.command(name="historico", description="Consulta o histórico recente de decisões de moderação de um membro.")
    @app_commands.describe(membro="Membro cujo histórico será consultado")
    @app_commands.default_permissions(manage_guild=True)
    async def automod_historico(self, interaction: discord.Interaction, membro: discord.Member):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        decisoes = await carregar("automod_decisoes.json", {})
        registros = [
            item for item in decisoes.get(str(interaction.guild.id), [])
            if int(item.get("membro_id", 0)) == membro.id
        ]
        registros.sort(key=lambda item: float(item.get("timestamp", 0)), reverse=True)
        registros = registros[:10]
        embed = discord.Embed(
            title="📋 Histórico AutoMod",
            description=f"**Membro:** {membro.mention}\n**Decisões registradas:** {len([x for x in decisoes.get(str(interaction.guild.id), []) if int(x.get('membro_id', 0)) == membro.id])}",
            color=discord.Color.blurple(),
        )
        if not registros:
            embed.add_field(name="Histórico", value="Nenhuma decisão registrada pelo novo sistema.", inline=False)
        else:
            linhas = []
            for item in registros:
                data = datetime.datetime.fromtimestamp(float(item.get("timestamp", 0)), datetime.timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
                resultado = "Não punido" if item.get("tipo") == "nao_punido" else f"Punido — nível {item.get('nivel', '?')}"
                linhas.append(f"**{data}** · {resultado}\nInfração: {item.get('infracao', 'Não informada')}\nMotivo: {item.get('motivo', 'Não informado')[:180]}")
            embed.add_field(name="Últimas decisões", value="\n\n".join(linhas)[:1024], inline=False)
        punicoes = await historico_punicoes(interaction.guild.id, membro.id, limite=10)
        if punicoes:
            linhas_punicoes = []
            for item in punicoes[:5]:
                data = datetime.datetime.fromtimestamp(float(item.get("timestamp", 0)), datetime.timezone.utc).strftime("%d/%m/%Y")
                linhas_punicoes.append(f"• {data} — {item.get('tipo', 'registro')}: {item.get('motivo', 'Sem motivo')[:120]}")
            embed.add_field(name="Histórico de punições", value="\n".join(linhas_punicoes)[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ========================================================
    # COMANDO — REGRAS
    # ========================================================

    @app_commands.command(
        name="regras",
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
        name="atualizar",
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
        name="status",
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
    bot.add_view(PainelPunicao(bot))

    print(
        "[AUTOMOD] Cog registrado no bot."
    )