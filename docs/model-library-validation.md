# Validação da biblioteca — 2026-11-17

Implementada a especificação em `superpowers/specs/2026-11-17-model-library-design.md`.
Validação com arquivos temporários e servidor HTTP local; sem baixar pesos reais
nem iniciar geração. Nenhuma instalação ou commit. Arquivos do SSD preservados.

Verificações diretas executadas:

- Retomada por Range a partir de 12.345 bytes, SHA-256 e publicação atômica.
- Persistência da pasta escolhida e do registro dos downloads.
- Verificação manual de um download válido.
- Remoção recuperável de downloads sem tocar arquivo importado.
- Content-Range incorreto rejeitado, preservando o parcial.
- SHA incorreto rejeitado, sem publicar um modelo corrompido.
- Cancelamento e retomada posterior do mesmo parcial.
- Falta de espaço rejeitada antes de iniciar a transferência.
- Arquivo existente diferente preservado sem sobrescrita.
- Publicação em sistema sem hard links por renameat2/RENAME_NOREPLACE e colisão
  concorrente sem sobrescrita.
- Remoção da biblioteca de uma pasta já indisponível.
- Descoberta e configuração de três componentes renomeados por cabeçalho;
  arquivo de outra família excluído; ausência de conjunto completo detectada.

Interface conferida em instância isolada: primeira abertura automática na aba
Modelos, navegação e seleção da pasta, espaço disponível, importação dos dois
conjuntos reais do SSD sem cópia, escolha e salvamento do Klein, atualização da
página sem repetir primeira abertura, componentes recolhidos e scroll interno.
Captura em `model-library.jpg`. Configurações salvas apenas na instância temporária.

Regressão: 18 testes de backend e 6 de interface. Não se mediu desempenho de
geração nem se transferiram os vários GiB dos modelos pela internet nesta etapa.

## Atualização — versão 22-1.11.26 (22/11/2026)

A biblioteca agora mantém **quatro conjuntos oficiais**, incluindo Qwen Image
2.1 · ChatR Labs Turbo. O modelo Qwen depende de gerador, encoder, VAE,
projetor de visão e Turbo LoRA (cinco componentes, aproximadamente 15,22 GB).
O manifesto fixa URL, revisão, tamanho e SHA-256 de cada um.

Os **novos downloads** são agrupados, sem duplicação por preset, nas subpastas
`Z-Image Turbo/`, `FLUX.2 Klein 4B/`, `FLUX 3 Image Klein/` e
`Qwen Image 2.1/` do destino escolhido. A biblioteca ainda registra outras
pastas, detecta arquivos importados pelo cabeçalho e não os move para
reorganizar um modelo existente. A LoRA do Qwen pode ser localizada separadamente
do gerador: a execução recebe `--lora-model-dir` com o diretório verdadeiro.

A compatibilidade com os downloads antigos foi preservada: um `.part` em pasta
legada continua sendo retomado ali. A verificação de safetensors da LoRA
confere tensores de adaptação. Se faltar a LoRA, o aplicativo exibe a
pendência em **Settings → Models**.

Regressão desta versão: **41 testes Python e 17 testes de interface**.
Foram simuladas uma biblioteca vazia, a fila com cinco componentes Qwen,
a instalação com apenas a LoRA ausente, o destino organizado, a retomada
legada e a geração simulada com gerador e LoRA em diretórios diferentes.
URLs e hashes foram confrontados com os metadados publicados, mas não se
transferiram novamente os 15,22 GB de arquivos nem se mediu desempenho real.
Veja [22-1.11.26](release-22-1.11.26.md).

## Situação atual — 23/11/2026

A biblioteca do popAI contém três conjuntos: Z-Image Turbo, FLUX.2 Klein 4B
e Qwen Image 2.1. A família FLUX 3 Image Klein foi removida do catálogo e
do manifesto. A organização atual usa as pastas homônimas na raiz de modelos,
com links simbólicos preservando os caminhos legados dos três modelos restantes.
Os registros acima documentam versões anteriores.
