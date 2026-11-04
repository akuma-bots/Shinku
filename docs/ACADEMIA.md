# Academia Nêmesis

A Academia mantém o cadastro de treinamentos, inscrições e resultados individuais no Shinku. Os dados são separados por servidor e persistidos pelo armazenamento já utilizado pelo bot.

## Comandos

- `/academia criar`: liderança registra um treinamento com descrição, data/hora de Brasília e limite opcional de vagas.
- `/academia listar`: consulta os treinamentos com inscrições abertas.
- `/academia inscrever`: integrante registra a própria inscrição usando o código do treinamento.
- `/academia avaliar`: liderança registra aprovado, reprovado ou ausente para alguém inscrito, com observação opcional.
- `/academia encerrar`: liderança encerra as inscrições sem apagar os registros.
- `/academia meu-historico`: integrante consulta o próprio histórico.
- `/academia historico`: liderança consulta o histórico de outro integrante.

## Regras de integridade

- O código de cada treinamento é único e gerado pelo bot.
- Inscrições repetidas não criam duplicatas.
- Limite de vagas é respeitado no momento da inscrição.
- Avaliações só podem ser registradas para pessoas inscritas.
- Reavaliações preservam as decisões anteriores.
- Encerrar um treinamento não apaga inscrições ou avaliações.
- Sessões encerradas antigas podem ser removidas apenas quando o limite de armazenamento for atingido; sessões abertas não são descartadas automaticamente.
- A Academia não concede XP automaticamente. A pontuação depende de critérios oficiais definidos pela organização; este módulo registra o resultado sem inventar recompensas.

A criação, avaliação e encerramento são restritos à liderança definida em `utils/guild_config.py`. A inscrição e a consulta do próprio histórico ficam disponíveis aos integrantes com acesso ao bot.
