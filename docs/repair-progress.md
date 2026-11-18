# Escopo substituído pelo usuário — 2026-11-17

O usuário interrompeu o empacotamento e definiu uso local no PC atual.
O plano anterior abaixo é histórico; não continuar downloads, build Ubuntu ou
pacote portátil. Não houve instalação no sistema.

Implementado no novo escopo: único conjunto Z-Image Turbo, Vulkan em todos os
módulos, offload RAM em CLI e residente, sem teto de VRAM do app; abas Geral e
Stable Diffusion; Padrão imutável e um Personalizado sobrescrevível; erro encerra
motor e oferece Ajustar configuração. Modelos e resultados preservados.

# Revisão Linux portátil — execução

Plano aprovado na conversa: seis etapas obrigatórias, nesta ordem.

1. Caminhos e configuração portátil — concluída: migração v1 com backup, caminhos relativos, pastas configuráveis; verificados relocação com espaços/acentos e sintaxe.
2. Hardware automático ajustável — concluída: identidade Vulkan, mapeamento GGML, orçamento disponível com reserva, opções na interface; verificados GPU real e seleção simulada com várias GPUs.
3. Validação de componentes — concluída: identificação limitada a cabeçalhos e formas de tensores, cache por tamanho/mtime, combinação por família e NCNN; verificados todos os modelos locais e rejeição de papel incompatível.
4. Recuperação sem regeneração — concluída: manifestos atômicos, configuração por pedido, restauração após reinício e botão Concluir imagem; verificado reaproveitamento da base com pesos ausentes e nenhuma chamada ao gerador.
5. PNG final no backend — concluída: Pillow decodifica e valida, recorte central sem reamostragem e PNG atômico; frontend exibe/baixa o mesmo arquivo; verificados os seis presets e rejeição de PNG truncado.
6. Organização e pacote portátil — pendente.

Restrições: Linux x86_64, sem instalação no sistema; preservar modelos, imagens e
preferências; ampliar com Real-ESRGAN NCNN; uma geração real curta no final.
Verificações diretas e adaptação dos testes existentes, sem coleção de scripts novos.

Ruling: trabalhar na pasta autorizada existente, sem commits/worktrees fora dela:
o Git pertence à pasta pai e contém outros projetos. Não alterar esse repositório.
Ruling: implementar pessoalmente as seis etapas; uma revisão independente ao final,
conforme a rotina de execução; sem delegações de implementação por etapa.
