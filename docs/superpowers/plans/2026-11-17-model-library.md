# Biblioteca de modelos — implementação

**Objetivo:** primeira abertura e gestão dos dois conjuntos na pasta escolhida.
**Arquitetura:** módulo model_library.py para manifesto, estado, transferências e
pastas; API no server.py; aba e seletor em web/app.js/index.html/style.css.
**Tecnologias:** Python padrão, HTTP local e JavaScript existente.
**Especificação:** docs/superpowers/specs/2026-11-17-model-library-design.md.
**Restrições:** não instalar, gerar imagens, baixar pesos reais durante validação,
alterar configuração atual ou criar commits. Verificações diretas sem novos scripts
de teste conforme preferência do usuário. Usar os testes existentes como regressão.

1. Manifesto oficial com seis componentes, URLs imutáveis, tamanhos e SHA-256.
2. Biblioteca: caminhos persistidos atomicamente; seleção de diretórios; download
   sequencial em thread, Range validado, espaço, cancelamento, SHA, rename atômico;
   verificação e remoção recuperável só de arquivos gerenciados, encerrar worker.
3. Integração API e catálogo por cabeçalhos; compatibilidade validada sem nomes.
4. Aba Modelos, escolha de pasta, dois cartões, progresso/ações/componentes;
   primeira abertura sem conjunto completo; seletores compatíveis no Personalizado.
5. Verificar importação renomeada, HTTP/Range truncado, hash incorreto, retomada,
   cancelamento, destino sem espaço e remoção sem tocar importados, com fixtures
   temporárias e servidor HTTP simulado. Executar suítes existentes e conferir GUI.

Revisão: distinguir conjunto completo de download parcial; não sobrescrever arquivos
importados; validar Content-Range; não apagar arquivos fora do registro; preservar
configurações e impedir remoção enquanto geração está ativa.

Resultado: etapas 1–5 concluídas. Revisão independente corrigiu a remoção de uma
pasta indisponível; verificação direta passou. Adicionado fallback atômico para
pastas sem hard links, também verificado com colisão. Registros de validação em
docs/model-library-validation.md. Os 18 testes de backend e 6 de interface passaram.
Nenhum download de pesos reais, alteração dos ajustes atuais ou geração de imagem.
