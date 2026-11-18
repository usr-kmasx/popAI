# Validação real — 2026-11-17

Testes locais com os pesos oficiais existentes no SSD, RX 580 2048SP de 8 GiB,
Vulkan, offload para RAM e modo Leve. Configurações de teste isoladas das
configurações do usuário. Registros em `logs/validation-20261117-220942/`.

| Caso | Base | PNG final | Tempo total |
| --- | --- | --- | --- |
| Klein Q8, carregamento inicial após correção | 768×432 | 1920×1080 | 46,0 s |
| Klein Q8, motor reutilizado | 768×432 | 1920×1080 | 45,0 s |
| Klein Q8, edição com referência, 5 passos | 768×432 | 1920×1080 | 81,7 s |
| Z-Image Turbo Q8, carregamento inicial | 432×768 | 1080×1920 | 102,6 s |
| Z-Image Turbo Q8, motor reutilizado, 4K vertical | 432×768 | 2160×3840 | 118,4 s |

Os tempos incluem a geração e a ampliação Real-ESRGAN NCNN. A saída 4K é
ampliada, não gerada nativamente nessa resolução. São medições destes pedidos,
não médias nem promessa de desempenho em outros computadores.

## Resultados

- Todos os PNGs finais foram decodificados e suas dimensões conferidas.
- Edição inspecionada visualmente: a cabana, o lago e a composição foram
  preservados e a cena recebeu neve, conforme o pedido.
- O mesmo processo nativo do Klein foi reutilizado na geração seguinte e na
  edição, inclusive alterando passos e selecionando parâmetros personalizados.
- O mesmo processo do Z-Image foi reutilizado ao trocar a resolução final.
- Download pelo botão do navegador: PNG 1920×1080 em
  `/home/usr/Downloads/wallpaper-1920x1080.png`, com SHA-256 idêntico ao preview.
- Contagem por passos e progresso percentual do ampliador observados na interface.
- Cancelamento durante amostragem real: 0,273 s; motor e supervisor encerrados.
- Atualizar a página ocultou o resultado e o botão de download.
- Nenhum PNG foi escrito no diretório permanente de saída do servidor de teste.
- Fechamento durante uma geração ativa: motor encerrado, diretórios temporários
  removidos e arquivo de configuração original preservado byte a byte. Servidor
  de teste encerrado ao final.
- Pico observado de VRAM total: 5,90 GiB no Klein e 7,28 GiB no Z-Image,
  incluindo o ambiente gráfico e outros consumidores. Não representa memória
  exclusiva de pesos, nem garantia de permanência integral dos pesos na GPU.

## Correção encontrada durante os testes

O primeiro teste revelou que o motor persistente era encerrado quando a thread
Python do pedido terminava. No Linux, `PR_SET_PDEATHSIG` acompanha a thread
criadora. O supervisor nativo passou a acompanhar a vida do processo Python,
mantendo o motor vivo entre pedidos e encerrando-o quando o app fecha.

O executável foi recompilado e os testes reais seguintes confirmaram a
reutilização. A compilação do supervisor e da sondagem Vulkan também foi
incluída em `build.sh`. Saída 137 agora recebe o diagnóstico de processo morto.
O registro `klein-cold.json` é o teste anterior à correção; os demais casos
listados na tabela foram executados depois dela.

## Verificação automatizada e escopo

- 18 testes existentes de backend passaram, incluindo uma regressão para o
  encerramento da thread criadora sem matar o motor persistente.
- 6 testes de interface passaram.
- Sintaxe dos módulos Python alterados e de `build.sh` conferida.
- Código próprio licenciado em MIT no arquivo `LICENSE`; licenças dos modelos
  e executores preservadas e distinguidas no README.
- Distribuição/instalador continua adiada por decisão do usuário. Não foram
  instalados pacotes, movidos pesos ou criados commits.

O fechamento durante uma geração ativa e a preservação das configurações são
registrados separadamente em `shutdown-active.json` e `shutdown.json`.
Esta validação cobre os casos e o hardware descritos; não comprova compatibilidade
com todas as GPUs ou todos os presets.
