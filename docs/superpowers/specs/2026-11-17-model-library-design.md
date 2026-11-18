# Biblioteca de modelos

Decisão do usuário: substituir o campo de pastas por uma aba Modelos; na primeira
abertura escolher Z-Image Turbo Q8, Klein 4B Q8 ou ambos e uma pasta de destino.
Permitir localizar arquivos existentes sem copiar. Identificar componentes pelo
conteúdo, sem exigir nomes específicos. Manter dois perfis oficiais e Personalizado.

Aba com dois conjuntos, componentes e caminhos, espaço necessário/disponível,
download cancelável e retomável, SHA-256 antes de publicar arquivos, verificação
manual e remoção recuperável apenas dos arquivos baixados pelo app. Pastas podem
ser adicionadas e removidas da biblioteca sem apagar seu conteúdo. Primeira abertura
é identificada pela ausência de qualquer conjunto completo, sem atrapalhar a instalação
existente. Downloads são iniciados somente por ação explícita do usuário.

Abordagem escolhida: biblioteca local e downloader Python no servidor existente,
interface web na configuração. Alternativas: exigir downloads manuais (mantém o
problema) ou embutir pesos no app (impede escolher só um conjunto e ocupa o projeto).
Manifesto imutável com revisões/hashes já registrados em sources.json. Sem dependências
novas, instalações, geração de imagem, transferência de pesos atuais ou commits.
Estado da biblioteca separado das configurações de geração. Usar seletor de pastas
do próprio app, compatível com o navegador local. Erros e cancelamento preservam
parciais; arquivos incompletos não aparecem como instalados.
