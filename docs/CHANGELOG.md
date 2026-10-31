# Notas de atualização — NÊMESIS / Shinku

Este arquivo registra mudanças por estado de entrega. Merge no GitHub não significa, por si só, que o recurso já esteja ativo no Discord; a ativação depende do deploy e da inicialização correta do bot.

## 2026-10-30 — Central de tickets

### Entregue no código (PRs #49 e #50)
- Reformulação da central de atendimento com identidade visual Carmesim.
- Painel com catálogo de categorias, descrições, fluxo de atendimento, etapas e informações de privacidade.
- Suporte a banner e miniatura por URL HTTPS.
- Novos comandos administrativos:
  - `/ticket-painel-configurar`
  - `/ticket-categoria-visual`
- Novas ações no ticket: adicionar participante e solicitar equipe.
- Preservação das ações de assumir e fechar atendimento, registros, histórico e avaliação.
- Renovação dos nomes e descrições das oito categorias, preservando as chaves internas para compatibilidade.

### Emblemas personalizados (PRs #53 e #54)
- Integração dos oito emojis personalizados ao menu de categorias e ao catálogo visual.
- O bot localiza os emblemas pelo nome cadastrado no servidor, sem exigir IDs informados manualmente.
- Nomes atuais reconhecidos: `emoji_1` a `emoji_8`.
- Compatibilidade mantida com os nomes anteriores `TicketEmoji1` a `TicketEmoji8`.
- Emoji Unicode alternativo utilizado quando um emblema personalizado não está disponível.

### Categorias atuais planejadas
1. Recrutamento e Admissão
2. Estrutura e Hierarquia
3. Integridade e Conduta
4. Operações Competitivas
5. Assistência Técnica
6. Relações Institucionais
7. Gestão de Eventos
8. Premiações e Reconhecimentos

## Sistema de missões e provas

### Em desenvolvimento — PR #55
- Reforma visual dos cartões de catálogo e da central de validação.
- Recompensas de missões apresentadas exclusivamente em XP; P.C. não deve ser exibido como recompensa de missão.
- Cartões de validação com protocolo, participante, categoria, referência, horário e diretrizes de análise.
- Preservação do fluxo de aprovação manual, auditoria, prevenção de duplicidade e divisão de XP entre responsável e auxiliar.

**Estado:** a PR #55 ainda deve ser confirmada como mesclada e implantada antes de anunciar essas mudanças como disponíveis no servidor.

### Atualização do fluxo de participação — 2026-10-31
- O botão de envio abre um seletor privado de atividades ativas, separado por categoria.
- Catálogos com mais de 25 atividades recebem paginação no seletor.
- O formulário de evidência deixa de exigir que o membro copie e digite o código da missão.
- O tutorial de missões foi atualizado para refletir o novo fluxo.
- A navegação identifica a categoria pelo painel atual, inclusive após reinicializações do Shinku.

### Central de Validação de Provas — 2026-10-31
- Painel administrativo privado com indicadores gerais de pendências, aprovações e recusas.
- Filtros combináveis por situação e categoria (Missões, Contribuições, Operações especiais, PvP e PvE).
- Paginação de oito registros por página, com atualização manual e navegação.
- Cada registro exibe protocolo, referência, participante, auxiliar, categoria, data e revisor; recusas exibem a justificativa.
- Painel e cartões de revisão usam ícone do servidor e avatar do bot; o banner aparece no painel sem substituir a imagem da evidência.
- Participante e auxiliar recebem DM após uma aprovação, com o protocolo e o resultado da validação.
- O painel e seus controles verificam o administrador que abriu a sessão; as decisões continuam protegidas pela validação administrativa e pelo estado pendente no armazenamento.

## Observações de implantação
- Alterações mescladas precisam de deploy bem-sucedido no Render.
- Após o deploy, validar os logs de inicialização e os painéis no Discord.
- Não publicar como ativo nenhum recurso marcado como em desenvolvimento ou sem confirmação de deploy.


## 2026-10-31 — Conquistas, medalhas e recompensas

### Entregue no código
- Novo catálogo com 18 conquistas de progressão, participação, operações, guerras e combate.
- Critérios verificáveis por XP organizacional, mensagens válidas, missões aprovadas (incluindo auxiliares), guerras registradas, vitórias, MVPs e recorde de sequência.
- Ledger persistente por servidor e membro, com timestamp de desbloqueio e estado individual da recompensa.
- Recompensas em XP organizacional entregues com chave idempotente; uma mesma conquista não credita XP duas vezes.
- Verificação automática após XP de participação, recompensas de missões e resultados PvP aprovados.
- Anúncio agrupado no canal de conquistas 1563995881508831339.
- Novo comando /conquistas com progresso individual e exibição das metas; o /perfil passa a apresentar as conquistas já desbloqueadas.
- Testes para critérios, dados inválidos, contagem de missões aprovadas e idempotência de desbloqueios/recompensas.

### Observações
- As recompensas são XP organizacional e reconhecimento visual; não concedem permissões administrativas nem alteram a hierarquia de liderança.
- O sistema não apaga nem substitui medalhas competitivas antigas.
- Ativação no Discord depende do deploy e da inicialização do Shinku.
