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
