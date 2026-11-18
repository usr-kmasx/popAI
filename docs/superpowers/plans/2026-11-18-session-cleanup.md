# Limpeza da sessão e Desfazer persistente

Escopo autorizado: itens 1 e 2. Não alterar detecção de SSD/primeira abertura.

1. Manter a prévia atual e a anterior por 60 segundos para dar tempo de a interface
   atualizar; guardar os intermediários do pedido corrente para recuperação. Ao
   aceitar um pedido novo, intermediários de pedidos já abandonados podem sair.
   Downloads leem o PNG sob o mesmo lock da limpeza; bytes já enviados ao handler
   permanecem disponíveis mesmo se o arquivo temporário for removido.
2. Referências removidas na interface são liberadas por API; referência de geração
   em curso só sai após o pedido terminar. Ao sair da página, liberação best-effort.
   Referências anexadas recebem heartbeat no polling existente; órfãs expiram em
   uma hora. Limpeza preguiçosa no status, upload e término de pedido, sem nova
   thread. PNGs permanentes antigos, downloads e registros de jobs/logs preservados.
3. Salvar um registro único de draft e undo no navegador, migrando o draft antigo.
   Restauração só aceita undo cujo texto melhorado corresponda ao draft; apagar ou
   editar invalida undo. Streaming não grava texto parcial: salvar snapshot anterior
   até sucesso; falha/cancelamento restaura snapshot anterior completo.
4. Validar com fixtures pequenas e mocks existentes, incluindo leitura de download
   durante limpeza, geração ativa, retry, heartbeat, expiração e múltiplas reaberturas.
   Sem instalar, gerar imagens reais, novos scripts de testes ou mudar o app em uso.

Concluído: limpeza limitada ao workspace temporário, snapshots de download sob lock,
leases/liberação de referências com proteção de geração ativa e recovery, migração
atômica de draft/undo. A revisão encontrou a liberação indevida em navegação via
cache Voltar/Avançar; corrigida usando pagehide.persisted e reconciliação de refs
expiradas ao retornar. Casos diretos passaram: 9 de limpeza/referências/download,
3 de persistência/undo e 2 de navegação. Regressão existente: 18 backend e 6 frontend.
Nenhuma mudança em detecção de SSD/primeira abertura.
