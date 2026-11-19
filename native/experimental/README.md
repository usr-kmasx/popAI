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
