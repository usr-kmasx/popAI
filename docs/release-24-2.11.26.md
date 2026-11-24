# popAI V24-2.11.26 — notas da versão

Data: 24 de novembro de 2026. Tag Git: `24-2.11.26`.
Continuação de [24-1.11.26](release-24-1.11.26.md).

## Generation e processamento de prompts

A aba Stable Diffusion foi renomeada para **Generation**. Em **Prompt processing**,
há três opções independentes e persistentes: Corrector, Enhancer e Lite.
Por padrão, Corrector e Enhancer estão ativos e Lite está desativado.

| Modo | Contexto | Raciocínio Corrector | Raciocínio Enhancer |
| --- | ---: | ---: | ---: |
| Normal | 8192 | 1024 | 1024 |
| Lite | 4096 | 512 | 192 |

Ambos utilizam cache KV Q4_0 para K e V e Flash Attention. Os pesos Q8_0
do modelo de texto permanecem inalterados. Não há histórico de conversação
entre as etapas; o mesmo motor local é reutilizado durante o processamento
e liberado ao concluir.

- Apenas Corrector: clique direto na varinha, sem menu de estilos.
- Enhancer ativo: escolha entre Simple, More details, Creative e Dramatic;
  o Corrector precede o aprimoramento somente se estiver ativo.
- Ambos desativados: não há processamento; Undo continua disponível
  enquanto existir texto recuperável.

O backend valida as opções e rejeita modos indisponíveis. Uma interface
atualizada não habilita processamento quando o servidor antigo não reconhece
as novas configurações.

## Preload on startup

O interruptor ao lado de Generation profile permite preparar o modelo
selecionado ao iniciar o servidor. A preferência é persistente, desativada
por padrão, e utilizada na próxima inicialização. Sem preload, mantém-se
o carregamento sob demanda.

A implementação reutiliza o motor residente sd-server, sem gerar imagens
durante a inicialização. Utiliza `--eager-load` e, com mmap ativo,
`SD_MMAP_FLAGS=populate` para preencher as páginas mapeadas, respeitando
a política de distribuição entre RAM e VRAM. A assinatura do motor considera
essas opções para evitar reutilização incompatível. Pesos mapeados não são
bloqueados na RAM: o Linux pode recuperar páginas sob pressão de memória.
Uma mudança de modelo, política de pesos ou necessidade de configuração
visual diferente pode exigir recarga.

## Cancelamento

Com preload ativo e o motor pronto, o cancelamento usa a API nativa de jobs,
aguarda a confirmação de estado terminal e preserva o processo residente.
Se não for possível confirmar a interrupção, o motor é encerrado para não
deixar uma geração órfã. Sem preload, o cancelamento conserva o comportamento
anterior de descarregar o motor. O encerramento do aplicativo libera seus
processos. A interface informa se o modelo permaneceu pronto.

## Validação

- 60 testes Python e 26 testes JavaScript aprovados.
- Teste real isolado com Qwen Image 2.1 Fast (4 steps), pesos na RAM:
  inicialização em 3,41 s com cache previamente aquecido; 12,95 GiB de RSS,
  100% das páginas dos três arquivos mapeados residentes e nenhum swap do processo.
- Teste real de cancelamento: o mesmo PID permaneceu ativo, com estado nativo
  ready; 12,95 GiB antes e 12,32 GiB depois, cancelamento em 1,93 s.
- Os testes reais não constituem benchmark de inicialização a frio nem
  validação de todas as combinações de modelos e hardware.

O instalador, os pesos existentes e os prompts artísticos permanecem
inalterados. Não há nova dependência.
