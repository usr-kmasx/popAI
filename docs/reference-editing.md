# Imagem de referência no popAI

> **Registro histórico de 17/11/2026.** Esta seção descreve a primeira
> implementação com uma única referência. Para o comportamento atual, incluindo
> múltiplas referências, preview ampliado e editor de desenho, consulte o
> [lançamento 21.11.26](release-21.11.26.md) e o adendo ao final deste arquivo.
> Para a versão atual, incluindo o Qwen Image 2.1 como modelo oficial,
> veja [22-1.11.26](release-22-1.11.26.md).

Pedido aprovado: adicionar botão + ao campo para anexar uma imagem e editar com
uma instrução textual. Manter FLUX.2 Klein 4B Q8, pipeline de ampliação e saída
1920×1080. Sem instalações ou serviços externos; teste real de geração pelo usuário.

Interface: + abre seletor PNG/JPEG/WebP; uma referência por vez. Mostrar miniatura
com opção de remover. Imagem + instrução usa edição; somente texto continua
gerando normalmente. Botões ficam bloqueados durante upload/geração/ampliação.

Upload local normalizado pelo navegador para PNG, até 20 MiB de arquivo original,
25 MiB normalizado, máximo 8192 pixels por eixo e 16 megapixels. API retorna um
identificador aleatório; o cliente nunca envia caminhos do computador ao gerador.
Referências ficam em references/ no projeto, separadas dos resultados.

POST /api/reference recebe PNG binário e retorna {id,image}. POST /api/generate
aceita {prompt,reference?}. O servidor valida o identificador e a referência antes
de iniciar o job, e passa somente o caminho resolvido por ele em -r ao sd-cli.
O modo de edição Klein usa os mesmos encoder e VAE; não é necessário mmproj.
O ampliador continua em processo separado após finalizar o Klein.

Verificação: upload e leitura da referência, rejeição de arquivo inválido/grande,
identificador inválido/ausente, passagem literal do -r, geração sem referência,
remoção da imagem e comportamento do botão +/estado ocupado. Sem geração real.

Resultado: 18 testes Python e 5 testes da interface passaram. No navegador,
o botão abriu o seletor, o upload exibiu a miniatura e a remoção restaurou o campo
normal. Captura em `reference-interface.jpg`. O servidor temporário de verificação
foi encerrado. A edição real na GPU continua reservada ao teste do usuário.

## Atualização — versão 21.11.26 (21/11/2026)

A implementação atual aceita **até dez referências** por pedido nos modelos
FLUX.2 Klein 4B e FLUX 3 Image Klein. O botão **+** aceita PNG, JPEG e WebP,
normaliza para PNG e apresenta miniaturas com botão de remoção. O Z-Image Turbo
continua sem edição por referência.

O botão de **caneta**, à direita do **+**, abre um editor dentro do app. Sua
área de desenho é 960 × 720 (4:3 fixo, independentemente da proporção escolhida
para a imagem gerada), com pincel, borracha, texto, seleção, movimento,
redimensionamento individual por alças, paleta e desfazer/refazer. As formas
são retângulo, elipse, linha reta contínua e seta. **Confirmar** transforma
o desenho em PNG e o anexa via o mesmo `POST /api/reference`.

Clicar na miniatura de um sketch reabre o editor; confirmar a alteração
substitui seu PNG e ID na mesma posição. O estado dos objetos é armazenado
em `sessionStorage` na aba e restaurado após F5 enquanto a imagem no servidor
continuar disponível. Desenhos anteriores sem esse estado reabrem como um
PNG achatado para receber novos traços, mas os traços antigos não são objetos
selecionáveis. Miniaturas de referências comuns abrem uma prévia ampliada.

O ciclo de vida das referências continua **temporário**: a sessão do servidor
remove os arquivos no encerramento. A integração usa as rotas locais já
existentes, com validação de origem na comunicação com o iframe do editor.

Validação da atualização: 13 testes de interface, 27 testes Python e
testes de integração no Chromium headless com gerenciador de geração fictício,
sem executar modelos de imagem na GPU. Consulte
[notas da versão 21.11.26](release-21.11.26.md).

## Atualização — Qwen Image 2.1 oficial (22/11/2026)

A versão [22-1.11.26](release-22-1.11.26.md) adiciona o **Qwen Image 2.1
ChatR Labs Turbo** aos modelos com referências, ao lado dos dois Klein.
O Qwen aceita até dez imagens e requer o projetor de visão Qwen3-VL 8B.

Antes da inferência, o servidor cria cópias temporárias das imagens, limita
cada uma a 512 pixels no maior eixo e usa preenchimento branco para alinhá-la
a múltiplos de 32 sem deformar a proporção. As imagens enviadas não são
sobrescritas. O encoder de referência e o VAE usam o caminho CPU configurado
para hardware de baixa VRAM; a difusão permanece no Vulkan. O resultado é
recortado para as dimensões solicitadas antes da ampliação existente.

O editor de desenho integrado e o fluxo de upload continuam iguais. Testes
simulados cobrem múltiplas referências e o pré-processamento; a qualidade
visual depende do modelo e da entrada. Consulte também
[Qwen Image 2.1 — integração oficial](qwen-image21.md).
