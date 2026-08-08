import re
import datetime
import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar_config, carregar_texto_config
from utils.guild_config import get_config, set_config
from utils.ia import perguntar_ia, ErroIA
from utils.pesquisa import pesquisar_web, ErroPesquisa
from utils.memoria import salvar_interacao, resumo_interacoes_recentes, resumo_fatos_ensinados
from utils.atualizacao import get_atualizacao_de_hoje

MAX_TOKENS_RESPOSTA = 2000  # limite de tamanho da resposta da IA

FUSO_BRASIL = datetime.timezone(datetime.timedelta(hours=-3))  # Brasil não usa horário de verão desde 2019
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

SYSTEM_PROMPT = """Você é o assistente de um servidor de Discord. Pode responder qualquer \
pergunta, sobre qualquer assunto — não só sobre jogos. Responda em português, de forma \
clara e completa, mas sem enrolação desnecessária, como quem manda mensagem no Discord \
(pode usar parágrafos curtos e, se ajudar, listas).

Data e hora agora (horário de Brasília, use isso pra qualquer pergunta sobre tempo, prazo ou \
data — nunca chute): {agora}

Você também tem conhecimento extra e curado sobre o jogo Gakuran (Roblox), que fica listado \
abaixo — use isso quando a pergunta for sobre esse jogo especificamente. Além disso, você \
recebe o resultado de uma pesquisa na web feita agora mesmo sobre a pergunta (pode vir vazia \
se a pesquisa falhar ou não for necessária — nesse caso, responda com seu próprio \
conhecimento). Priorize informação recente da pesquisa quando ela contradisser o que você já \
sabia.

=== PRINCÍPIOS DE COMPORTAMENTO (siga sempre) ===
{principios}
=== FIM DOS PRINCÍPIOS ===

=== FATOS QUE A EQUIPE DESTE SERVIDOR TE ENSINOU (trate como verdade sobre este servidor) ===
{fatos_ensinados}
=== FIM DOS FATOS ENSINADOS ===

=== CONVERSAS RECENTES NESTE SERVIDOR (contexto do que já foi perguntado) ===
{memoria_recente}
=== FIM DAS CONVERSAS RECENTES ===

=== ATUALIZAÇÃO DE HOJE (pesquisa automática diária sobre um tema configurado pela equipe) ===
{atualizacao_diaria}
=== FIM DA ATUALIZAÇÃO DE HOJE ===

=== CONHECIMENTO EXTRA SOBRE O JOGO GAKURAN (use se for relevante à pergunta) ===
{conhecimento}
=== FIM DO CONHECIMENTO SOBRE GAKURAN ===

=== PESQUISA NA WEB AGORA (feita neste exato momento, sobre a pergunta atual) ===
{pesquisa}
=== FIM DA PESQUISA ==="""


def _agora_formatado() -> str:
    agora = datetime.datetime.now(FUSO_BRASIL)
    dia_semana = DIAS_SEMANA[agora.weekday()]
    return agora.strftime(f"%d/%m/%Y %H:%M ({dia_semana}, horário de Brasília)")


class Chat(commands.Cog):
    """Sistema de chat do bot — IA adaptativa, mas supervisionada:
    - lembra sozinha das conversas recentes de cada servidor (automático)
    - usa fatos que a equipe ensinou de propósito (/ensinar, no cogs/aprendizado.py)
    - recebe uma atualização diária pesquisada na web sozinha (uma vez por dia)
    - pesquisa na web a cada pergunta também, pra informação bem recente
    - segue os princípios de comportamento em config/principios_ia.txt"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        entradas = carregar_config("gakuran_knowledge.json")["entradas"]
        self.conhecimento_base = "\n".join(f"- {e['resposta']}" for e in entradas)
        self.principios = carregar_texto_config("principios_ia.txt")

    @app_commands.command(name="configurar-chat", description="Define quem pode conversar com o bot marcando ele (@bot pergunta).")
    @app_commands.describe(cargo="Cargo liberado pra usar o chat", canal="(Opcional) restringe o chat a um canal específico")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_chat(self, interaction: discord.Interaction, cargo: discord.Role, canal: discord.TextChannel = None):
        await set_config(interaction.guild.id, chat_cargo_id=cargo.id, chat_canal_id=canal.id if canal else None)
        onde = f" só em {canal.mention}" if canal else " em qualquer canal"
        await interaction.response.send_message(
            f"✅ Agora quem tem o cargo {cargo.mention} pode marcar o bot pra conversar sobre qualquer assunto{onde}.",
            ephemeral=True,
        )

    @app_commands.command(name="desativar-chat", description="Desativa o sistema de chat do bot neste servidor.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def desativar_chat(self, interaction: discord.Interaction):
        await set_config(interaction.guild.id, chat_cargo_id=0, chat_canal_id=0)
        await interaction.response.send_message("🔒 Chat do bot desativado neste servidor.", ephemeral=True)

    def _limpar_pergunta(self, conteudo: str) -> str:
        return re.sub(r"<@!?\d+>", "", conteudo).strip()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if self.bot.user not in message.mentions:
            return

        config = await get_config(message.guild.id)
        cargo_id = config["chat_cargo_id"]
        if not cargo_id:
            return

        canal_id = config["chat_canal_id"]
        if canal_id and message.channel.id != canal_id:
            return

        cargo = message.guild.get_role(cargo_id)
        if not cargo or cargo not in message.author.roles:
            await message.reply(
                f"Você precisa do cargo {cargo.mention if cargo else '(configurado)'} pra conversar comigo.",
                mention_author=False,
            )
            return

        pergunta = self._limpar_pergunta(message.content)
        if not pergunta:
            await message.reply("Oi! Pode perguntar qualquer coisa — eu pesquiso na web se precisar.", mention_author=False)
            return

        async with message.channel.typing():
            try:
                resultado_pesquisa = await pesquisar_web(pergunta)
            except ErroPesquisa:
                resultado_pesquisa = "(pesquisa na web indisponível agora — respondendo só com conhecimento próprio)"

            atualizacao = await get_atualizacao_de_hoje(message.guild.id)
            texto_atualizacao = atualizacao["resumo"] if atualizacao else "(ainda não pesquisou hoje — primeira atualização do dia pode levar algumas horas)"

            system_prompt = SYSTEM_PROMPT.format(
                agora=_agora_formatado(),
                principios=self.principios,
                fatos_ensinados=await resumo_fatos_ensinados(message.guild.id),
                memoria_recente=await resumo_interacoes_recentes(message.guild.id),
                atualizacao_diaria=texto_atualizacao,
                conhecimento=self.conhecimento_base,
                pesquisa=resultado_pesquisa,
            )

            try:
                resposta = await perguntar_ia(system_prompt, pergunta, max_tokens=MAX_TOKENS_RESPOSTA)
            except ErroIA as e:
                await message.reply(f"⚠️ Não consegui pensar numa resposta agora: {e}", mention_author=False)
                return

        await salvar_interacao(message.guild.id, pergunta, resposta)

        pedacos = [resposta[i:i + 1900] for i in range(0, len(resposta), 1900)] or ["(sem resposta)"]
        for pedaco in pedacos:
            await message.reply(pedaco, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Chat(bot))
