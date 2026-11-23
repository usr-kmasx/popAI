# popAI 22-1.11.26 — notas da versão

Data: 22 de novembro de 2026. Tag: `22-1.11.26`.
Continuação de [22.11.26](release-22.11.26.md).

## Qwen Image 2.1 passa a ser oficial

- O popAI apresenta **quatro modelos oficiais**: Z-Image Turbo, FLUX.2 Klein 4B,
  FLUX 3 Image Klein e **Qwen Image 2.1 · ChatR Labs Turbo**. O Qwen deixa de
  aparecer como experimental na interface e integra a seleção, o catálogo e
  a biblioteca de downloads como as demais famílias.
- A variante oficial é o gerador ChatR Labs Q8_0 com **Turbo LoRA de 8 passos**,
  encoder Qwen3-VL 8B Q4_K_M, VAE Qwen Image 2.1 BF16 e projetor visual F16.
  Não é o antigo Turbo da Unsloth registrado nos documentos históricos.
- O identificador interno `qwen-image21-experimental` foi mantido apenas por
  **compatibilidade** com configurações e jobs existentes. Não representa o
  status público do modelo.
- Cinco dependências publicadas no
  [manifesto de modelos](../model-downloads.json), totalizando cerca de **15,22 GB**:

| Componente | Arquivo | Tamanho aproximado |
| --- | --- | ---: |
| Gerador Q8_0 | `qwen-image-2.1-step90000-Q8_0.gguf` | 7,69 GB |
| Encoder Q4_K_M | `Qwen3VL-8B-Instruct-Q4_K_M.gguf` | 5,03 GB |
| VAE BF16 | `qwen_image_2.1_vae_bf16.safetensors` | 0,68 GB |
| Projetor de visão F16 | `mmproj-Qwen3VL-8B-Instruct-F16.gguf` | 1,16 GB |
| Turbo LoRA | `chatrlabs-omni-turbo-8step-fp32.safetensors` | 0,67 GB |

Os URLs e hashes SHA-256 estão fixados no manifesto. Os downloads são
retomáveis e verificados antes da publicação. As licenças dos pesos permanecem
sob responsabilidade dos respectivos fornecedores.

## Geração e edição com Qwen

- O Qwen segue o caminho **`sd-cli` por geração**, com Euler, 8 passos,
  CFG 1 e scheduler `simple`. Seu motor não é tratado como residente.
- Suporte a até **10 imagens de referência**. O projetor Qwen3-VL é obrigatório
  para o modo de edição. Antes de enviá-las ao motor, cópias temporárias são
  limitadas a 512 pixels no maior eixo, recebem preenchimento branco para
  múltiplos de 32 e preservam a proporção; os arquivos enviados pelo usuário
  não são modificados.
- As dimensões internas da imagem Qwen também são alinhadas a múltiplos de 32.
  O servidor recorta o excedente antes do fluxo de ampliação existente.
- A LoRA pode estar em uma pasta registrada **diferente** da do gerador. O
  caminho correto é encaminhado ao `sd-cli` via `--lora-model-dir`. Isso
  permite reutilizar arquivos já importados sem duplicação de pesos.
- O sistema atual de ampliação **Real-ESRGAN 4× NCNN/Vulkan** foi mantido;
  não foi adotada a proposta de seleção automática entre ampliadores 2×/4×.

Detalhes em [Qwen Image 2.1 — modelo oficial](qwen-image21.md).

## Seleção de perfis mais limpa

Na mesma janela de configurações, aba **Stable Diffusion**, a antiga lista
longa de variantes deu lugar a **quatro cartões de modelo**. Clicar em um
cartão expande os presets diretamente abaixo, sem trocar o modelo selecionado.
Os presets disponíveis são:

| Modelo | Original | Variações |
| --- | --- | --- |
| Z-Image Turbo | 9 passos | 5 e 4 passos |
| FLUX.2 Klein 4B | 4 passos | 3 e 2 passos |
| FLUX 3 Image Klein | 16 passos | 8 e 5 passos |
| Qwen Image 2.1 | Turbo 8 passos | — |

A seleção ativa aparece destacada. A alteração manual de Steps, CFG, sampler
ou scheduler ativa **Custom settings** sem mudar a família. As opções de
componentes, memória e VAE permanecem na janela atual. Botões **Save** e
**Cancel** permanecem acessíveis durante a rolagem. Os nomes internos dos
presets continuam compatíveis com as preferências anteriores.

## Biblioteca e organização dos downloads

Uma única pasta de destino escolhida pelo usuário contém **uma subpasta por
modelo**, com nomes legíveis:

```text
<download folder>/
├── Z-Image Turbo/
├── FLUX.2 Klein 4B/
├── FLUX 3 Image Klein/
└── Qwen Image 2.1/
    ├── qwen-image-2.1-step90000-Q8_0.gguf
    ├── Qwen3VL-8B-Instruct-Q4_K_M.gguf
    ├── qwen_image_2.1_vae_bf16.safetensors
    ├── mmproj-Qwen3VL-8B-Instruct-F16.gguf
    └── chatrlabs-omni-turbo-8step-fp32.safetensors
```

- Presets de passos não duplicam os pesos: variantes da mesma família usam os
  mesmos arquivos.
- Arquivos importados **não são movidos nem copiados automaticamente**.
- Para uma instalação incompleta do Qwen, a biblioteca encontra as dependências
  já registradas e prepara apenas as ausentes. A Turbo LoRA pode ser baixada
  para a pasta organizada do Qwen mesmo quando o gerador já existe em outra.
- Downloads antigos com arquivos `.part` mantêm sua pasta original para
  permitir a retomada. O popAI também reconhece localizações legadas.
- A validação manual da LoRA confere a estrutura safetensors e a presença
  de tensores LoRA, além do controle de integridade do manifesto.

Consulte a [validação da biblioteca](model-library-validation.md) para o
histórico e os testes da evolução.

## Validação desta versão

| Verificação | Resultado |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | 41 testes aprovados |
| `node --test tests/frontend.test.cjs` | 17 testes aprovados |
| `node --check web/app.js` e compilação Python | Sem erros de sintaxe |
| Chromium headless com catálogo real | Seleção/expansão e modo Custom verificados |
| Qwen com todos os arquivos importados | Reconhecido como conjunto completo, sem cópia |
| Biblioteca simulada vazia | Cinco componentes preparados para download |
| Instalação parcial | Apenas a LoRA ausente incluída na fila simulada |
| Caminhos legados | Retomada de `.part` preservada |
| `git diff --check` | Sem erros |

Os testes de download usam filas simuladas e conferência de URLs/metadados;
**não houve novo download completo de 15,22 GB nem benchmark de geração real
com estes cinco componentes** nesta etapa. A interface foi verificada sem
abrir janelas no desktop. Configurações reais e modelos importados foram
preservados durante a validação.

## Referências

- [README](../README.md)
- [Qwen Image 2.1 — modelo oficial](qwen-image21.md)
- [Manifesto de downloads](../model-downloads.json)
- [Validação da biblioteca](model-library-validation.md)
- [Versão anterior 22.11.26](release-22.11.26.md)
