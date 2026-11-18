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
