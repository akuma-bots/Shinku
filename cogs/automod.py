import re
import time
import datetime
import unicodedata
import discord
from discord.ext import commands
from utils.storage import carregar, salvar, carregar_config
from utils.guild_config import get_config
from utils.punicoes import registrar_punicao


class AutoMod(commands.Cog):
    """
    Lê as regras em config/rules.json, escaneia as mensagens de TODOS os
    servidores em que o bot está e, ao identificar quebra de regra, avisa
    o membro (citando a regra), registra o aviso e aplica a punição
    automática quando o limite daquela regra é atingido (mute, kick ou ban).

    As regras em si (config/rules.json) são compartilhadas por todos os
    servidores — os avisos e o canal de logs são separados por servidor.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.regras_config = carregar_config("rules.json")
        self.regras = self.regras_config["regras"]
        self.config_geral = self.regras_config["config_geral"]
        # avisos.json: { "guild_id": { "user_id": { "regra_id": contagem } } } — carregado em cog_load
        self.avisos = {}
        # histórico de mensagens recentes por usuário, para detectar spam/flood
        self._historico_msgs = {}

    async def cog_load(self):
        self.avisos = await carregar("avisos.json", {})

    # ---------- utilidades ----------

    async def _salvar_avisos(self):
        await salvar("avisos.json", self.avisos)

    async def _canal_logs(self, guild: discord.Guild):
        config = await get_config(guild.id)
        log_id = config["log_channel_id"]
        if not log_id:
            return None
        return guild.get_channel(log_id)

    async def _registrar_aviso(self, guild_id: int, user_id: int, regra_id: str) -> int:
        gid, uid = str(guild_id), str(user_id)
        self.avisos.setdefault(gid, {})
        self.avisos[gid].setdefault(uid, {})
        self.avisos[gid][uid][regra_id] = self.avisos[gid][uid].get(regra_id, 0) + 1
        await self._salvar_avisos()
        return self.avisos[gid][uid][regra_id]

    async def _detectar_regra_quebrada(self, message: discord.Message):
        conteudo = message.content.lower()
        agora = time.time()

        for regra in self.regras:
            # canais onde essa regra específica não se aplica: os fixos da regra (globais)
            # + os liberados por este servidor via /liberar-canal
            canais_liberados = list(regra.get("canais_liberados") or [])
            config_servidor = await get_config(message.guild.id)
            canais_liberados += config_servidor["canais_liberados"].get(regra["id"], [])
            if canais_liberados and message.channel.id in canais_liberados:
                continue

            tipo = regra["tipo_deteccao"]

            if tipo == "palavras":
                for palavra in regra.get("palavras", []):
                    if palavra.lower() in conteudo:
                        return regra

            elif tipo == "regex":
                for padrao in regra.get("padroes", []):
                    if re.search(padrao, conteudo, re.IGNORECASE):
                        return regra

            elif tipo == "mencao_massa":
                total_mencoes = len(message.mentions) + len(message.role_mentions)
                if message.mention_everyone:
                    total_mencoes += 1
                if total_mencoes >= regra.get("limite_mencoes", 5):
                    return regra

            elif tipo == "caps_spam":
                texto = message.content
                letras = [c for c in texto if c.isalpha()]
                if len(texto) >= regra.get("tamanho_minimo", 12) and letras:
                    maiusculas = sum(1 for c in letras if c.isupper())
                    if maiusculas / len(letras) >= regra.get("percentual_maiusculas", 0.7):
                        return regra

            elif tipo == "emoji_spam":
                emojis_custom = re.findall(r"<a?:\w+:\d+>", message.content)
                emojis_unicode = re.findall(
                    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]", message.content
                )
                total_emojis = len(emojis_custom) + len(emojis_unicode)
                if total_emojis >= regra.get("limite_emojis", 12):
                    return regra

            elif tipo == "zalgo":
                marcas_unicode = sum(1 for c in message.content if unicodedata.combining(c))
                if marcas_unicode >= regra.get("limite_marcas_unicode", 8):
                    return regra

            elif tipo == "spam_flood":
                # chave por servidor + usuário, pra não misturar contagem entre servidores
                chave = f"{message.guild.id}:{message.author.id}"
                janela = regra.get("janela_segundos", 6)
                limite = regra.get("limite_mensagens", 5)
                historico = self._historico_msgs.setdefault(chave, [])
                historico.append(agora)
                self._historico_msgs[chave] = [t for t in historico if agora - t <= janela]
                if len(self._historico_msgs[chave]) >= limite:
                    self._historico_msgs[chave] = []
                    return regra

        return None

    async def _aplicar_punicao_final(self, message: discord.Message, regra: dict):
        membro = message.author
        punicao = regra.get("punicao_final", "warn")
        motivo = f"Quebra repetida da regra: {regra['titulo']}"

        try:
            if punicao == "mute":
                duracao = self.config_geral.get("duracao_mute_minutos", 30)
                await membro.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=duracao), reason=motivo)
                texto_log = f"🔇 {membro.mention} foi silenciado por {duracao} min — {motivo}"
            elif punicao == "kick":
                await membro.kick(reason=motivo)
                texto_log = f"👢 {membro.mention} foi expulso — {motivo}"
            elif punicao == "ban":
                await membro.ban(reason=motivo, delete_message_days=0)
                texto_log = f"🔨 {membro.mention} foi banido — {motivo}"
            else:
                return
            await registrar_punicao(message.guild.id, membro.id, punicao, motivo, aplicado_por_id=None)
        except discord.Forbidden:
            texto_log = f"⚠️ Não tive permissão para punir {membro.mention} ({punicao}). Verifique a hierarquia de cargos."

        canal_log = await self._canal_logs(message.guild)
        if canal_log:
            await canal_log.send(texto_log)

    # ---------- evento principal ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        regra = await self._detectar_regra_quebrada(message)
        if not regra:
            return

        if self.config_geral.get("apagar_mensagem_infratora", True):
            try:
                await message.delete()
            except discord.Forbidden:
                pass

        contagem = await self._registrar_aviso(message.guild.id, message.author.id, regra["id"])

        aviso_texto = (
            f"⚠️ {message.author.mention}, você quebrou uma regra do servidor:\n"
            f"**{regra['titulo']}**\n{regra['descricao']}\n"
            f"Este é o aviso {contagem}/{regra['limite_avisos_para_punicao']} para esta regra."
        )

        if self.config_geral.get("avisar_por_dm", True):
            try:
                await message.author.send(aviso_texto)
            except discord.Forbidden:
                await message.channel.send(aviso_texto, delete_after=15)
        else:
            await message.channel.send(aviso_texto, delete_after=15)

        canal_log = await self._canal_logs(message.guild)
        if canal_log:
            await canal_log.send(
                f"📋 Aviso registrado: {message.author.mention} — regra `{regra['id']}` "
                f"({contagem}/{regra['limite_avisos_para_punicao']})"
            )

        if contagem >= regra["limite_avisos_para_punicao"]:
            await self._aplicar_punicao_final(message, regra)
            self.avisos[str(message.guild.id)][str(message.author.id)][regra["id"]] = 0
            await self._salvar_avisos()


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
