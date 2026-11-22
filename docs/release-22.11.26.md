# popAI 22.11.26 — notas da versão

Data: 22 de novembro de 2026. Tag de lançamento: `22.11.26`.
Continuação de [21-1.11.26](release-21-1.11.26.md).

## Novo modelo de melhoramento de prompts

- O modelo ativo passa a ser **Qwen3.5-4B-Uncensored-HauhauCS-Aggressive**, em
  **GGUF Q8_0 (8 bits, 4.482.402.656 bytes)**, obtido do
  [repositório HauhauCS](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive).
  O arquivo, a revisão e o hash SHA-256 estão fixados no
  [`prompt-enhancer.json`](../prompt-enhancer.json). O modelo original LFM3
  e a variante Huihui-Q4 não são necessários nem distribuídos nesta versão.
- A licença-base do Qwen (Apache 2.0) substitui a antiga licença do LFM3
  em [`models/prompt-enhancer/LICENSE`](../models/prompt-enhancer/LICENSE).
  O código do popAI mantém sua licença MIT; os pesos e dependências têm
  suas próprias condições.
- O contexto do melhorador aumenta de **2.048 para 4.096 tokens**;
  `--reasoning off` e as temperaturas dos quatro modos são mantidos.

## Inferência Vulkan sob demanda

- Novo backend dedicado do `llama.cpp`, compilado com **Vulkan** e salvo em
  `backends/llama-vulkan/`, separado do motor de geração de imagens.
  Os binários e pesos são recursos locais ignorados pelo Git.
- O modelo **não é carregado quando o popAI inicia**. Cada ação **Enhance**
  inicia o processo do melhorador, carrega os pesos na GPU, transmite a
  resposta e encerra o processo para liberar a VRAM **antes** de sinalizar
  conclusão. Cancelamento, desconexão e fechamento também encerram o filho.
- O backend é selecionado explicitamente com `--device Vulkan0` e
  `-ngl 999`, sem fallback silencioso para CPU. A GPU precisa suportar Vulkan
  e ter memória suficiente; a configuração foi testada na RX 580 8 GB.
- O instalador `tools/setup-prompt-enhancer.py` agora compila o backend Vulkan
  com as ferramentas e cabeçalhos locais de `tools/local` após `build.sh`,
  baixa o Q8_0 verificado por SHA-256 e prepara a licença do modelo.
  Não há instalação de binários do melhorador fora da pasta do popAI.

## Cinematic Art e interface

- O prompt interno **Cinematic Art** ganhou 12 tópicos: papel, fidelidade,
  direção de arte, materiais, iluminação, profundidade, cores, câmera,
  atmosfera, acabamento, método de reescrita e formato de saída.
  Foi restaurada a versão mais detalhada desse prompt, de 788 palavras,
  priorizando preservar a cena solicitada. A instrução específica que
  proibia introduzir terror, sensualidade, melancolia, agressividade ou drama
  gótico foi removida por pedido do usuário.
- O menu do melhorador permanece disponível quando o modelo está
  descarregado; o botão **Enhance** dispara o carregamento sob demanda.
  Os modos **Simple**, **More details** e **Creative**, desfazer e
  cancelamento continuam presentes.
- Nenhum modelo nem parâmetro da **geração de imagem** foi alterado nesta
  atualização. As notas anteriores continuam como histórico.

## Validação

| Verificação | Resultado |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | 31 testes aprovados |
| `node --test tests/frontend.test.cjs` | 13 testes aprovados |
| `node --check web/app.js` | Sem erro de sintaxe |
| Execução real com Cinematic Art e Q8_0 | Aproximadamente 12,05 s no teste local |
| Gerenciamento Vulkan sob demanda | Processo encerra ao terminar; porta liberada |
| `git diff --check` | Sem erros |

No teste do Q8_0 na RX 580, o uso total de VRAM observado durante o processo
foi de aproximadamente **6,84 GB**, caindo para **2,05 GB** após a execução.
Esses valores incluem outros usos da GPU e não são garantias de desempenho.
O texto gerado preservou os elementos principais do prompt de teste; essa
verificação não garante fidelidade perfeita para todos os pedidos.

## Referências

- [README atualizado](../README.md)
- [Manifesto do melhorador](../prompt-enhancer.json)
- [Registro histórico e adendos do melhorador](prompt-enhancer-validation.md)
- [Versão anterior 21-1.11.26](release-21-1.11.26.md)
