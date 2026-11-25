# popAI V25.11.26 — notas da versão final

Data: 25 de novembro de 2026. Tag Git: `25.11.26`.
Continuação de [24-2.11.26](release-24-2.11.26.md).

Esta versão encerra o desenvolvimento planejado do aplicativo com foco em
integridade, descarte de arquivos temporários e preservação das configurações.
Os modelos, presets, políticas de memória, motores Vulkan e prompts artísticos
permanecem inalterados.

## Integridade

- Perfis e famílias de modelos inválidos são rejeitados com HTTP 400, inclusive
  quando recebem listas ou objetos em vez de texto.
- Imagens PNG de referência são verificadas antes de serem armazenadas:
  cabeçalho, limites de dimensões e tamanho, CRC dos blocos, fluxo comprimido,
  tamanho exato dos dados dos pixels, filtros das linhas e decodificação completa
  com Pillow. PNGs válidos com diferentes formatos de cor e entrelaçamento Adam7
  continuam disponíveis. Os bytes originais são preservados.
- O histórico antigo em JSON deixou de ser lido ou gravado. Um manifesto antigo
  corrompido não interfere mais na inicialização.

## Armazenamento e ciclo de vida

- O estado da geração atual existe apenas na memória do servidor. Não existe
  histórico persistente de gerações.
- Imagens, referências, intermediários e logs de inferência utilizam uma
  pasta temporária privada da sessão. Ao substituir um resultado, o anterior
  é descartado. O botão New também elimina o resultado no servidor, preservando
  as referências anexadas.
- Cópias de referência preparadas para o Qwen são removidas após o uso.
  A base recuperável de uma geração com falha pode ser usada para tentar
  finalizar a imagem novamente, enquanto a sessão estiver aberta.
- O encerramento normal, inclusive por Ctrl+C e SIGTERM, libera os processos
  e remove a pasta temporária. Uma interrupção forçada ou queda de energia
  pode deixar resíduos até a limpeza temporária do sistema operacional.
- Somente imagens baixadas explicitamente permanecem como arquivos do usuário.
  Configurações, biblioteca de modelos, pesos e downloads retomáveis continuam
  persistentes.
- Instalações atualizadas não leem o histórico legado, mas não apagam
  automaticamente arquivos pessoais antigos. Arquivos de experimentos
  e logs de versões anteriores podem ser removidos manualmente.

## Validação

- 66 testes Python de aplicação (47 backend, 6 downloads, 13 processamento de
  prompts) e 26 testes JavaScript aprovados: 92 no total.
- Auditoria anterior da mesma base: 85 testes de regressão aprovados e 105
  verificações adicionais; as cinco falhas encontradas em três grupos foram
  tratadas nesta versão.
- Testes adicionais de PNGs inválidos e válidos, rejeição de entradas malformadas,
  descarte do resultado, ausência de manifestos JSON, isolamento entre sessões
  e encerramento com SIGINT/SIGTERM.
- Verificação do instalador com `./install.sh --check` na máquina Arch Linux
  existente; verificação de sintaxe dos scripts e `git diff --check`.
- As verificações desta versão utilizam componentes simulados, sem novos
  benchmarks com modelos reais. Não foi realizada instalação limpa em
  Debian ou Ubuntu nesta rodada.

Não há nova dependência. Os registros de testes e experimentos locais não
fazem parte do repositório.
