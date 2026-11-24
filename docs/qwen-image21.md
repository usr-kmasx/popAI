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

A seleção contém **Original · 8 steps** e **Fast · 4 steps**.
Ambos usam os mesmos arquivos e Turbo LoRA, Euler, CFG 1 e scheduler
`simple`; apenas `--steps` muda. Em uma comparação controlada de uma
mesma cena (seed `20261122`, 768 × 448), os tempos totais medidos foram
aproximadamente **120 s e 80 s**, respectivamente. Isso é um resultado
específico, não uma garantia de qualidade nem de velocidade.
O **motor residente `sd-server`**, já utilizado pelos outros modelos do popAI,
agora também é o padrão para o Qwen. Após uma geração, os pesos permanecem
carregados para as próximas solicitações enquanto o aplicativo estiver aberto e
as configurações de carregamento não mudarem. As duas variantes reutilizam o
mesmo processo; só as opções de amostragem da requisição são alteradas.

No `sd-server`, a Turbo LoRA é passada pelo campo estruturado `lora` da API;
o diretório é enviado via `--lora-model-dir`. Diferentemente do `sd-cli`, o
servidor não interpreta tags `<lora:...>` inseridas no prompt. O popAI mantém
o caminho `sd-cli` para execuções com persistência desativada. As configurações
de GPU Vulkan, uso de RAM, distribuição automática dos pesos, `mmap`, VAE tiling,
sampler, scheduler e CFG continuam sendo respeitadas.

A interface expõe o Qwen junto aos outros dois modelos, em cartão com variantes
expansíveis. O usuário pode alterar amostragem e ativar Custom sem modificar
arquivos de peso.

## Edição por referência

O Qwen aceita até 10 imagens enviadas pelo botão **+** ou pelo editor de
sketch do popAI. O projetor visual correspondente é necessário. O servidor
cria **cópias temporárias** das entradas, reduzindo o maior eixo a no máximo
512 pixels e preenchendo com branco até múltiplos de 32 sem distorcer a
proporção. Os PNGs originais enviados pelo usuário não são sobrescritos.

As dimensões internas do resultado também podem ser alinhadas a múltiplos
de 32; o excedente é recortado antes da ampliação. Com ou sem imagens de
referência, a difusão, o encoder de texto/visão e o VAE usam o backend Vulkan
selecionado. A distribuição dos pesos entre RAM e VRAM continua obedecendo
às mesmas opções gerais dos demais modelos (`--auto-fit` ou
`--offload-to-cpu`), sem limite extra ou política especial para o Qwen.
Ao alternar entre geração por texto e edição, o motor residente reinicializa
o contexto quando necessário para carregar o projetor visual; gerações
seguintes com a mesma configuração reutilizam o processo. O restante do
pipeline de ampliação permanece igual ao de outros modelos; **não há
ampliação adaptativa**.

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
