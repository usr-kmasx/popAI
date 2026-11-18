# Troca para Qwen Image 2.1 — 2026-11-17

Histórico da troca para Qwen normal. O modelo ativo passou a ser Turbo conforme
`qwen-turbo.md`; os parâmetros abaixo documentam a etapa anterior.

Pedido: substituir o conjunto completo do DreamShaper pelo Qwen existente no SSD,
mantendo a interface. O usuário fará a geração; não carregar modelos reais para
testes, não deixar servidor em execução e não instalar nada no sistema.

## Identificação e carregamento

Pasta: `/run/media/usr/dados/Models/IMG/Qwen-Image-2.1-Turbo-Quantized`.
O nome da pasta não define a variante. O SHA-256 do gerador é:

```text
631d532e7ca71e8d90a87c71d3699761a812039d22e3370e87498d87754660fe
```

Ele corresponde ao arquivo publicado pela Unsloth como Qwen Image 2.1 normal:
https://huggingface.co/unsloth/Qwen-Image-2.1-GGUF/blob/main/qwen-image-2.1-Q4_K_M.gguf

O servidor recebe uma pasta de modelos, valida a presença dos três arquivos antes
de iniciar o pedido e usa `--diffusion-model`, `--llm` e `--vae` separadamente.
O caminho padrão aponta ao SSD; `--model-dir` permite mudar o ponto de montagem.
Sem cópia dos pesos, alteração no SSD ou dependência dos pesos antigos do DreamShaper.

## Configuração

- Modelo normal: Euler, 20 passos, CFG 6, seed aleatória. Sem sigmas Turbo.
- GGUF preservado sem `--type f32`; removido o prompt negativo fixo do DreamShaper.
- `diffusion=Vulkan0,te=cpu,vae=Vulkan0`; orçamento de VRAM de 6 GiB.
- Pesos na RAM com offload, mmap, VAE em blocos e cache de contexto q8_0.
- 768×448; interface mantém recorte ao centro e exportação 1920×1080.
- API local, um pedido por vez e encerramento dos processos mantidos.

As escolhas de memória destinam-se à RX 580 8 GB, sem garantir consumo ou tempo
antes do teste real. O encoder CPU pode aumentar o tempo do pedido. Não foi feita
conversão dos GGUF nem modificada a compilação existente, que suporta Qwen 2.1.

## Verificação

- Testes usam somente executáveis simulados; nenhum modelo real foi carregado.
- Validação dos três componentes, argumentos separados, preservação do prompt,
  concorrência, arquivos ausentes, falhas, HTTP e SIGTERM/SIGINT.
- Teste JavaScript da recuperação de erro da imagem preservado.
- Opções conferidas na ajuda do executável compilado e na documentação local.
- Revisão independente sem problemas importantes encontrados.

O teste real de geração e seu tempo ficam para o usuário. O resultado de 38s
do teste anterior refere-se exclusivamente ao DreamShaper.
