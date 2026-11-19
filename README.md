# popAI

Geração local com **Z-Image Turbo**, **FLUX.2 Klein 4B** e **FLUX 3 Image Klein**, stable-diffusion.cpp/Vulkan e
ampliação geral Real-ESRGAN NCNN/Vulkan. Uso no Linux atual, sem pacote portátil.

## Iniciar e encerrar

Execute `./start.sh` e abra http://127.0.0.1:7860. Outra porta:
`./start.sh --port 7861`. Ctrl+C encerra o servidor e seus motores.
Após alterações no backend, reinicie o servidor. Fechar só a aba do navegador
não encerra o servidor; use Ctrl+C para liberar o motor.

## Configurações

O botão ⚙ abre duas abas:

- **Geral**: proporção, resolução final, geração Padrão/Leve, pastas de modelos e manter motor carregado.
- **Stable Diffusion**: conjunto oficial, parâmetros de geração e GPU Vulkan.

Os conjuntos padrão são **Z-Image Turbo Q8** (9 passos, CFG 1, Euler,
scheduler automático), **FLUX.2 Klein 4B Q8** (4 passos, CFG 1, Euler,
scheduler flux2) e **FLUX 3 Image Klein Q8** (16 passos, CFG 1, Euler, scheduler discrete). Seus encoders e VAEs oficiais são escolhidos automaticamente
na biblioteca. Componentes compatíveis dessas mesmas famílias são identificados
pelo conteúdo, inclusive arquivos renomeados e outras quantizações. Os pesos atuais continuam no SSD externo; não foram
copiados para a partição do projeto. DreamShaper foi removido.

**Personalizado** ajusta os parâmetros de um desses conjuntos. Alterar passos,
CFG, sampler, scheduler, resolução ou VAE em blocos não descarrega o gerador.
Trocar conjunto, GPU de geração, compatibilidade Vulkan ou mmap exige recarga.
A GPU do ampliador pode ser trocada sem descarregar o gerador.
Se a ampliação falhar por um arquivo inválido ou um erro de gravação, o gerador
residente continua disponível. O app o libera se faltar RAM, se o sistema encerrar
o processo ou se a GPU compartilhada perder o contexto ou ficar sem VRAM.

A configuração de geração é aplicada e gravada ao clicar em **Salvar**.
Cancelar descarta os ajustes de geração ainda não salvos. As ações da aba
**Modelos** são aplicadas imediatamente e têm estado próprio.
Desmarcar a permanência cancela/descarrega imediatamente por segurança, mas a
preferência só é gravada ao Salvar. O Klein aceita referências; Z-Image gera por texto.

Na primeira abertura sem nenhum conjunto completo, o app abre a aba **Modelos**.
Escolha **Pasta de download** e baixe um conjunto ou todos; **Localizar existentes**
adiciona arquivos sem copiá-los. Os cartões mostram disponibilidade, componentes,
caminhos e o tamanho restante. A pasta escolhida recebe uma subpasta por conjunto.
Downloads cancelados deixam `.part` para retomada, inclusive após fechar o app.
SHA-256 e tamanho são conferidos antes de publicar cada arquivo. URLs imutáveis,
tamanhos e hashes dos padrões estão em `model-downloads.json`. **Verificar** usa os
arquivos escolhidos no cartão, valida compatibilidade e calcula o SHA-256. Padrões
confirmados pelo manifesto, fingerprints locais inalterados e arquivos compatíveis
sem hash de origem conhecido têm resultados distintos. A primeira verificação de
uma quantização alternativa não comprova sua integridade de origem. Downloads ou
padrões anteriormente confirmados com hash divergente ficam bloqueados para geração.
**Remover download** move somente arquivos inalterados registrados pelo app para
`.popai-trash` na pasta do modelo, onde podem ser recuperados manualmente. Isso não
libera espaço no disco até essa lixeira ser esvaziada. Importados são preservados.
Remover uma pasta da biblioteca não apaga seu conteúdo. A biblioteca fica em
`model-library.json`, separada dos ajustes de geração em `model-settings.json`.

O cálculo do gerador, encoder e VAE usa Vulkan. Os pesos têm offload para RAM,
carregados na GPU conforme necessário. Não passamos `--max-vram`, não impomos
reserva percentual nem rejeitamos pesos maiores que a VRAM. O motor respeita a
memória física disponível; isso não torna a capacidade da GPU ilimitada.
Manter carregado reutiliza o processo e o modelo, com pesos que podem ficar na
RAM; não fixa todos os pesos na VRAM. A compatibilidade Polaris mantém os envios
Vulkan em 4 nós e sincronizados, como no ajuste local anterior.

Se o carregamento ou a geração falhar, o processo é encerrado e o motor
persistente é descarregado, sem nova tentativa automática. **Ajustar configuração**
abre a aba Stable Diffusion. A mensagem distingue VRAM, RAM, disco, driver e componentes; confira o ajuste indicado.
**Cancelar** interrompe o pedido. Desligar a permanência também cancela e libera.

## Melhorar prompt

O botão de varinha ao lado do input usa **AtomicChat/LFM3-1.7B-Uncensored-GGUF,
AD-Q4_K_M**. O texto em inglês chega diretamente ao campo, sem gerar uma imagem.
**Desfazer** restaura o texto anterior; **Cancelar** interrompe o pedido e também
restaura o original. Falhas e streams incompletos preservam a descrição original.
O navegador salva o texto e seu único nível de Desfazer num registro conjunto;
recarregar/reabrir mantém ambos. Edição manual invalida o Desfazer. Uma melhoria
interrompida mantém o texto e o Desfazer anteriores, sem persistir a saída parcial.
O prompt interno fica em `prompt-enhancer-system.txt`, sem meta fixa de palavras.

O `llama-server` próprio inicia junto com `./start.sh`, fica carregado na RAM e
encerra junto com o app. Usa somente CPU (`-ngl 0`, `--device none`), contexto de
**2048 tokens**, raciocínio desligado e uma sequência por vez. Escuta somente em
127.0.0.1:8081, com chave interna. Uma porta ocupada não é tomada nem reutilizada;
falha do melhorador não impede o uso dos geradores de imagem. Se o motor de texto
cair, clicar novamente em melhorar
tenta recuperar somente esse motor. Uma falha de carga continua sendo mostrada
sem um ciclo infinito de novas tentativas. O código do app não
acrescenta filtros de assunto; o comportamento do modelo não é uma garantia de
ausência absoluta de recusas.

O executor e bibliotecas ficam em `backends/llama-cpu/` (cerca de 19 MiB); o modelo,
em `models/prompt-enhancer/` (1.132.208.000 bytes). Nada é instalado no sistema.
`python3 tools/setup-prompt-enhancer.py` reproduz o download verificado e a compilação
CPU usando ferramentas já disponíveis; fontes/intermediários usam uma pasta
temporária, removida depois. Esta compilação x86-64 requer AVX2, FMA e F16C.
Revisões, URLs e hashes estão em `prompt-enhancer.json`. O executor tem licença MIT;
o modelo usa a licença LFM própria, preservada junto aos pesos.

## Imagem e arquivos

O formato anterior continua como padrão: base 960×544 em 16:9. As proporções
16:9, 9:16, 9:20, 1:1, 4:3 e 3:4 ajustam a base e a saída. Leve usa até 768 px
no maior lado da base; Padrão usa até 960 px. A base é alinhada a blocos de 16 pixels.
O seletor de resolução mostra as dimensões finais da proporção escolhida. O Real-ESRGAN amplia em 4× e o executor ajusta à largura
do preset. O backend recorta somente o pequeno excesso horizontal ou vertical e grava o PNG
exato em 720p, 900p, 1080p, 1440p, 1800p ou 4K UHD (3840×2160).
Imagem exibida e download apontam para esse mesmo PNG, sem conversão no navegador.

Em **Muito leve**, a base tem 256 px no maior lado. O Real-ESRGAN aplica duas
ampliações 4× com uma única carga dos pesos. Os pixels de 8 bits da primeira
passagem seguem em memória para a segunda. O ajuste à resolução escolhida
acontece depois das duas passagens e o ampliador encerra ao terminar.
O executor local `backends/upscayl-ncnn/upscayl-chain` usa os mesmos pesos,
GPU e blocos de 128 px do executor original. Quando a compilação encontra a
libpng no Linux, o executor também grava o PNG diretamente das linhas do recorte
final. Isso evita uma segunda gravação quando a ampliação excede o preset.
`./build.sh` prepara essa variante e `./tools/build-upscayl.sh` permite
recompilá-la à parte. O app detecta os recursos do executável. Versões anteriores
continuam usando o recorte em Python e, quando necessário, duas chamadas para ampliar.

**Nenhum PNG novo é salvo automaticamente em `outputs/`.** Bases, referências
e ampliações são arquivos temporários em uma pasta privada `popai-*` no diretório
temporário do sistema. Após sucesso, base e ampliação intermediária são removidas.
A prévia atual fica disponível; a anterior tem uma margem de 60 segundos antes
da limpeza. Intermediários do pedido corrente são preservados para recuperação;
pedidos abandonados ao iniciar outro são limpos. Downloads já iniciados usam uma
cópia dos bytes, sem depender da permanência do arquivo temporário.
Referências removidas da interface são liberadas; se estiverem em uso, a remoção
espera a geração terminar. Referências anexadas renovam sua atividade no polling;
órfãs expiram após uma hora. Ao sair da página há liberação best-effort, preservando
o cache de navegação Voltar/Avançar. A limpeza ocorre durante o uso, sem nova thread.
O botão de download salva a
cópia permanente no destino escolhido pelo navegador, sem gravar uma cópia adicional
no projeto. PNGs antigos existentes no projeto foram preservados.

`logs/` guarda diagnósticos e `jobs/` guarda metadados dos pedidos;
`model-settings.json` guarda as configurações. Em falha de ampliação/finalização,
**Concluir imagem** reaproveita os temporários válidos durante a mesma sessão,
sem gerar uma imagem nova. Encerrar o servidor remove os temporários; a recuperação
de novos pedidos não persiste após o encerramento. Atualizar a página oculta a foto.
Arraste move a visualização, a roda dá zoom no cursor e duplo clique reenquadra;
o arquivo baixado permanece igual ao PNG final, sem aplicar o zoom da tela.

Os executores locais existentes ficam em `backends/`. `./build.sh` é a rotina
local de recompilação do stable-diffusion.cpp; não há instalação no sistema.

## Modelos oficiais e licenças

- [Z-Image Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo): Apache-2.0.
- [FLUX.2 Klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B): Apache-2.0.
- [FLUX 3 Image Klein](https://huggingface.co/black-forest-labs/flux-3-image-klein#license): FLUX Kommunity License.

O executor comum é stable-diffusion.cpp (MIT). Os modelos são componentes do
backend de geração; o app não é afiliado aos seus autores. O executor de ampliação
upscayl-ncnn tem licença AGPL-3.0, preservada em `backends/upscayl-ncnn/LICENSE`.
Ao distribuir os componentes, preservar suas licenças e avisos e cumprir suas
respectivas condições. O código próprio do popAI usa a licença MIT, disponível em `LICENSE`. As licenças dos modelos e executores permanecem próprias; a licença MIT do app não as substitui.
