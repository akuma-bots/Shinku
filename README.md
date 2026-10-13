# NÊMESIS — Bot oficial

Bot oficial da NÊMESIS, desenvolvido em Python com `discord.py`. O projeto reúne operações da gangue, atendimento, moderação, missões, revisão de provas, confrontos PvP, guerras, progressão, sorteios e integração com o dashboard.

O bot é exclusivo do servidor configurado por `NEMESIS_GUILD_ID`. Não é um modelo multi-servidor.

## Sistemas principais

- **Atendimento:** tickets privados, categorias de solicitação, fechamento e registro.
- **Moderação e segurança:** regras, avisos, punições e registros administrativos.
- **Missões:** missões, contribuições e missões especiais, com provas e aprovação da staff.
- **PvP:** desafios entre membros, apostas de XP, envio de resultados e revisão.
- **Guerras:** registro de resultados, guerras em andamento, atualização de placar, regras, cancelamento e histórico.
- **Progressão da gangue:** XP de participação, ranks, cargos configuráveis e recompensas.
- **Perfil e competitivo:** XP, patentes, vitórias, derrotas, KDR, P.C., temporadas e rankings; o perfil também exibe a conta Roblox verificada.
- **Roblox:** vínculo por código de verificação, consulta de perfil, identificação de membros pelo nome Roblox e sincronização opcional de cargos por rank.
- **Tutoriais:** central interativa `/tutorial` com guias para missões, PvP, guerras, moderação, provas, sorteios, tickets, eventos, formulários, Roblox e outros sistemas.
- **Novidades por DM:** releases oficiais enviados automaticamente a todos os membros humanos do servidor, sem inscrição prévia, com registro persistente para evitar repetição em reinicializações.
- **Sorteios:** embeds, botões de participação, requisitos informativos, prêmios, término automático e seleção de vencedores.
- **Recordes, eventos e parcerias:** registros e anúncios nos canais configurados.
- **Dashboard:** compartilhamento de dados com o site da NÊMESIS por meio do Upstash.

## Requisitos

- Python 3.12 recomendado.
- Aplicação de bot criada no [Discord Developer Portal](https://discord.com/developers/applications).
- Redis REST do Upstash para manter bot e dashboard usando o mesmo armazenamento.
- Permissões Discord compatíveis com os recursos ativados, incluindo visualizar/enviar mensagens, embeds, gerenciar mensagens e canais, moderar membros e gerenciar cargos quando necessário.

Ative no portal os intents **Message Content** e **Server Members** quando os recursos instalados exigirem esses dados.

## Configuração local

Crie um ambiente virtual e instale as dependências:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Windows, ative o ambiente com `.venv\\Scripts\\activate`.

Configure as seguintes variáveis de ambiente. Não coloque credenciais no código nem as envie ao GitHub.

| Variável | Obrigatória | Finalidade |
|---|---|---|
| `DISCORD_TOKEN` | Sim | Token privado do bot. |
| `NEMESIS_GUILD_ID` | Sim | ID numérico do servidor oficial da NÊMESIS. |
| `UPSTASH_REDIS_REST_URL` | Sim em produção | URL REST do banco compartilhado. |
| `UPSTASH_REDIS_REST_TOKEN` | Sim em produção | Token privado do banco compartilhado. |
| `PORT` | Não | Porta HTTP de health check; usa 8080 como padrão fora de plataformas que definem a porta. |

Em produção no Render, o bot recusa iniciar se o Upstash não estiver configurado. Isso evita operar silenciosamente com dados locais que não sincronizam com o dashboard.

Inicie localmente:

```bash
python bot.py
```

## Deploy e diagnóstico

O processo de inicialização carrega os módulos da pasta `cogs`, registra falhas de carregamento e sincroniza os comandos de barra com o servidor configurado.

- `/` — resposta básica de disponibilidade HTTP.
- `/health` — estado do bot, ID do servidor, backend de armazenamento, cogs carregados e falhas de carregamento.

O estado HTTP não substitui a verificação dos logs do Render nem confirma, por si só, que todos os comandos e integrações estão funcionando.

## Validação automática

O workflow em `.github/workflows/quality.yml` executa em pushes e pull requests para `main`. Ele verifica:

1. Sintaxe Python dos módulos principais.
2. Validade dos arquivos JSON versionados.
3. Estrutura básica do catálogo padrão de missões, incluindo IDs únicos, tipos válidos, títulos e recompensas não negativas.

O workflow é uma primeira barreira de qualidade; não substitui testes funcionais no Discord, no Render ou no Upstash.

## Armazenamento e segurança

- O bot e o dashboard devem usar o mesmo banco Upstash e os mesmos nomes de chaves esperados pela integração.
- Os arquivos locais em `data/` servem para execução local; não são um substituto para o armazenamento compartilhado em produção.
- Nunca faça commit de `.env`, tokens, chaves REST ou outros segredos.
- Alterações em comandos só ficam disponíveis no Discord depois que o processo atualizado inicia e sincroniza a árvore de comandos.
- Confirme logs e o endpoint `/health` após cada deploy.

## Contribuição

1. Faça as alterações em uma branch.
2. Confira o resultado do workflow de validação.
3. Teste o comportamento no servidor de desenvolvimento antes de usar recursos administrativos ou recompensas no servidor oficial.
4. Documente mudanças em comandos, armazenamento e variáveis de ambiente.

## Tutoriais e avisos automáticos

- O comando `/tutorial` abre uma central interativa de tutoriais por sistema.
- As novidades oficiais de versões novas são obrigatórias e enviadas por DM a todos os membros humanos do servidor, sem opção de inscrição ou cancelamento. Membros com DMs bloqueadas podem não receber a mensagem; isso não interrompe o envio aos demais. `/avisos-privados` continua controlando apenas comunicados manuais direcionados aos inscritos.
- Ao publicar uma nova versão com novidades para anunciar, atualize `config/novidades.json`: altere `release_id` para um identificador novo e revise `titulo`, `tipo` e `mensagem`. O bot registra os usuários processados no armazenamento compartilhado para não reenviar a mesma versão após reiniciar.
- Para vincular o Roblox, o membro usa `/roblox-vincular`, adiciona temporariamente o código à descrição do perfil Roblox e confirma com `/roblox-confirmar`. A mesma conta Roblox não pode ser vinculada a dois membros diferentes.
