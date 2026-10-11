
    @app_commands.command(
        name="missao-completar",
        description="Envia uma prova de conclusão.",
    )
    @app_commands.describe(
        missao_id="ID da atividade.",
        print="Imagem comprovando a conclusão.",
    )
    async def missao_completar(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        print: discord.Attachment,
    ):
        # Reconhece a interação imediatamente para evitar
        # que o Discord a considere expirada.
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "❌ Este comando só pode ser usado em um servidor.",
                ephemeral=True,
            )
            return

        missao = await missoes.get(
            guild.id,
            missao_id,
        )

        if not missao or not missao.get("ativa", False):
            await interaction.followup.send(
                "❌ Não encontrei nenhuma atividade ativa com esse ID.",
                ephemeral=True,
            )
            return

        tipo = missao.get("tipo", "missao")

        if tipo not in TIPOS:
            await interaction.followup.send(
                "❌ Essa atividade utiliza um tipo antigo que não "
                "faz mais parte da NÊMESIS.",
                ephemeral=True,
            )
            return

        config = await get_config(guild.id)

        chave_provas = f"canal_provas_{tipo}_id"
        canal_id = config.get(chave_provas)

        canal = (
            guild.get_channel(canal_id)
            if canal_id
            else None
        )

        if not isinstance(canal, discord.TextChannel):
            await interaction.followup.send(
                "❌ O canal de provas desse sistema ainda não foi configurado.",
                ephemeral=True,
            )
            return

        revisoes_cog = self.bot.get_cog("Revisoes")

        if not revisoes_cog:
            await interaction.followup.send(
                "⚠️ O sistema de revisão não está carregado.",
                ephemeral=True,
            )
            return

        info = TIPOS[tipo]

        await revisoes_cog.abrir_revisao(
            guild,
            canal,
            tipo="missao",
            autor_id=interaction.user.id,
            referencia_id=missao["id"],
            print_url=print.url,
            titulo=f"{info['nome']} — {missao['titulo']}",
            descricao=(
                f"Prova enviada por {interaction.user.mention}."
            ),
        )

        await interaction.followup.send(
            f"✅ Sua prova foi enviada para {canal.mention} "
            "e aguarda revisão.",
            ephemeral=True,
        )
