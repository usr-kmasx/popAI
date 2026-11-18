# popAI — implementação local

Registro da implementação inicial. A substituição posterior do DreamShaper pelo
Qwen completo está em `qwen-migration.md`. A seleção ativa posterior do Klein
está documentada em `flux-klein.md`.

Objetivo: DreamShaper 8 / SD 1.5 com stable-diffusion.cpp Vulkan e página local
com um único campo. Imagem ocupa o painel principal; input sobreposto embaixo,
conforme desenho do usuário. Enter gera; resultado pode ser salvo em 1920×1080.

Restrições: todos os downloads e artefatos ficam neste projeto. Nenhuma instalação
no sistema, nenhuma alteração em drivers ou configurações globais. Usuário autorizou
compilar localmente após a proposta inicial de somente fontes.

Arquitetura: Python padrão serve HTML/CSS/JS e API de jobs; subprocesso sd-cli
recebe argumentos em lista. Uma geração por vez. Geração em 768×448, Euler,
20 passos, CFG 7, seed aleatória; navegador recorta ao centro e redimensiona para 1920×1080.
Redimensionamento não equivale a super-resolução por IA.

## Execução

- [x] Baixar e verificar modelo oficial e ferramentas locais; registrar versões.
- [x] Preparar cabeçalhos no prefixo tools/local/prefix e compilar sd-cli Vulkan.
- [x] Testar comportamento de jobs e erros com processo simulado antes da integração.
- [x] Criar servidor e interface seguindo o desenho; documentar iniciar e compilar.
- [x] Executar testes e smoke test real se GPU disponível; registrar limitações.

Ruling: usar a pasta solicitada diretamente; ela não contém código prévio. Não
criar worktree nem commits, pois a entrega é local e a pasta .git é gerenciada.
Ruling: executar o plano já aprovado sem nova rodada de aprovação.
Ruling: o backend encontra SPIRV-Headers via CMake mas não propaga seu include
para ggml-vulkan. Passar o include local em CMAKE_CXX_FLAGS, preservando os fontes
originais. Falha inicial reproduzida: spirv/unified1/spirv.hpp não encontrado.
Ruling: o teste real confirmou alinhamento obrigatório a múltiplos de 64:
768×432 vira 768×448 no motor. Solicitar 768×448 explicitamente e recortar 8 pixels
de cada borda vertical no navegador antes de ampliar a 1920×1080. A exibição usa
o mesmo PNG exportado, preservando a proporção e a correspondência com o download.

Verificação: validação de prompt vazio, limite de concorrência, passagem literal
do prompt ao processo, falha de execução, saída PNG ausente/inválida, rotas de
imagem sem acesso fora de outputs e API local. Testes de geração usam processo
simulado, sem substituir a validação real da GPU.
