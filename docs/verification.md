# Histórico: verificação inicial com DreamShaper — 2026-11-17

Este registro é anterior aos modelos atuais. As trocas históricas constam de
`qwen-migration.md` e `flux-klein.md`; o conjunto oficial atual está descrito
em [22-1.11.26](release-22-1.11.26.md). Os tempos abaixo são do DreamShaper.

- Compilação Release Vulkan concluída com sucesso dentro do projeto.
- Executável: `backends/stable-diffusion.cpp/build/bin/sd-cli`.
- Versão: `master-1106-532d2c1`, commit `532d2c15c430a785a712b2d94281f04e733008a4`.
- GPU real detectada: AMD Radeon RX 580 2048SP, RADV POLARIS10, Mesa 26.2.7.
- Checkpoint DreamShaper 8 de 2.132.625.894 bytes, SHA-256 conferido contra
  os metadados do repositório oficial. Versões e hashes em `sources.json`.

## Teste real completo

Descrição de um lago entre montanhas ao nascer do sol, floresta e neblina.
Executado pelo campo da interface, pressionando Enter. Configuração: Euler,
20 passos, CFG 7, semente aleatória, tipo solicitado f32, Vulkan0.

O segundo teste terminou em aproximadamente **38 segundos**, incluindo carregar
o modelo. A interface exibiu a imagem e liberou o campo para outro pedido.
O download foi acionado pelo navegador e o arquivo PNG foi verificado em
**1920×1080**. Cópia do teste em `outputs/wallpaper-test-1920x1080.png`.
Imagem original em `outputs/4c963bc12588471ba43773a358c7e25f.png` (768×448).
Registro em `logs/4c963bc12588471ba43773a358c7e25f.log`.

O primeiro teste mostrou que o motor alinha 768×432 para 768×448. A integração
foi ajustada para solicitar 768×448 e recortar 8 pixels no topo e embaixo no
navegador, antes da ampliação. O download preserva a proporção 16:9 e corresponde
à imagem exibida. Não é geração nativa em 1080p nem super-resolução por IA.

## Testes automatizados e interface

- 8 testes Python passaram: validação, texto literal no subprocesso, uma geração
  por vez, falha de execução/saída, arquivos ausentes, rotas HTTP, restrição de
  origem/caminho e encerramento dos subprocessos por SIGTERM e SIGINT.
- 1 teste JavaScript passou: falha ao abrir resultado mantém o campo disponível
  e não repete a tentativa em todos os ciclos de consulta.
- Sintaxe de Python, JavaScript e scripts de inicialização/compilação verificada.
- Layout conferido no navegador em tela estreita e em 1280×800; apenas um input.
- Captura final em `docs/interface.jpg`. Removido backdrop-filter do input para
  evitar artefato visual na composição sobre a imagem.

Não foram instalados pacotes no sistema nem alterados drivers ou configurações
globais. CMake, cabeçalhos, fontes, modelo, executável e cache ficam no projeto.
O tempo medido é específico deste teste; outras descrições e condições de uso
podem variar. O servidor usa um processo por pedido e recarrega o modelo.
