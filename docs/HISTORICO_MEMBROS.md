# Central de Histórico Individual — NÊMESIS

## Acesso pelo Registro Global

Não existe comando para abrir o histórico individual. A consulta fica integrada ao tópico permanente **👥・Arquivo de Membros**, dentro do Fórum privado do Registro Global.

1. Abra o tópico **👥・Arquivo de Membros**.
2. Clique em **Consultar histórico de membro** no cabeçalho do tópico.
3. Pesquise pelo nome e selecione a pessoa no seletor nativo do Discord.
4. Navegue pelas seções do dossiê no menu privado.

O painel é atualizado automaticamente pelo Shinku quando o Registro Global é inicializado. O botão é persistente e continua disponível após reinicializações.

## Seções do dossiê

1. **Visão geral:** identidade Discord, ID, criação da conta, entrada no servidor, situação atual, cargos, XP, rank, mensagens, missões, guerras, combate, punições, conquistas e recrutamento.
2. **Missões e atividades:** provas em que a pessoa consta como autora ou auxiliar, status, categoria, protocolo, revisor e justificativa de recusa quando registrada.
3. **Competitivo:** vitórias, derrotas, empates, K/D, KDR, MVPs, sequência, XP e rank organizacional.
4. **Conquistas:** marcos desbloqueados e distinções sazonais.
5. **Moderação:** punições persistidas e ocorrências recentes de moderação/AutoMod encontradas no Registro Global.
6. **Linha do tempo:** eventos associados ao ID do membro nos tópicos privados do Registro Global, com link para abrir o registro original.

## Fontes consultadas

- perfis.json e progressao_gangue.json
- revisoes.json
- conquistas.json
- temporadas_missoes.json
- punicoes.json
- convites_nemesis.json
- competitivo.json
- Tópicos privados do Registro Global.

A busca da linha do tempo percorre até 40 mensagens recentes por categoria configurada (12 áreas oficiais). Os bancos de missões, punições, conquistas e progressão são consultados separadamente e não dependem desse recorte. Campos sem registro são exibidos como não registrados; o sistema não presume que uma ação ocorreu.

## Privacidade e segurança

- A consulta e o dossiê são efêmeros/privados; somente quem iniciou a consulta vê os dados.
- Acesso verificado pela função central membro_tem_lideranca(); não depende de Administrator ou Manage Guild genéricos.
- O botão, o seletor e o menu de navegação verificam novamente o usuário e a liderança em cada interação.
- O painel é exclusivo do servidor oficial da NÊMESIS.
- A consulta não altera dados, cargos, punições ou histórico.

## Limites conhecidos

- O Discord não oferece um histórico completo de todas as mensagens antigas de um membro por meio deste dossiê; a linha do tempo consulta os registros que o Shinku gravou no Registro Global.
- Eventos anteriores à implantação dos respectivos sistemas, ou ações que nunca foram registradas, não podem ser reconstruídos retroativamente.
- Guerras individuais só são atribuídas quando os dados de progressão/perfil identificam a participação; um placar geral de guerra não é atribuído a todos os membros automaticamente.
