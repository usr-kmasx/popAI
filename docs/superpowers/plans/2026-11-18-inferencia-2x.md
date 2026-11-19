# Reduzir pela metade a espera pela imagem

**Objetivo.** Medir a aceleração de cada um dos três perfis desde o pedido até o PNG final. A versão de referência é a tag `18.11.26`, commit `94fb58e`. O alvo é entregar os mesmos pixels com a mesma seed, no máximo com o pico de VRAM da versão de referência.

**Estratégia.** Atacar primeiro as multiplicações de matrizes Q8 que dominam os passos na GPU. Medir à parte o tempo de colocar pesos à disposição do motor e o custo do Real-ESRGAN. Manter os pesos, os passos, o sampler, os previews e as resoluções de cada caso durante as comparações.

## 1. Medir o ponto de partida

- [x] Consultar gerações reais da RX 580 2048SP de 8 GiB, com motor já carregado, modo Leve, sem referências, base de 768 × 432 e saída de 3840 × 2160. A tabela usa a mediana por coluna. Os pedidos tinham prompts e seeds diferentes.

| Perfil Q8 | Pedidos | Passos | Geração da base | Ampliação | Pedido até PNG | Alvo de 2× |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FLUX.2 Klein 4B | 4 | 4 | 31,46 s | 14,91 s | 46,55 s | 23,27 s |
| Z-Image Turbo | 3 | 9 | 90,61 s | 15,46 s | 110,06 s | 55,03 s |
| FLUX.3 Image Klein | 8 | 16 | 113,35 s | 13,85 s | 127,90 s | 63,95 s |

- [x] Cronometrar uma geração base completa por perfil no motor original, com timestamps Vulkan por operação. Usar Euler, CFG 1, os schedulers do catálogo, seed `181126` e o prompt `A red ceramic cup on a wooden desk beside a window, soft morning light.` Cada processo recebeu o ambiente de compatibilidade do app, fez offload para RAM e emitiu preview por passo.

| Perfil | Tempo somado das operações Vulkan nos passos | Multiplicações Q8 | Atenção | Pico observado na placa |
| --- | ---: | ---: | ---: | ---: |
| FLUX.2 Klein 4B | 23,44 s | 19,08 s · 81,4% | 3,21 s | 5,92 GiB |
| Z-Image Turbo | 74,37 s | 62,37 s · 83,9% | 7,67 s | 7,33 GiB |
| FLUX.3 Image Klein | 90,94 s | 76,80 s · 84,5% | 10,26 s | 6,92 GiB |

Os percentuais usam só as operações que o Vulkan cronometrou entre o início e o fim da amostragem. Carregamento, esperas no host, VAE e ampliador têm custos próprios. Para repetir, usar os argumentos de `GenerationManager._generate` em `server.py` para o executor `sd-cli`, com `GGML_VK_PERF_LOGGER=1` e `GGML_VK_PERF_LOGGER_FREQUENCY=1`. Somar as linhas de operações entre `generating image` e `sampling completed`. A instrumentação sincroniza a GPU. O pico é da placa inteira, amostrado a cada 120 ms. Os logs locais, parâmetros e hashes RGB estão em `logs/perfil-2x-181126/`.

Se **apenas** as multiplicações Q8 passassem a levar metade do tempo, a soma dessas operações e das demais operações da GPU cairia, por cálculo, para 13,90 s no Klein 4B, 43,19 s no Z-Image e 52,53 s no FLUX.3. Isso equivale a aproximadamente 1,69–1,73× nos passos medidos. O tempo de entrega inclui também as etapas da primeira tabela.

## 2. Acelerar as multiplicações que mais pesam

O seletor fica em `backends/stable-diffusion.cpp/ggml/src/ggml-vulkan/ggml-vulkan.cpp`. O shader usado como ponto de partida é `vulkan-shaders/mul_mm.comp`, no mesmo diretório. O executor desta placa informa grupos de 64 threads, sem instrução de produto escalar inteiro acelerado nem núcleos de matrizes. As variantes precisam respeitar as capacidades que o driver reporta.

| Perfil | Primeira operação a otimizar (M × N × K) | Tempo acumulado dessa operação |
| --- | --- | ---: |
| FLUX.2 Klein 4B | 27648 × 1808 × 3072 | 10,24 s |
| Z-Image Turbo | 10240 × 1344 × 3840 | 26,72 s |
| FLUX.3 Image Klein | 18432 × 1376 × 3072 | 31,41 s |

- [x] Comparar o tamanho dos blocos nas três multiplicações mais caras do FLUX.3, com uma cópia temporária do motor. O caminho automático escolheu 64 × 64. No ensaio de dois passos, alternando original / 32 × 32 / 32 × 32 / original, os passos levaram em média **14,35 s** com 64 × 64 e **17,13 s** com 32 × 32. Os pixels da base foram idênticos nas quatro execuções. Diminuir o bloco levou 19,4% mais tempo nessa amostra. O resultado está em `logs/perfil-2x-181126/ensaio-blocos32-flux3.json`.
- [x] Verificar na CPU uma organização alternativa para as leituras Q8. O GGUF guarda uma escala de 2 bytes ao lado de 32 pesos de 1 byte. Em grupos de 32 blocos completos, guardar juntas as 32 escalas e depois os 1024 pesos permite ler quatro pesos alinhados por palavra de 32 bits. O grupo ocupa os mesmos 1088 bytes. Em amostras de três tensores reais, os 21.504 valores desquantizados em FP32 foram idênticos bit a bit. O ensaio na GPU está registrado abaixo.
- [x] Testar as duas leituras na RX 580 com os pesos reais. A disposição alternativa das escalas e dos pesos preservou a saída FP32 e usou o mesmo espaço para os pesos. Na ordem Klein 4B, Z-Image e FLUX.3, a mediana por multiplicação passou de 131,15 para 134,72 ms, de 37,53 para 43,73 ms e de 73,40 para 75,58 ms. A reorganização na CPU acrescentou de 6 a 28 ms por matriz testada. O aplicativo continua lendo o GGUF original.
- [x] Experimentar 14 geometrias de bloco e levar a de 64 × 128 ao fluxo completo. A triagem das matrizes isoladas serviu para selecionar a candidata. A referência para aceitar uma troca é o executável distribuído, que já escolhe uma geometria própria no RADV/GCN. Os resultados até a entrega estão na seção 4.
- [x] No Z-Image, fundir a leitura da entrada de `w1` e `w3` com a ativação. O hash dos 13.762.560 valores FP32 da saída da operação coincidiu com o original. Na geometria candidata, as projeções separadas levaram 93,26 ms e a fusão 90,57 ms, medianas de dez execuções por variante. O protótipo exige um caminho próprio para esses pesos. O ganho de 2,9% é restrito a essa operação.

## 3. Medir carregamento e transferências

No Klein 4B, o motor instrumentado concluiu a primeira base em 45,75 s e a segunda em 35,81 s. O processo leu cerca de 1,18 GiB do disco na primeira geração e zero bytes na segunda. A preparação síncrona de 1,80 GiB antes dos passos caiu de 10,56 s para 0,55 s. Durante a amostragem, o prefetch enviou 3,94 GiB em 26 chamadas por geração. Com o motor aquecido, as chamadas de envio ocuparam 1,15 s no host e a espera explícita pelas transferências somou 2 ms. Os tempos instrumentados podem se sobrepor ao trabalho da GPU.

No Z-Image, o contador do processo da primeira série original registrou cerca de 9,84 GiB de leitura física. A série candidata seguinte encontrou mais dados no cache do sistema. Por isso, o terceiro par inverteu a ordem e leu previamente os arquivos dos dois lados. O Z-Image levou 124,65 s com a candidata e 112,58 s com o original nesse par. Medir a primeira imagem isoladamente teria superestimado o ganho da candidata.

O prefetch existente continua ativo. Nos Klein, os blocos conjuntos dependem do latente e, no FLUX.3, parte das modulações depende do timestep. No Z-Image, as multiplicações Q8 de 32 tokens do prompt curto somaram 0,35 s durante os nove passos. O custo do refinador com texto longo e a troca de perfil dentro de uma única sessão continuam sem medição controlada. A política de cache do motor permanece a da versão de referência.

## 4. Comparar geração e edição até o PNG

Foram 22 gerações em 11 pares. Nove pares cobrem os três modelos em paisagem, no modo Leve, com base de 768 × 432 e entrega em 3840 × 2160. Cada modelo recebeu dois pares com processo novo e um com processo residente e prompt diferente. Nos outros dois pares, o Klein 4B recebeu uma referência e o FLUX.3 recebeu duas, em retrato no modo Muito leve. As dimensões e os hashes SHA-256 dos pixels RGB da base e do PNG final coincidiram nos **11 pares**.

| Perfil em paisagem | Mediana original | Mediana com bloco 64 × 128 | Variação pareada do tempo¹ | Maior pico observado, original / candidato |
| --- | ---: | ---: | ---: | ---: |
| FLUX.2 Klein 4B | 50,55 s | 47,00 s | −9,1% a +4,8% | 5,88 / 5,94 GiB |
| Z-Image Turbo | 124,90 s | 114,98 s | −14,9% a +10,7% | 7,34 / 7,40 GiB |
| FLUX.3 Image Klein | 138,50 s | 133,08 s | −7,5% a +6,8% | 7,05 / 6,98 GiB |

¹ Um valor negativo indica que a candidata entregou a imagem mais cedo. As medianas agrupam estados de carga diferentes. O pico é o da placa inteira, amostrado a cada 100 ms. Todos os modelos tiveram pelo menos um par em que a candidata demorou mais até a entrega.

Na geração da base, o bloco de 64 × 128 reduziu o tempo em três dos três pares do Klein 4B, três dos três do Z-Image e dois dos três do FLUX.3. Com o motor já carregado, os ganhos respectivos foram 1,82 s, 7,22 s e 1,98 s. No FLUX.3 com processo novo, um par levou 9,23 s a mais e o outro 10,33 s a menos. As bases e as imagens finais coincidiram em cada comparação.

Após a avaliação da geração separadamente, o bloco foi integrado ao caminho Vulkan escalar de multiplicação Q8_0 × FP32. A seleção ocorre por operação, no motor comum aos três modelos. O dispositivo precisa oferecer subgrupos de 64, grupos de trabalho de 256 na dimensão X e pelo menos 32 KiB de memória compartilhada. A seleção de blocos pequenos e grandes e os caminhos especializados do ggml continuam disponíveis. As medições de desempenho acima vieram de uma única GPU.

Com o executável distribuído, repetimos o caso FLUX.3 de seed `181126`. A base ficou pronta em 110,60 s e o PNG 4K em 119,69 s. Os dois hashes RGB coincidiram com os da versão de referência. Essa execução verificou a integração. Os tempos comparativos são os dos pares acima. A biblioteca recompilada também reproduziu os hashes das três multiplicações de referência e de uma multiplicação com saída de 45 × 77.

## 5. Ampliação e gravação do PNG

O perfil do Real-ESRGAN x4plus mediu 6,56 s somados nas camadas Vulkan de uma ampliação. As convoluções responderam por 88,75% desse tempo. Os dois operadores de redimensionamento anteriores a `Conv_1178` e `Conv_1182` somaram 13 ms. Uma fusão experimental preservou os pixels em uma e duas passagens. O custo medido dos dois redimensionamentos não justificou distribuir um grafo e convoluções específicos para esse modelo.

A mudança adotada foi escrever as linhas do recorte diretamente do buffer já redimensionado pelo ampliador. No Linux, a compilação com libpng oferece a opção `-P`. O executor grava o PNG sem perdas e o backend verifica a imagem antes de publicá-la. Um executor anterior usa a finalização existente. O manifesto do pedido registra as dimensões implícitas no formato intermediário para permitir retomar pedidos de ambas as versões.

| Medida na mesma imagem | Original | PNG direto |
| --- | ---: | ---: |
| Ampliação, ajuste e gravação de 768 × 432 para 3840 × 2160 | 8,69 s | 7,96 s |
| Somente gravação, validação e publicação de 3840 × 2160 | 1,27 s | 0,83 s |
| Mesma etapa com buffer de 3840 × 2176 e recorte para 3840 × 2160 | 4,31 s | 0,58 s |

A primeira linha usa duas execuções por versão em ordem A/B/B/A e pixels reais do Klein. O maior pico da placa foi 1,15 GiB nas duas versões, com diferença inferior a 2 MiB entre seus máximos. As duas últimas linhas isolam a etapa de CPU em três pares por geometria. Para testar o recorte, oito linhas de borda foram acrescentadas em cima e embaixo da mesma imagem. Em todos os casos o RGB final coincidiu. Nessa cena, o arquivo direto ocupou 7,32 MB. O original sem recorte ocupou 9,86 MB e o recorte regravado pelo Pillow ocupou 6,29 MB.

Também foram conferidos recortes com diferenças ímpares, escala de cinza, RGB e alfa, a retomada pela API a partir da base ou de cada formato de intermediário e o cancelamento nos dois lados da publicação atômica. Os resultados por execução estão em `logs/perfil-2x-181126/`. Os arquivos principais são `entrega-ab.jsonl`, `transferencias.jsonl`, `ampliador-publicado-ab.json` e `gravacao-4k.json`. A meta de 2× de ponta a ponta continua aberta.
