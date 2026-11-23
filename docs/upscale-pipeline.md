# Geração e ampliação por IA em etapas

> **Histórico técnico.** Esta página registra a experiência inicial com 2×.
> Na versão [22-1.11.26](release-22-1.11.26.md), o upscaler ativo é o
> Real-ESRGAN NCNN/Vulkan 4×. A proposta de escolha automática entre modelos
> de ampliação foi apenas planejada e **não foi implementada**.

O usuário aprovou gerar em 960×544 com o Klein, encerrar o processo e depois
carregar um ampliador 2×. Manter um input, mostrar a etapa atual e salvar em
1920×1080. Nenhuma instalação no sistema; geração real na GPU será testada por ele.

Atualização de precisão: gerador ativo FLUX.2 Klein 4B **Q8_0**, arquivo
`flux-2-klein-4b-Q8_0.gguf` da Unsloth (4.300.644.928 bytes). Substitui o Q4_K_M
somente no gerador. Encoder, VAE, ampliador, dimensões, amostragem e orçamento
de memória permanecem iguais. O Q4 foi preservado no SSD. Hash e revisão ficam
em `sources.json`; geração real em Q8 e seu pico de VRAM ficam para o usuário.

## Fluxo e interfaces

- Klein: Euler, 4 passos, CFG 1, scheduler flux2, 960×544; salva `ID-base.png`.
- O servidor aguarda o processo encerrar e valida a intermediária antes de seguir.
- Outro `sd-cli -M upscale` carrega apenas o ESRGAN, via `--upscale-model`; não
  recebe gerador, encoder ou VAE. Amplia em blocos de 128 pixels no Vulkan0.
- Validação obrigatória de 1920×1088 no resultado. O navegador só recorta as
  quatro linhas de cada borda vertical, com cópia 1:1 para PNG 1920×1080.
- `state=running` permanece durante as duas etapas; `phase=generating` ou
  `phase=upscaling` informa o texto de progresso. Durações de cada etapa ficam
  em `generation_seconds` e `upscale_seconds`, além do tempo total.
- Uma execução por vez, limite total de 30 minutos, encerramento do processo ativo
  por Ctrl+C/SIGTERM. Falha de geração impede ampliação; falha de ampliação nunca
  é apresentada como sucesso, e a imagem intermediária é preservada.

## Ampliador e compatibilidade

**2xNomosUni esrgan multijpg**, autor **Philip Hofmann**, licença **CC BY 4.0**.
Fonte: https://github.com/Phhofm/models/releases/tag/2xNomosUni_esrgan_multijpg
Arquivo `.safetensors`, 33.478.206 bytes, SHA-256:
`d71c55cc1c70fbb7ac42a25e37bcb99a46672de0bc750924bea81e57c163b5ab`.
Hash conferido também nos metadados do repositório do autor Phips no Hugging Face,
revisão `6d4be1a90e2f272053f2402b74df8977acd12e44`.

Esse ESRGAN usa pixel-unshuffle RGB: transforma a entrada em 12 canais antes da
rede interna 4×, resultando em uma ampliação efetiva 2×. O motor não implementava
essa preparação. O ajuste local detecta os canais, prepara a imagem **inteira antes
da divisão em blocos**, usa a escala interna para o processamento e a escala
efetiva para a saída. Isso evita que origens de blocos ímpares alterem o agrupamento
de pixels e introduzam emendas. O caminho 4× existente permanece sem alteração.

Fontes e patch preservados dentro do projeto. O executável foi recompilado
localmente; não houve instalação de pacotes nem alteração de drivers.

## Verificação

- Testes simulados verificam dois comandos separados, PID do gerador já encerrado
  antes de iniciar o ampliador, fases, concorrência, falhas em ambas as etapas,
  validação de tamanho e encerramento durante ampliação.
- Testes JavaScript cobrem a fase “Ampliando com IA”, o campo bloqueado e o recorte
  final sem nova ampliação no navegador.
- Teste C++ verifica a ordem dos pixels no unshuffle para canais e batches.
- Teste nativo na CPU com pesos sintéticos e blocos pequenos reproduziu a falha de
  alinhamento (erro máximo de 11 níveis por pixel); valida o resultado corrigido
  contra pixels conhecidos, com tolerância de um nível pelo arredondamento.
- Modelo real em teste sintético **CPU**: 8×8 → 16×16, em cerca de 0,24s de
  processamento. Isso verifica compatibilidade e dimensões, não prevê o tempo
  de ampliação de um wallpaper na RX 580. Nenhuma geração real na GPU foi feita.

Referências medidas pelo usuário: ~37s para Klein em baixa resolução e 228s para
1080p nativo. O tempo e a qualidade do fluxo novo ficam para sua comparação.
