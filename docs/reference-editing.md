# Imagem de referência no popAI

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
