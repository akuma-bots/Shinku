# Painel Administrativo Central — NÊMESIS

O Painel Administrativo Central é uma navegação privada por botões e menus, publicada no cabeçalho do tópico canônico **Administração** do Registro Global.

## Acesso

- O botão persistente **Abrir Central Administrativa** é exibido no tópico Central de Administração.
- Somente membros da NÊMESIS reconhecidos por `membro_tem_lideranca()` podem abrir a central.
- A consulta é efêmera e vinculada à pessoa que abriu a interface; outra pessoa não pode controlar a sessão.
- A interface não cria comandos slash e não concede permissões novas.

## Áreas

1. **Visão geral:** estado do bot, latência, tempo ativo, efetivo, módulos, tarefas automáticas, Upstash e sincronização do Registro Global.
2. **Membros e hierarquia:** dossiê individual, progressão, entradas, saídas e atividade. A auditoria de cargos permanece separada no tópico administrativo; mensagens editadas e excluídas ficam somente na consulta privada de atividade.
3. **Operações:** botões privados para abrir Processos seletivos, Gestão de missões e Revisão de provas. Em Processos seletivos, a central permite criar e editar formulários, adicionar etapas com até cinco perguntas, remover etapas mediante confirmação, configurar a lista de cargos notificados, pausar, reativar, arquivar e atualizar a central pública. A fila de fichas pendentes é restrita à liderança administrativa, paginada e atualizável; cada dossiê oferece avaliação estruturada, decisão justificada e histórico de auditoria. As decisões exigem ao menos uma avaliação e são serializadas no storage. A gestão de formulários não depende mais de comandos slash. O atalho **Inteligência de operações** aparece somente para o OCTÓGONO e abre a central de métricas de missões já existente. Os demais destinos continuam disponíveis pelos painéis próprios enquanto suas ferramentas administrativas são migradas.
4. **Segurança:** segurança, AutoMod, moderação e decisões administrativas.
5. **Sistemas e infraestrutura:** botões privados para Saúde do sistema e Diagnóstico do armazenamento, além dos destinos de infraestrutura, integrações, configurações e Roblox.
6. **Auditoria e registros:** comunicação, atendimento, histórico individual, eventos e sugestões.

Os botões de destino apontam para tópicos permanentes já existentes ou canais de sistemas existentes. Os atalhos slash para abrir as centrais de formulários, gestão de missões, revisão de provas, status e diagnóstico foram removidos; os fluxos agora partem dos botões da Central Administrativa. O grupo slash de gerenciamento de formulários também foi retirado depois que as operações de criação, edição, etapas, cargos, publicação e fila receberam equivalentes interativos. A central não cria cópias de painéis nem duplica registros. A fila de candidaturas é consultada dentro da gestão do formulário, sem um painel separado de aprovação.

## Regras de autoridade preservadas

- Supervisor Staff continua incluído na liderança administrativa.
- Gestão de missões e acesso à Inteligência de operações continuam exclusivos do OCTÓGONO.
- Promoções, rebaixamentos e banimentos continuam restritos aos cargos autorizados acima de Elite, respeitando a posição hierárquica do alvo.
- As operações sensíveis continuam sendo validadas pelos próprios sistemas e seus fluxos de confirmação.

## Publicação e manutenção

Na inicialização, depois que o Registro Global valida a privacidade e sincroniza os 29 tópicos, o bot atualiza a mensagem inicial do tópico Central de Administração com a view persistente. A mensagem existente é editada; não é criada uma nova publicação a cada reinício.
