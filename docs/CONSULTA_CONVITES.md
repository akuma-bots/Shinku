# Central de Convites — NÊMESIS

## Consulta individual
A consulta é aberta pelo botão **Consultar convites de membro** no canal **Convites** (`1563995880623841332`), pelo painel fixo **🔗 CENTRAL DE CONVITES**. A liderança pesquisa e seleciona uma pessoa pelo seletor nativo do Discord. O painel fica diretamente no canal de Convites, não no Registro Global. O resultado é privado e não apresenta ranking.

A ficha mostra:
- quantidade de convidados atribuídos ao membro;
- quantos desses convidados continuam no servidor e quantos saíram;
- cada código/link de convite identificado;
- lista dos convidados vinculados a cada link, com situação atual.

## Atribuição e integridade
O Shinku compara o cache de usos dos convites antes e depois de cada entrada. Só atribui um convidado quando exatamente um convite existente teve seu contador incrementado e há um criador identificável. Se houver mais de um candidato, convite desconhecido ou permissão insuficiente, não inventa a atribuição.

O vínculo original é preservado quando uma pessoa sai e retorna: a reentrada não cria um novo convite nem troca o recrutador. Os dados novos guardam o código e a URL utilizados. Registros antigos são migrados para a consulta, mas não recebem links retroativos quando o código não foi armazenado anteriormente.

O cache exige que o bot consiga consultar os convites do servidor (permissão **Gerenciar servidor**). Convites personalizados/vanity, convites temporários já expirados e usos anteriores à implantação não podem ser atribuídos retroativamente com segurança.
