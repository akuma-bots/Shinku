# Gestão de formulários — Shinku / NÊMESIS

## Acesso administrativo

A gestão começa na **Central Administrativa** do Discord:

1. Abra a área **Operações**.
2. Selecione **Processos seletivos**.
3. Na Central de Formulários, escolha um formulário existente ou crie um novo.
4. Use o seletor de ações para editar os dados, estruturar etapas e perguntas, configurar a comissão e controlar a publicação.

A interface é privada e vinculada ao membro da liderança que abriu a central. A validação confere o servidor de origem, o autor da sessão e a função de liderança já definida no projeto. Nenhum comando digitado, comando slash ou dashboard é necessário.

## Formulários e etapas

- Criação e edição por modais nativos do Discord: nome interno, título público, descrição e banner HTTPS.
- Cada etapa aceita até cinco perguntas por envio, respeitando o limite de componentes do modal.
- Etapas podem ser renomeadas pela ação **Renomear etapa**.
- A remoção de etapa continua exigindo confirmação explícita.
- O painel administrativo apresenta a estrutura das etapas e a distribuição dos tipos de resposta.

## Perguntas

A ação **Editar pergunta** permite alterar o enunciado e configurar:

| Tipo | Componente apresentado ao candidato |
| --- | --- |
| Texto curto | Campo de texto de uma linha |
| Texto longo | Campo de texto em parágrafo |
| Escolha única | Seletor nativo do Discord com 2 a 25 opções |

Cada pergunta também pode ser marcada como obrigatória ou opcional. As opções de escolha aceitam até 100 caracteres cada. O seletor de escolha é usado no modal de candidatura, e não apenas armazenado como metadado.

Perguntas legadas em formato textual continuam aceitas e são tratadas como texto longo. Ao editar uma pergunta legada, ela é convertida para o formato estruturado sem perder seu enunciado.

## Comissão e publicação

- A lista de cargos que recebe os dossiês é configurada por seletor nativo de cargos e botão de salvamento.
- O cargo de instrutor já configurado no módulo continua sendo incluído automaticamente.
- A central pública de inscrições é atualizada após alterações que afetam a apresentação ou disponibilidade.
- Pausar, reativar e arquivar continuam sendo operações distintas. O arquivamento é lógico e preserva candidaturas e auditoria.
- O painel público só habilita formulários ativos, não arquivados e com perguntas.

## Integridade dos registros

- O catálogo permanece em utils/formularios.py, usando a camada existente utils.storage (Upstash quando configurado).
- A edição de perguntas não reescreve respostas já recebidas.
- Cada candidatura mantém o snapshot dos enunciados usados no momento do envio; o dossiê histórico não passa a exibir o texto editado posteriormente.
- A criação, edição, arquivamento, fila de análise, avaliação e decisão continuam usando os registros existentes. Nenhum formulário ou candidatura é apagado por esta melhoria.
- A fila de candidaturas, avaliação estruturada, decisão justificada e histórico permanecem nos painéis já existentes.

## Limites técnicos relevantes

- O Discord permite no máximo cinco campos/componentes principais em um modal.
- A interface agrupa até cinco perguntas por etapa/modal.
- Um seletor de escolha única aceita no máximo 25 opções, com rótulos de até 100 caracteres.
- Cada seletor administrativo exibe até 25 opções; o seletor de perguntas tem paginação.

## Validação

Os testes do módulo verificam a estrutura dos modais, o seletor de escolha nativo, as opções de obrigatoriedade, a renomeação de etapas, a validação de opções e a preservação dos snapshots de candidaturas. A publicação no Discord e o comportamento em produção dependem da execução dos workflows e da disponibilidade do serviço hospedado.
