# Experimentos de tempo de geração

O ponto de retorno é o commit `5a9ed09`, tag `pre-arquitetura-geracao-2x`. O aplicativo e os executáveis de distribuição continuam usando esse motor. Os testes abaixo foram feitos fora do servidor do usuário.

## Multiplicação Q8 por produtos externos

`q8-outer-product.comp` é um protótipo Vulkan para multiplicar pesos Q8_0 por ativações FP32. Cada grupo carrega um trecho de 32 coeficientes em memória compartilhada, reorganiza os dados por par de coeficientes e acumula quatro linhas por invocação em registradores. O protótipo usa a interface de buffers e constantes do ggml e a ordem de acumulação do caminho escalar para esse formato. Foi exercitado com os blocos da bancada, sem integração ao seletor de produção.

Compilação isolada com `glslc -fshader-stage=compute --target-env=vulkan1.2 -O q8-outer-product.comp -o /tmp/popai-q8-outer.spv`. As medianas das multiplicações principais em milissegundos foram 143,09 → 193,09 no Klein, 75,14 → 98,34 no FLUX.3 e 44,39 → 66,51 no Z-Image. Os hashes da saída FP32 conferiram. O protótipo foi descartado para distribuição.

## Previsão dentro de cada pedido

O modo Spectrum já existe no stable-diffusion.cpp. Foi usado como referência para testar a troca de avaliações completas por estimativas a partir dos passos daquele pedido. Cada imagem recebeu prompt diferente e seed sorteada pelo servidor ou por um gerador aleatório do sistema. A primeira imagem produzida foi a amostra avaliada. Os campos abaixo se aplicam exclusivamente ao corpo da requisição experimental de geração do sd-server.

```json
{"cache_mode":"spectrum","cache_option":"warmup=2,window=3,flex=0.25,stop=0.9,m=2"}
```

| Base e modelo | Controle | Previsão | Observação |
| --- | ---: | ---: | --- |
| Klein, 768 × 432, primeira base | 35,93 s | 25,30 s | Processos novos |
| Klein, 768 × 432, segunda base | 37,04 s | 24,38 s | Mesmo motor de cada série, outro pedido |
| FLUX.3, 256 × 144 | 18,67 s | 13,25 s | Mesmo motor, previsão primeiro, sem ampliação |

No Klein, o motor estimou 1 dos 4 passos. A canoa e a margem de pedras são reconhecíveis na primeira imagem. Na segunda, o relógio aparece, mas os numerais estão irregulares e a contagem dos mapas dobrados é ambígua. No FLUX.3, o motor estimou 8 dos 16 passos. A amostra apresenta o veleiro amarelo e a boia vermelha pedidos. Amostras independentes permitem verificar aderência ao texto e defeitos visíveis. Elas não separam a variação da seed de uma possível perda causada pela aproximação. A triagem pequena também não estabelece o ganho em resolução de uso.

Medições locais em `logs/perfil-2x-181126/`. A bateria longa foi encerrada após os dois pedidos aproximados do Klein. Os testes seguintes usaram 256 × 144 sem ampliador. Não há medição de geração aproximada do Z-Image.

Uma terceira solicitação inédita de 256 × 144 no FLUX.3 usou `warmup=2,window=8,flex=0,stop=0.98,m=2`. O motor avaliou 4 passos completos e estimou 12. A base levou **7,23 s** após a inicialização do servidor. A referência de 18,67 s acima foi outro pedido, com o mesmo número de passos e a mesma resolução. O barco verde e a boia amarela aparecem. A amostra tem pouco contraste e a ligação do barco à boia é difícil de distinguir. Como se trata de um único pedido desse modo, o resultado de 2,58× é exploratório. O modo fica isolado para avaliação visual.

## Reuso exato do texto por pedido

Triagem com os perfis Vulkan já gravados na RX 580, base de 768 × 432. No trecho entre `get_learned_condition completed` e `sampling completed`, somamos a duração agregada de cada linha de multiplicação por largura de sequência (`n`). Os totais representam operações da GPU. Outras operações e transferências ficam fora dessa soma.

| Modelo | Passos | Multiplicações na largura do texto | Multiplicações após juntar texto e imagem | Tempo dos passos |
| --- | ---: | ---: | ---: | ---: |
| Z-Image Turbo | 9 | 0,35 s (24 ou 32 posições) | 54,80 s (1344 posições) | 88,57 s |
| FLUX.3 Klein | 16 | 1,40 s (80 posições) | 64,66 s (1376 posições) | 95,24 s |

A projeção inicial do texto do Z-Image (3840 × 24 × 2560) aparece nove vezes no registro. As multiplicações do ramo textual somam cerca de 0,4% do tempo dos passos nesse prompt curto. Isso confirma repetição, mas dá pouca sustentação para acelerar a geração inteira somente por essa via. Os registros não medem a economia de transferências de uma implementação de reuso, nem validam igualdade dos pixels. Não houve publicação de um novo modo.

## Disposição dos pesos na memória compartilhada da GPU

Testamos duas formas de distribuir os mesmos pares FP32 do peso Q8 decodificado entre as posições de memória do grupo Vulkan. Uma permuta a coluna com XOR da linha. A outra transpõe linha e coluna e permuta a linha. Ambas mantêm a ordem das somas e os pesos originais. A multiplicação isolada usou `layers.0.feed_forward.w1.weight` do Z-Image, K=3840, M=10240, N=1344, com a geometria larga de produção na RX 580. Cada série teve dois aquecimentos e nove medições. Executamos as três alternativas em ordem direta e inversa.

| Disposição | Mediana da primeira série | Mediana da segunda série |
| --- | ---: | ---: |
| Original | 34,38 ms | 36,34 ms |
| Coluna permutada | 52,12 ms | 46,59 ms |
| Transposta com linha permutada | 41,58 ms | 48,28 ms |

O SHA-256 dos 13.762.560 valores FP32 da saída coincidiu nas seis séries. As duas alternativas foram mais lentas que o controle nas duas ordens. A triagem terminou no bloco, sem gerar imagens. Dados brutos em `logs/perfil-2x-181126/q8-local-layout.json`.

## Projeções de entrada juntas nas camadas principais do Z-Image

Comparamos as projeções Q8 W1 e W3 seguidas de SwiGLU com o protótipo que calcula as duas e grava diretamente sua combinação. O controle usa a geometria Vulkan larga do app. Usamos os pesos reais de duas camadas, ativações sintéticas idênticas entre modos e nove medições após dois aquecimentos por série. Em cada caso invertemos a ordem para a segunda comparação. Os valores abaixo são as medianas de cada série em milissegundos.

| Camada e largura de sequência | Separadas | Juntas |
| --- | --- | --- |
| 0, 1344 posições | 88,94 / 89,92 | 88,08 / 88,05 |
| 12, 608 posições | 32,27 / 32,48 | 32,18 / 32,45 |

O hash da saída FP32 coincidiu em cada comparação. No primeiro tamanho, a média das duas medianas caiu cerca de 1,5%. No segundo, cerca de 0,2%. A variação entre medições individuais excede essas diferenças. Sem evidência de um ganho material, a triagem terminou sem integrar o protótipo nem gerar imagens. Dados brutos em `logs/perfil-2x-181126/ff-camadas-principais.json`.

## Distribuição de pesos com os modelos originais

A opção experimental usa o planejamento nativo de memória no motor Vulkan. Ao desativá-la, o app volta a solicitar armazenamento inicial dos pesos em RAM. O botão começa desligado. O planejador pode escolher RAM para todos os componentes, como ocorreu nos cinco pares da RX 580. Os cálculos continuam na GPU escolhida.

Três pedidos inéditos com Z-Image verificaram o primeiro carregamento e mais dois pedidos na mesma sessão. Um pedido por Klein verificou a integração pelo app com processo novo. Usamos a mesma seed nos dois lados de cada par, base 256 × 144, preview por passo e Real-ESRGAN até 1280 × 720. Os hashes RGB da base e do PNG entregue coincidiram em todos os cinco pares.

| Modelo e pedido | Base padrão / experimental | Até o PNG padrão / experimental |
| --- | ---: | ---: |
| z-image-turbo · 1 | 18.17 / 16.96 s | 32.09 / 30.75 s |
| z-image-turbo · 2 | 15.65 / 15.95 s | 30.41 / 30.03 s |
| z-image-turbo · 3 | 16.87 / 16.55 s | 31.41 / 31.53 s |
| klein · 1 | 13.64 / 16.05 s | 27.66 / 30.13 s |
| flux3-klein · 1 | 23.17 / 22.67 s | 40.13 / 38.65 s |

Os tempos mistos não demonstram aceleração consistente. A tentativa separada de converter W1 e W3 das quatro primeiras camadas para FP32 aumentou a memória dos parâmetros de difusão em 881 MiB e alterou os pixels nos três pares do Z-Image. Ela foi descartada. Dados locais em `logs/perfil-2x-181126/pesos-preparados-pares.jsonl` e `pesos-ui-klein.jsonl`.

## Passagem direta entre passos do Z-Image

A primeira etapa do plano mediu o caminho atual. O patch [trace-zimage-euler.patch](trace-zimage-euler.patch) adiciona um registro por passo com `POPAI_TRACE_EULER=1`. Aplique o patch com `patch -p1` em uma cópia do fonte do stable-diffusion.cpp e compile os executáveis dessa cópia com o Vulkan. Para esta medição, recompilamos e religamos `execution_engine.cpp` e `diffusion_engine.cpp` em executáveis isolados, usando as opções e bibliotecas da compilação atual. Os executáveis do app ficaram fora do experimento.

O Z-Image Turbo Q8 usou Euler, nove passos, CFG 1, preview projetado em cada passo, offload para RAM e a política Vulkan padrão da RX 580. O primeiro pedido, de 256 × 144, abriu o motor residente. O segundo, de 960 × 544 (Padrão), usou o mesmo motor com outro prompt. Ambos passaram pela ampliação e publicaram um PNG de 1280 × 720.

| Soma dos nove passos | 256 × 144 | 960 × 544 |
| --- | ---: | ---: |
| Leitura da saída do modelo para RAM | 0,671 ms | 2,119 ms |
| Envio do latente de entrada | 0,038 ms | 0,459 ms |
| Escalas e combinação na RAM | 0,111 ms | 1,811 ms |
| Atualização de Euler na RAM | 0,092 ms | 1,132 ms |
| **Subtotal da passagem** | **0,912 ms** | **5,521 ms** |
| Produção do preview e callback | 1,423 ms | 15,727 ms |
| Sincronizações explícitas após submissão e no fim do último segmento | 14,924 ms | 21,031 ms |
| **Soma incluindo preview e sincronizações** | **17,259 ms** | **42,279 ms** |
| Tempo até a imagem base | 27,69 s | 133,12 s |
| Tempo até o PNG | 41,17 s | 145,11 s |
| Pico de VRAM da placa inteira | 7,33 GiB | 7,26 GiB |

As sincronizações medidas podem incluir espera por cálculos necessários. A soma também não inclui esperas internas durante a execução serializada das operações Vulkan. Esse tempo pertence à execução do grafo e exigiria outro experimento para avaliar sobreposição. Em 960 × 544, a leitura da saída transferiu 522.240 bytes por passo. O envio do latente foi medido também quando ocorreu em memória acessível pela CPU.

A base e o PNG do pedido pequeno coincidiram em SHA-256 dos pixels RGB com o registro anterior do mesmo prompt, seed 2065121 e configuração. Essa comparação valida a instrumentação. A geração no Padrão mediu custo, sem comparação com uma implementação de dois buffers.

Mesmo incluindo preview e sincronizações explícitas, o total medido no Padrão equivaleu a cerca de 0,032% do tempo até a base. A meta de 10% representaria 13,31 s nesse pedido. Encerramos na etapa de medição conforme o critério do plano. A passagem com dois buffers e o botão ficaram fora do app. Dados por passo em `logs/perfil-2x-181126/execucao/trace-euler-z-image-turbo-stock/resident.log` e tempos e hashes em `logs/perfil-2x-181126/passagem-euler-controle.jsonl`.

## Sobreposição do fim e do começo de passos consecutivos

Medimos um pedido Z-Image Turbo Q8 com Euler, nove passos, base de 960 × 544, preview por passo e ampliação até 1280 × 720 na RX 580. Usamos a seed `5240132` e o mesmo prompt do pedido de referência em resolução Padrão. O controle de compatibilidade Vulkan continuou ativo. Os hashes RGB da base e do PNG final coincidiram com os da referência.

Aplicamos [trace-vulkan-operation-order.patch](trace-vulkan-operation-order.patch) e [trace-zimage-euler.patch](trace-zimage-euler.patch) apenas aos executáveis de diagnóstico. O primeiro expõe os timestamps em ordem quando `POPAI_TRACE_VULKAN_ORDER=1` e `GGML_VK_PERF_LOGGER=1`. Usamos o modo não concorrente do profiler para identificar cada operação. O segundo registra a fronteira de cada passo com `POPAI_TRACE_EULER=1`. Entre o início da amostragem e cada marcador conferimos 1.289 operações e 34 atenções sobre a imagem por passo. Quatro atenções do refinador cobriram as 2.048 posições de imagem com padding. Trinta atenções conjuntas cobriram 2.080 posições, incluindo o texto.

Para cada transição, comparamos o intervalo entre a última atenção global e a saída do passo anterior com o intervalo entre a entrada do passo seguinte e sua primeira atenção global. Os intervalos da tabela incluem as lacunas entre operações, além do trabalho que poderia ter dependências mais restritivas. Usar o menor dos dois intervalos é uma estimativa otimista do tempo que poderia ser escondido por essa sobreposição.

| Transição | Fim do passo anterior | Início do passo seguinte | Sobreposição ideal |
| --- | ---: | ---: | ---: |
| 1 → 2 | 248,083 ms | 83,147 ms | 83,147 ms |
| 2 → 3 | 243,533 ms | 107,636 ms | 107,636 ms |
| 3 → 4 | 263,529 ms | 85,048 ms | 85,048 ms |
| 4 → 5 | 248,186 ms | 88,688 ms | 88,688 ms |
| 5 → 6 | 250,871 ms | 109,933 ms | 109,933 ms |
| 6 → 7 | 250,553 ms | 103,324 ms | 103,324 ms |
| 7 → 8 | 260,650 ms | 98,900 ms | 98,900 ms |
| 8 → 9 | 267,114 ms | 85,248 ms | 85,248 ms |
| **Total ideal** | | | **761,924 ms** |

A referência levou 133,12 s até a base. A meta de 10% equivale a 13,31 s nesse pedido. A janela total equivale a 0,57% e ficou abaixo também do mínimo absoluto de 2 s. Os 129,95 s do pedido instrumentado são um tempo de diagnóstico, com outro estado do motor, e não representam ganho de sobreposição. O experimento encerrou antes do protótipo de execução paralela. O aplicativo e os executáveis de produção ficaram fora da mudança.

Registros em `logs/perfil-2x-181126/execucao/trace-vulkan-overlap-z-image-turbo-stock/resident.log`, `sobreposicao-vulkan-limite.json` e `sobreposicao-vulkan-controle.jsonl`.
