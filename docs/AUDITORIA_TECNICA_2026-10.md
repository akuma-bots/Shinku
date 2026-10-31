# Auditoria técnica do Shinku — NÊMESIS

**Data:** 31/10/2026  
**Base analisada:** branch `main`, commit `527e86bf`  
**Escopo:** inicialização, comandos e permissões, armazenamento, tarefas automáticas, segurança, sistemas principais, workflows e testes.

> Esta auditoria é uma revisão estática do repositório e dos resultados recentes do GitHub Actions. Ela não equivale a um teste funcional dentro do Discord, nem comprova o estado atual do Render ou do Upstash.

## Resumo executivo

O projeto tem uma base considerável de testes, separação entre cogs e utilitários, armazenamento compartilhado opcional e workflows de validação. Os workflows recentes de Python Validation, Validar bot NÊMESIS e Security audit estavam aprovados na revisão.

Os riscos mais relevantes não são falta de funcionalidades. São **consistência de autorização**, **concorrência no armazenamento**, **confiabilidade das tarefas automáticas** e **divergência entre configuração padrão e configuração efetiva do servidor**.

## Achados priorizados

### P0 — Política de autorização administrativa não está centralizada

- `bot.py` aplica uma verificação global baseada no cargo `NEMESIS_ROLE_ID` (1563995879990624372).
- A autorização administrativa continua distribuída pelos cogs através de `administrator=True`, `manage_guild=True` e `has_permissions(...)`.
- Há comandos administrativos em AutoMod, formulários, guerras, desafios, auditoria, temporadas, Roblox, ranking, sorteios, parcerias, recordes, missões e outros módulos.
- A política organizacional definida para a NÊMESIS é que ações administrativas sejam exclusivas do OCTÓGONO/liderança autorizada. Permissões Discord genéricas não garantem essa política por si só.

**Risco:** um membro com permissões Discord elevadas e o cargo-base de acesso pode passar pelos checks genéricos sem pertencer ao grupo administrativo autorizado. O inverso também pode ocorrer se um líder autorizado não possuir o cargo-base exigido.

**Correção planejada:** criar uma política central de autorização com allowlists explícitas por nível de ação, validar os IDs de cargos com a configuração atual do servidor e aplicar checks tanto em slash commands quanto em botões/modais. Não alterar a lista de cargos sem confirmar os IDs atuais. Os 12 cargos competitivos nunca receberão acesso administrativo por XP.

### P1 — Operações de armazenamento Redis não são transacionais

- `utils/storage.py` executa leituras e gravações Redis separadas (`GET` e `SET`).
- Locks existentes em módulos como `utils/guild_config.py` e cogs protegem apenas o processo atual.
- Fluxos concorrentes de leitura-modificação-gravação em cogs diferentes podem sobrescrever alterações uns dos outros; locks locais não coordenam processos ou instâncias diferentes.
- O backend local usa escrita atômica de JSON, mas isso não resolve concorrência distribuída nem persistência em disco efêmero.

**Risco:** perda silenciosa de XP, estatísticas, decisões, configurações ou estados quando operações concorrentes atualizam o mesmo documento.

**Correção planejada:** introduzir operações atômicas por chave (Lua/CAS ou estrutura Redis apropriada), migração incremental e testes concorrentes. Priorizar dados de progressão, missões, revisões, tickets e configurações. Não trocar o formato de dados sem migração e backup.

### P1 — Configurações padrão contêm IDs antigos que precisam ser reconciliados

- `utils/guild_config.py` ainda traz vários IDs padrão iniciados por `154...`.
- A configuração efetiva pode já estar persistida no Upstash e sobrescrever esses padrões; por isso, a presença dos IDs antigos não prova que os canais atuais estejam errados.
- Há também IDs fixos distribuídos em cogs, como canais de tickets, inscrições e conquistas.

**Risco:** instalação limpa ou chave ausente pode apontar sistemas para canais/cargos que não correspondem mais à estrutura atual.

**Correção planejada:** inventariar todos os IDs, classificá-los como configuração oficial, fallback ou legado e validá-los com a API do Discord antes de alterar qualquer valor. Não sobrescrever a configuração persistida automaticamente.

### P1 — Fluxo de comunicados manuais ainda permite concorrência elevada

- Em `cogs/novidades.py`, `/avisos-enviar` cria uma tarefa em segundo plano e cria tarefas para os destinatários em lote.
- O caminho manual não compartilha o mesmo mecanismo persistente de idempotência por destinatário usado pelo fluxo de release.
- `CONCORRENCIA_ENVIO = 40` é um limite alto para disparo de DMs em lote.
- O fluxo automático de release reserva cada destinatário no armazenamento antes da DM, o que reduz duplicações após reinicialização. Entretanto, resultados incertos ficam marcados como tentados e não são reenviados automaticamente — escolha segura contra duplicação, mas que exige reconciliação administrativa para falhas reais.

**Risco:** comunicados manuais repetidos ou concorrentes podem causar rajadas de DMs. Falhas transitórias podem ficar sem recuperação automática.

**Correção planejada:** fila única, limite baixo de concorrência, chave idempotente por comunicado/destinatário, estado explícito (pendente, reservado, entregue, falha permanente, resultado incerto), relatório de entrega e reenvio manual controlado somente após reconciliação. Preservar opt-out.

### P2 — Inicialização e tarefas recorrentes precisam de observabilidade uniforme

- Existem loops em tickets, AutoMod, temporadas, Roblox, ranking, sorteios, contadores e novidades.
- O padrão de start/cancel e tratamento de falhas varia entre cogs.
- O evento `on_ready` pode ocorrer novamente em reconexões; listeners precisam ser idempotentes e não devem duplicar trabalhos.
- A inicialização atual carrega dinamicamente os cogs e sincroniza comandos com cache local.

**Risco:** tarefa repetida, painel atualizado várias vezes, exceção silenciosa ou tarefa que deixa de funcionar depois de reconectar.

**Correção planejada:** padrão comum de ciclo de vida, trava de inicialização, logs estruturados por tarefa, contadores de execução/falha e testes de reconexão. Manter uma única instância por tarefa e cog.

### P2 — Versões Python divergentes entre documentação e CI

- README recomenda Python 3.12.
- `.github/workflows/python-validation.yml` e `security-audit.yml` usam Python 3.11.
- `quality.yml` usa Python 3.12.

**Risco:** uma parte do pipeline pode validar comportamento diferente do runtime de produção.

**Correção planejada:** alinhar a versão de validação à versão de produção e, se necessário, manter matriz de compatibilidade explícita.

### P2 — Auditoria de segurança cobre principalmente dependências

- `security-audit.yml` executa `pip-audit` nas dependências declaradas.
- Não há, no workflow analisado, análise estática de segurança Python, detecção dedicada de segredos ou verificação de permissões/IDs fixos.
- As dependências estão declaradas com limites mínimos, sem lockfile visível na árvore analisada.

**Risco:** vulnerabilidades em código próprio, segredos acidentais e alterações transitivas podem não ser detectados pelo workflow atual.

**Correção planejada:** adicionar Bandit ou Ruff security rules, secret scanning, validação de configuração e lockfile com atualização automatizada controlada.

### P3 — Sessões HTTP Redis não são reutilizadas

- `utils/storage.py` abre uma nova `aiohttp.ClientSession` para cada comando Redis.

**Risco:** overhead de conexão e maior latência em operações de leitura/gravação frequentes.

**Correção planejada:** cliente HTTP de ciclo de vida controlado, reutilizado e encerrado no shutdown, com timeout e retry apenas para operações seguras.

## Pontos positivos confirmados

- O projeto separa comandos por cogs e lógica reutilizável em `utils/`.
- O armazenamento local valida nomes de arquivo e grava JSON com substituição atômica.
- O Upstash usa namespace `nemesis_bot:` e rejeita configuração parcial de URL/token em vez de fazer fallback silencioso.
- O painel de tickets tem proteção contra fechamento duplicado no processo e tarefas periódicas de manutenção.
- Missões e revisões possuem cobertura de testes de integridade e design.
- Existem testes específicos para armazenamento, progressão, formulários, tickets, conquistas, guerras, AutoMod e outros sistemas.
- Os workflows recentes de validação Python, validação do bot e auditoria de dependências estavam aprovados no commit analisado.

## Plano de implementação gradual

### Fase 0 — Linha de base e proteção
- Preservar o estado atual e os dados.
- Criar inventário de comandos, permissões, tarefas, IDs e chaves de armazenamento.
- Manter as notas de atualização sem disparo até a idempotência e o fluxo de entrega estarem validados.
- Não fazer migrações destrutivas.

### Fase 1 — Segurança e autorização
- Política central de cargos autorizados.
- Checks para comandos, botões, modais e callbacks administrativos.
- Testes negativos: membro comum, cargo competitivo, staff sem autorização administrativa, líder autorizado.
- Verificar que nenhum cargo competitivo recebe privilégios por XP.

### Fase 2 — Persistência e integridade
- Operações atômicas no Redis.
- Testes concorrentes e idempotência de recompensas.
- Backup e migração verificável dos documentos existentes.

### Fase 3 — Tarefas e notificações
- Fila única de DMs com opt-out e rate limit.
- Idempotência persistente e painel/relatório de entrega.
- Ciclo de vida padronizado para loops e eventos de reconexão.

### Fase 4 — Modernização dos sistemas
- Missões, tickets, formulários, perfil, ranking, conquistas, guerras, AutoMod e parcerias.
- Padronização de embeds, identidade visual, acessibilidade de componentes e respostas de interação.
- Preservar os fluxos funcionais e os dados existentes.

### Fase 5 — Observabilidade e qualidade contínua
- Health check com estado real de tarefas críticas e storage.
- Logs estruturados, alertas de falha e métricas.
- CI com versão Python alinhada, testes, lint, segurança e secret scanning.

## Critérios para considerar uma fase concluída

1. Testes automatizados aprovados.
2. Testes de regressão dos fluxos relacionados aprovados.
3. Nenhuma perda ou duplicação de dados em testes concorrentes.
4. Permissões testadas com perfis autorizados e não autorizados.
5. Deploy confirmado por logs e health check; teste funcional no Discord quando aplicável.
6. Rollback documentado para alterações de armazenamento ou autorização.

## Limitações desta auditoria

A revisão estática não permite confirmar permissões reais configuradas no Discord, conteúdo efetivo do Upstash, existência/validade de cada canal no servidor, entrega de DMs, comportamento de áudio/voz ou disponibilidade real no Render. Esses itens exigem validação no ambiente ativo.
