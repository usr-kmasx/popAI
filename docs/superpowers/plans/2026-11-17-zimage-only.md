# Z-Image local — plano ajustado pelo usuário

Escopo aprovado em conversa: abandonar a preparação de distribuição e usar o
backend local existente, somente Vulkan com offload RAM e sem teto de VRAM do app.

1. catalog.py, hardware.py e server.py: somente família Z-Image, remover orçamento
   e rejeição por tamanho; Vulkan para todos os módulos e offload também residente.
2. catalog.py/app_config.py/server.py: dois slots, padrão imutável (9 passos, CFG 1,
   Euler, scheduler automático, mmap e VAE tiling) e personalizado sobrescrevível;
   migrar seleção atual sem apagar modelos ou resultados.
3. web/: abas Geral e Stable Diffusion, edição ativa Personalizado; Salvar persiste
   só a seleção e um personalizado, sem criar/nomear perfis. Ajustes de geração e
   tile VAE; mensagem de falha abre configuração, sem repetição automática.
4. Verificação: sintaxe, adaptar testes existentes ao novo contrato e conferir
   argumentos CLI e residente sem geração real. Nada de instalar/compilar pacote.

Decisão: autorização anterior para decidir cobre esta implementação; não solicitar
nova aprovação nem criar commits no repositório da pasta pai.
