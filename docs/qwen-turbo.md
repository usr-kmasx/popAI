# Qwen Image 2.1 Turbo — 2026-11-17

Histórico: substituído posteriormente por FLUX.2 Klein 4B, conforme `flux-klein.md`.

O usuário relatou 471 segundos para Qwen normal, com qualidade muito melhor que
DreamShaper. Solicitou baixar o Turbo verdadeiro e trocar o backend; o teste de
geração será feito por ele.

Fonte do gerador: `unsloth/Qwen-Image-2.1-Turbo-GGUF`, revisão
`bd53e520a64472adaff780da0b2f2d7eb1605e30`.
Arquivo: `qwen-image-2.1-turbo-Q4_K_M.gguf`, 4.199.565.120 bytes.
SHA-256 publicado: `8940e8b522af886e0c0f5afddf720e82dd223cb9a43580b5f61c4d740452ac20`.

O arquivo é baixado na mesma pasta do SSD, com sufixo `.part` até terminar a
verificação. O gerador normal é preservado. Encoder Qwen3-VL e VAE Qwen 2.1 são
reutilizados diretamente do SSD.

Configuração ativa: Euler, 8 passos, CFG 1 e `--sigmas qwen-image-2.1-turbo`.
O preset fixa os 8 passos pelo agendamento de sigmas do Turbo; reduzir apenas
o número de passos do modelo normal não seria uma troca equivalente.

Mantidos: quantização GGUF, encoder na CPU, gerador e VAE no Vulkan0, orçamento
de 6 GiB, offload de pesos para RAM, mmap, VAE em blocos, cache q8_0 e dimensões
768×448 com exportação 1920×1080. Interface sem alterações.

Validação concluída sem gerar imagens reais: 9 testes Python e 1 teste JavaScript
passaram; tamanho e SHA-256 do download conferidos contra os metadados da revisão
publicada. Caminhos dos três componentes confirmados e revisão independente sem
problemas importantes. Nenhuma instalação no sistema.
Servidor não é iniciado para geração. Se o usuário deixou um servidor anterior
aberto, deve encerrá-lo e executar `./start.sh` novamente para carregar a troca.
