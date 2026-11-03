# Central de Histórico Individual — NÊMESIS

## Comando

`/historico membro:<nome, usuário ou ID Discord>`

O comando abre um dossiê privado e interativo do membro. A consulta é restrita à liderança autorizada da NÊMESIS, incluindo Supervisor Staff, respeitando a matriz administrativa central.

## Pesquisa e seleção

- O campo aceita ID numérico, nome de exibição, nome de usuário ou parte do nome.
- A lista de autocomplete sugere membros do servidor.
- Se houver mais de uma correspondência, o bot apresenta um seletor com nome e ID para evitar abrir a ficha errada.
- Um ID também pode localizar uma conta que já saiu do servidor, desde que o Discord ainda permita resolver a conta. Nesses casos, os dados atuais de cargos e entrada não estão disponíveis, mas os registros persistidos continuam sendo consultados.

## Seções do dossiê

1. **Visão geral:** identidade Discord, ID, criação da conta, entrada no servidor, situação atual, cargos, XP, rank, mensagens, missões, guerras, combate, punições, conquistas e recrutamento.
2. **Missões e atividades:** provas em que a pessoa consta como autora ou auxiliar, status, categoria, protocolo, revisor e justificativa de recusa quando registrada.
3. **Competitivo:** vitórias, derrotas, empates, K/D, KDR, MVPs, sequência, XP e rank organizacional.
4. **Conquistas:** marcos desbloqueados e distinções sazonais.
5. **Moderação:** punições persistidas e ocorrências recentes de moderação/AutoMod encontradas no Registro Global.
6. **Linha do tempo:** eventos associados ao ID do membro nos tópicos privados do Registro Global, com link para abrir o registro original.

## Fontes consultadas

- `perfis.json` e `progressao_gangue.json`
- `revisoes.json`
- `conquistas.json`
- `temporadas_missoes.json`
- `punicoes.json`
- `convites_nemesis.json`
- `competitivo.json`
- Tópicos privados do Registro Global.

A busca da linha do tempo percorre até 40 mensagens recentes por categoria configurada (22 categorias). Os bancos de missões, punições, conquistas e progressão são consultados separadamente e não ficam limitados a esse recorte. Campos sem registro são exibidos como não registrados; o sistema não presume que uma ação ocorreu.

## Privacidade e segurança

- A resposta é efêmera: somente quem executou o comando vê o dossiê.
- Acesso verificado pela função central `membro_tem_lideranca()`; não depende de `Administrator` ou `Manage Guild` genéricos.
- Os menus interativos verificam novamente o usuário e a liderança em cada interação.
- O comando é exclusivo do servidor oficial da NÊMESIS.
- A consulta não altera dados, cargos, punições ou histórico.

## Limites conhecidos

- O Discord não oferece um histórico completo de todas as mensagens antigas de um membro por meio deste dossiê; a linha do tempo consulta os registros que o Shinku gravou no Registro Global.
- Eventos anteriores à implantação dos respectivos sistemas, ou ações que nunca foram registradas, não podem ser reconstruídos retroativamente.
- Guerras individuais só são atribuídas quando os dados de progressão/perfil identificam a participação; um placar geral de guerra não é atribuído a todos os membros automaticamente.
