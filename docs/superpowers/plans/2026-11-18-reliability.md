# Correções de confiabilidade — itens 1–4

Autorização: seguir a recomendação de corrigir recuperação do melhorador,
biblioteca/seleção, verificação e mensagens de estado. Não medir threads nem
alterar modelos, contexto 2048 ou comportamento de imagem/draft.

1. PromptEnhancer.start permite repetir carga após erro/processo encerrado, sem
   duplicar motor vivo nem fechar servidor estrangeiro. A própria ação Melhorar
   tenta recuperar e espera ready, com cancelamento e limite de carga existentes.
2. Gerenciar pastas/downloads sincroniza roots em memória e identifica seleção
   indisponível; estado imediato na biblioteca e no status, bloqueando Enter para
   geração até selecionar componentes válidos. Não trocar modelo silenciosamente.
3. Verificar valida família/role e calcula SHA de qualquer quantização compatível.
   Hash oficial/registro de download é referência confiável; SHA de importado é
   fingerprint local, não prova de origem. Alteração de download conhecido falha;
   arquivo compatível sem referência recebe resultado distinto. Progresso usa
   tamanho real e registros valem apenas para size/mtime atuais.
4. Avisos do melhorador pertencem à interação e ao job observado. Polling do mesmo
   job concluído não sobrescreve o aviso; pedido novo, estado novo ou erro relevante
   prevalecem. Preservar os controles e a persistência de prompt já existentes.

Validação: fixtures pequenas e verificações temporárias, suíte existente, sem
novos scripts de teste persistentes nem geração de imagem. Recuperação real de
CPU em porta isolada, se necessária, sem tocar no app em uso. Não instalar, publicar
ou criar commits. Revisão final focada nas mudanças.

Resultado: itens 1–4 concluídos. Recuperação real em porta isolada voltou ao
primeiro token em 7,17 s, com PID novo e sem reiniciar o servidor do app. O teste
revelou TIME_WAIT na checagem da porta; corrigido com SO_REUSEADDR, mantendo a
rejeição de listeners estrangeiros. Revisão independente encontrou que Verificar
ignorava os seletores do cartão; corrigido com caminhos explícitos validados no
servidor e preservação das escolhas durante a consulta de progresso.

Verificados SHA padrão, variante compatível sem hash de origem, fingerprint local,
integridade divergente e bloqueio da geração, perda/restauração de pasta e arquivo
ausente, mensagens locais preservadas e prevalência de novo pedido/erro relevante.
Regressão: 18 testes de backend, 6 de interface e verificações temporárias adicionais.
Registro em logs/reliability-20261118.json. Nenhuma imagem gerada, instalação ou
alteração de configuração do app em uso.
