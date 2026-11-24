# popAI V23.11.26 — notas da versão

Data: 23 de novembro de 2026. Tag Git: `23.11.26`.
Continuação de [22-1.11.26](release-22-1.11.26.md).

## Instalação em um único comando

A partir desta versão, um novo usuário instala os componentes necessários executando:

```bash
git clone https://github.com/usr-kmasx/popAI.git
cd popAI
./install.sh
```

O instalador prepara o ambiente Python com Pillow, ferramentas de compilação,
motor `stable-diffusion.cpp` com Vulkan, motor de ampliação Real-ESRGAN/NCNN,
e o melhorador de prompts Qwen3.5 com llama.cpp/Vulkan. Os componentes usam
revisões e hashes fixados nos manifestos do projeto. A instalação foi
executada e repetida com sucesso em Arch Linux; Debian e Ubuntu estão
contemplados no script, mas não foram validados em instalação real nesta versão.

O instalador **não baixa** os modelos de geração de imagens: a primeira abertura
com `./start.sh` encaminha o usuário a **Settings → Models** para escolher
uma pasta e instalar o(s) modelo(s) desejado(s). O usuário também pode importar
pesos existentes. Os três conjuntos de imagens são independentes do modelo
interno do melhorador de prompts. `./install.sh --check` verifica a
preparação local sem iniciar o aplicativo.

Pacotes temporários de instalação verificados são descartados depois da
conclusão, sem apagar pesos importados, imagens, configurações ou outros
dados do usuário. O `start.sh` utiliza o Python virtual do projeto quando
disponível. Downloads interrompidos do melhorador podem ser retomados.

## Catálogo de modelos e presets

Os modelos disponíveis para download e seleção são:

| Modelo | Presets disponíveis | Componentes |
| --- | --- | ---: |
| Z-Image Turbo | 9, 5 e 4 passos | 3 |
| FLUX.2 Klein 4B | 4 e 3 passos | 3 |
| Qwen Image 2.1 · ChatR Labs Turbo | 8 e 4 passos | 5 |

O **FLUX 3 Image Klein** foi retirado do seletor, do catálogo interno e
do manifesto de downloads. As variações não aprovadas de 2 passos dos
modelos FLUX.2 Klein e Qwen também foram removidas. Isso não interfere
nos presets restantes.

O Qwen utiliza o gerador ChatR Labs Q8_0 e a Turbo LoRA existente. O modo
residente pode reutilizar o motor entre gerações com a mesma configuração;
a edição por referência carrega o projetor visual quando necessário.

## Melhorias e manutenção

- Motor residente e configurações de geração refinados, inclusive as
  transições entre geração por texto e referência do Qwen.
- Melhorador de prompts atualizado, com parâmetros e texto de orientação
  revisados, sem iniciar o modelo ao abrir o aplicativo.
- A área de preview do wallpaper não participa mais da navegação sequencial
  com Tab.
- Documentação de primeira instalação substitui a preparação manual de
  dependências e motores.
- Manifesto de fontes limitado aos componentes realmente necessários
  para compilar e instalar o aplicativo; registros antigos contendo caminhos
  de máquinas de desenvolvimento foram excluídos.

## Verificação

- Instalação real via `./install.sh` no Arch Linux: concluída.
- Segunda execução: concluída sem repetir downloads já preparados.
- `./install.sh --check`: aprovado.
- Testes Python: **51 aprovados**.
- Testes de interface: **17 aprovados**.
- Verificações de sintaxe e `git diff --check`: aprovadas.

Os testes não implicam uma garantia de compatibilidade com qualquer GPU ou
distribuição. Para instalar em outro computador, é necessário um driver
Vulkan funcional, acesso aos downloads externos e espaço para os modelos
escolhidos.
