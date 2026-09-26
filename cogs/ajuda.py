import discord
from discord import app_commands
from discord.ext import commands

SISTEMAS = {
    "Missoes": ("🎯", "Missões"),
    "Desafios": ("⚔️", "PvP / Desafios"),
    "PvE": ("👹", "PvE"),
    "Guerras": ("🏰", "Guerras"),
    "Perfil": ("🎖️", "Perfil & Patentes"),
    "PerfilCard": ("🖼️", "Perfil Visual"),
    "RankingGeral": ("🌍", "Ranking Geral"),
    "PontuacaoPvE": ("🗡️", "Pontuação PvE"),
    "Recordes": ("🏅", "Recordes"),
    "Temporadas": ("🏁", "Temporadas"),
    "Gangues": ("🏴", "Gangues"),
    "Loja": ("🛒", "Loja"),
    "Tickets": ("🎫", "Tickets"),
    "Formularios": ("📝", "Formulários"),
    "Revisoes": ("📋", "Revisão de Provas"),
    "Auditoria": ("🧾", "Auditoria"),
    "Ajuda": ("📖", "Ajuda"),
}
ORDEM = list(SISTEMAS.keys())
LIMITE_DESCRICAO = 3800  # margem de segurança abaixo do limite de 4096 do Discord


def _sistema_do_comando(comando: app_commands.Command):
    cog = comando.binding
    nome_cog = cog.qualified_name if cog else "Outros"
    emoji, titulo = SISTEMAS.get(nome_cog, ("🔧", nome_cog))
    return nome_cog, emoji, titulo


def _pode_ver(comando: app_commands.Command, membro: discord.Member) -> bool:
    if not comando.checks:
        return True
    return membro.guild_permissions.administrator or membro.guild_permissions.manage_guild


class PaginacaoAjuda(discord.ui.View):
    """Navegação simples entre páginas do /help, só pra quem pediu o
    comando — dura 2 minutos e depois os botões somem sozinhos."""

    def __init__(self, paginas: list, autor_id: int):
        super().__init__(timeout=120)
        self.paginas = paginas
        self.autor_id = autor_id
        self.indice = 0
        self._atualizar_botoes()

    def _atualizar_botoes(self):
        self.botao_anterior.disabled = self.indice == 0
        self.botao_proxima.disabled = self.indice == len(self.paginas) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Esse menu não é seu — use `/help` pra abrir o seu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
    async def botao_anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.indice -= 1
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.paginas[self.indice], view=self)

    @discord.ui.button(label="Próxima ➡️", style=discord.ButtonStyle.secondary)
    async def botao_proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.indice += 1
        self._atualizar_botoes()
        await interaction.response.edit_message(embed=self.paginas[self.indice], view=self)


class Ajuda(commands.Cog):
    """/help com todos os comandos organizados por sistema, em texto corrido
    (não em fields — evita o limite de 25 campos do Discord) e paginado
    automaticamente se não couber numa mensagem só."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _montar_agrupado(self, membro: discord.Member) -> dict:
        agrupado = {}
        for comando in sorted(self.bot.tree.get_commands(), key=lambda c: c.name):
            if not isinstance(comando, app_commands.Command):
                continue
            if not _pode_ver(comando, membro):
                continue
            nome_cog, emoji, titulo = _sistema_do_comando(comando)
            agrupado.setdefault(nome_cog, {"emoji": emoji, "titulo": titulo, "comandos": []})
            agrupado[nome_cog]["comandos"].append(comando)
        return agrupado

    def _montar_paginas(self, agrupado: dict) -> list:
        chaves_ordenadas = [k for k in ORDEM if k in agrupado] + [k for k in agrupado if k not in ORDEM]

        blocos = []
        for chave in chaves_ordenadas:
            grupo = agrupado[chave]
            linhas = "\n".join(f"**/{c.name}** — {c.description}" for c in grupo["comandos"])
            blocos.append(f"**{grupo['emoji']} {grupo['titulo']}**\n{linhas}")

        paginas_texto, atual = [], ""
        for bloco in blocos:
            candidato = f"{atual}\n\n{bloco}" if atual else bloco
            if len(candidato) > LIMITE_DESCRICAO:
                paginas_texto.append(atual)
                atual = bloco
            else:
                atual = candidato
        if atual:
            paginas_texto.append(atual)

        total = len(paginas_texto)
        embeds = []
        for i, texto in enumerate(paginas_texto, start=1):
            embed = discord.Embed(title="📖 Comandos do Bot", description=texto, color=0x5865F2)
            embed.set_footer(text=f"Página {i}/{total}")
            embeds.append(embed)
        return embeds

    @app_commands.command(name="help", description="Lista todos os comandos do bot, organizados por sistema.")
    async def help_cmd(self, interaction: discord.Interaction):
        agrupado = self._montar_agrupado(interaction.user)
        paginas = self._montar_paginas(agrupado)

        if len(paginas) == 1:
            await interaction.response.send_message(embed=paginas[0], ephemeral=True)
            return

        view = PaginacaoAjuda(paginas, interaction.user.id)
        await interaction.response.send_message(embed=paginas[0], view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ajuda(bot))