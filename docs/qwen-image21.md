# Qwen Image 2.1 — integração oficial do popAI

Versão de referência: [22-1.11.26](release-22-1.11.26.md).
Este documento descreve a variante oficial **Qwen Image 2.1 · ChatR Labs
Turbo**. Não se confunde com o Qwen normal e o antigo Turbo Unsloth dos
registros históricos [qwen-migration.md](qwen-migration.md) e
[qwen-turbo.md](qwen-turbo.md).

## Componentes

A família é configurada por um gerador Q8_0, encoder Qwen3-VL 8B Q4_K_M,
VAE BF16, projetor de visão F16 e Turbo LoRA de 8 etapas. Os cinco arquivos,
seus nomes exatos, fornecedores, revisões, tamanhos e hashes SHA-256 estão em
[`model-downloads.json`](../model-downloads.json).

Abra **Settings → Models**, escolha uma pasta de download e use **Download /
Resume** no cartão Qwen. Se o conjunto já estiver completo em uma pasta
registrada, o popAI reutiliza os arquivos sem transferi-los. O modelo ocupa
aproximadamente **15,22 GB** no total.

Arquivos baixados pelo aplicativo ficam juntos em uma pasta chamada
`Qwen Image 2.1` abaixo do destino escolhido. Os arquivos já importados
permanecem onde estão. A LoRA é procurada primeiro junto ao gerador e depois
nas pastas cadastradas; quando estiver ausente, o download usa a pasta
organizada do Qwen. O `sd-cli` recebe o diretório real da LoRA, portanto não
é preciso mover manualmente gerador, encoder, VAE ou adaptador.

O identificador `qwen-image21-experimental` é mantido **somente no código e
nos dados persistidos**, para não invalidar seleções e jobs anteriores.

## Preset e execução

O preset visual é **Turbo · 8 steps**: Euler, CFG 1, scheduler `simple`.
O `sd-cli` carrega o modelo por geração e recebe a Turbo LoRA pelo nome
`<lora:chatrlabs-omni-turbo-8step-fp32:1>`. A interface expõe o Qwen junto
aos outros três modelos, em cartão com variantes expansíveis. O usuário
pode alterar amostragem e ativar Custom sem modificar arquivos de peso.

## Edição por referência

O Qwen aceita até 10 imagens enviadas pelo botão **+** ou pelo editor de
sketch do popAI. O projetor visual correspondente é necessário. O servidor
cria **cópias temporárias** das entradas, reduzindo o maior eixo a no máximo
512 pixels e preenchendo com branco até múltiplos de 32 sem distorcer a
proporção. Os PNGs originais enviados pelo usuário não são sobrescritos.

As dimensões internas do resultado também podem ser alinhadas a múltiplos
de 32; o excedente é recortado antes da ampliação. No hardware com pouca
VRAM, o caminho de referência utiliza CPU para o encoder de texto/visão e
VAE e Vulkan para difusão. O restante do pipeline de ampliação permanece
igual ao de outros modelos; **não há ampliação adaptativa**.

## Compatibilidade e limites

- Downloads retomáveis usam `.part` e publicação somente após a verificação
  de integridade. Arquivos anteriores e downloads legados são preservados.
- Em instalações parciais, o conjunto só é marcado como completo com os
  cinco componentes presentes. Se faltar a LoRA, o popAI mostra a pendência.
- Os presets com números de passos diferentes não criam cópias dos pesos.
- Testes automatizados validam identificação, seleção, caminhos, parâmetros
  de execução, edição e organização da biblioteca. Não substituem a medição
  de qualidade ou desempenho de uma geração real.

Para instruções de instalação e compilação, use o [README](../README.md).
