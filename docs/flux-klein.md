# FLUX.2 Klein 4B — 2026-11-17

Histórico das etapas anteriores. O fluxo ativo de geração + ampliação por IA está
documentado em `upscale-pipeline.md`.

O usuário escolheu FLUX.2 Klein 4B para comparar qualidade/velocidade com Qwen
Image Turbo (90 segundos relatados por ele). Substituir o conjunto ativo, manter
a interface, preservar modelos anteriores e deixar a geração real para ele.
Nenhuma instalação no sistema ou alteração de drivers.

## Componentes e configuração

Arquivos usados nesta etapa: modelos importados de uma pasta selecionada
na biblioteca. A localização exata é configurável e não é necessária ao projeto.

- Gerador: `flux-2-klein-4b-Q4_K_M.gguf`, Unsloth FLUX.2-klein-4B-GGUF,
  variante destilada de 4 passos, não Base.
- Encoder: `Qwen3-4B-Q4_K_M.gguf`, Unsloth Qwen3-4B-GGUF. O antigo Qwen3-VL 8B
  não é usado nesta família.
- VAE: `flux2-vae.safetensors`, Comfy-Org/Flux-2-Klein-4B.

Total aproximado: 5,44 GB. Versões, tamanhos e SHA-256 publicados são registrados
em `sources.json` depois de verificar cada download. Arquivos incompletos usam
sufixo `.part`; só são finalizados quando tamanho e hash correspondem.

Euler, 4 passos, CFG 1, scheduler `flux2`. Removidos os sigmas específicos de
Qwen Image Turbo e o argumento de cache específico do Qwen Image 2.1. A seleção
de arquitetura e condicionamento FLUX.2 Klein é feita pelo motor existente.

Mantidos encoder na CPU, gerador/VAE no Vulkan0, orçamento de 6 GiB de VRAM,
pesos com offload para RAM, mmap e VAE em blocos. Quantizações GGUF preservadas.
Resolução inicial de comparação: 768×448, recorte central e ampliação para 1920×1080.
Essa configuração foi substituída pela resolução nativa descrita abaixo.

## Verificação

Testes simulados verificam nomes e passagem separada dos três componentes,
4 passos, CFG 1, scheduler flux2, ausência dos argumentos do Qwen e manutenção
das rotas, concorrência, erros e encerramento. Nenhum modelo real é carregado
por esses testes. O teste de geração e o tempo do Klein ficam para o usuário.

Resultado: 9 testes Python e 1 teste JavaScript passaram. Os três downloads foram
concluídos e seus tamanhos e SHA-256 conferidos contra os metadados das revisões
publicadas. Revisão independente não encontrou problemas importantes. Nenhuma
geração real foi executada nem servidor iniciado para uso durante a troca.

Para ativar a troca em um servidor que já estava aberto, encerrar com Ctrl+C e
executar `./start.sh` novamente. Não é necessário recompilar o motor.

## Atualização: 1080p nativo

O usuário mediu cerca de 37 segundos na configuração inicial, mas considerou a
ampliação muito borrada. A configuração ativa passa a gerar **1920×1088**. O VAE
FLUX.2 tem fator espacial 16 e o Klein fator de difusão 1, portanto a altura 1080
precisa ser alinhada a 1088 pelo motor. Não foi alterado o código do motor.

O navegador valida as dimensões e copia o retângulo de origem `(0,4,1920,1080)`
para o destino `(0,0,1920,1080)`. Isso remove só 4 linhas de cada borda vertical:
os pixels permanecem em escala 1:1, sem redimensionar nem interpolar. O PNG
original 1920×1088 fica em outputs e o arquivo baixado é 1920×1080. Resultados
antigos em 768×448 são rejeitados, em vez de ampliados.

Mantidos modelo, 4 passos, CFG 1, scheduler, memória e interface. A geração real
em alta resolução permanece a cargo do usuário; não foi executada por nós.
O tempo e uso de memória serão diferentes dos 37s medidos em baixa resolução.
Testes simulados cobrem o tamanho nativo, o recorte 1:1 e a rejeição de baixa resolução.

## Diagnóstico do erro em 1080p

O log `logs/b74d56e4807a4ffaa60bdf21c4e84ec6.log` registra `ErrorDeviceLost`
durante a amostragem, após carregar os componentes e completar o encoder. O
kernel registrou timeouts no ring compute do processo sd-cli e soft resets da
AMDGPU. Não há evidência neste log de erro de dimensão ou falta explícita de VRAM.

O backend Vulkan agrupa até 100 nós por submissão por padrão. Ajustado somente
no ambiente do subprocesso para `GGML_VK_MAX_NODES_PER_SUBMIT=1` e
`GGML_VK_SERIALIZE_SUBMISSIONS=1`, opções suportadas pelo motor compilado.
O objetivo é limitar a duração das submissões e sincronizá-las; se ocorrer nova
perda do dispositivo, o modo sincronizado também registra os nós envolvidos.
Não alterados resolução, modelo, driver, parâmetros do kernel ou sistema.

Perdas do contexto Vulkan recebem mensagem específica na API; a falha encerra o
pedido e não dispara repetição automática. Testes simulados validam passagem das
opções, diagnóstico e novo pedido após falha. A geração real continua a cargo do
usuário: essa mudança é uma mitigação baseada no timeout observado, não uma
confirmação de resolução do problema na GPU.
