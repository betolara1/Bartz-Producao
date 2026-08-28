# 🏭 Programa Produção — Gestão & Localizador de Planos de Corte

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+" />
  <img src="https://img.shields.io/badge/GUI-Tkinter%20%2F%20ttk-FF6F00?style=for-the-badge&logo=python&logoColor=white" alt="Tkinter GUI" />
  <img src="https://img.shields.io/badge/Engine-PyMuPDF%20(Fitz)-1E88E5?style=for-the-badge" alt="PyMuPDF" />
  <img src="https://img.shields.io/badge/Platform-Windows%207%20%7C%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows" />
  <img src="https://img.shields.io/badge/Deploy-PyInstaller%20Standalone%20.exe-2E7D32?style=for-the-badge" alt="PyInstaller" />
</p>

---

## 🎯 Sobre o Projeto

O **Programa Produção** é uma aplicação desktop nativa desenvolvida para automatizar e otimizar o fluxo de trabalho industrial no chão de fábrica. Ele resolve o gargalo de triagem de planos de corte gerados por sistemas ERP (como **PromobERP**), monitorando pastas de rede em tempo real, extraindo metadados e tabelas diretamente da estrutura interna dos PDFs e permitindo a gestão colaborativa de lotes entre múltiplos operadores sem necessidade de infraestrutura pesada de banco de dados.

---

## 🚀 Principais Funcionalidades

### ⚡ Automação e Leitura Inteligente
- **Monitoramento Contínuo em Segundo Plano**: Varredura periódica e assíncrona da pasta de rede sem travamento da interface gráfica.
- **Renomeação Automática por Lote**: O ERP frequentemente salva arquivos com nomes genéricos (ex: `PP5928.pdf`). O sistema lê o conteúdo interno via coordenadas espaciais, identifica o número real do lote e renomeia o arquivo com segurança (ex: `3409.pdf`, `3409_2.pdf`).
- **Prevenção de Conflitos de Gravação**: Arquivos em processo de gravação por impressoras PDF virtuais são ignorados automaticamente até a estabilização do arquivo.

### 📋 Gestão de Produção & Separação de Chapas
- **Extração Nativa por Coordenadas (Parser)**: Converte relatórios PDF complexos em uma tabela interativa com campos estruturados: *Código, Descrição do Item, Metros e Quantidade*.
- **Controle de Apontamento**: Campos editáveis para *Responsável*, *Qtde Chapas Real* e *Observações*, com validação de preenchimento obrigatório para conclusão de lotes.
- **Visualizador Integrado**: Permite inspecionar o PDF original renderizado em alta fidelidade com zoom e navegação.

### 👥 Colaboração Multi-usuário em Tempo Real
- **Sincronização Distribuída Leve**: Estado compartilhado via arquivos JSON estruturados em pasta de rede (`_controle`), permitindo que toda a equipe acompanhe o status de cada lote instantaneamente.
- **Sistema de Prioridades (⭐)**: Destaque visual imediato para lotes urgentes na fila de produção.
- **Histórico de Comentários & Notificações Flutuantes (Toast)**: Notificações visuais e sonoras estilo *Toast Notification* no canto da tela quando novos comentários são adicionados por outros operadores.

---

## 🛠️ Destaques Técnicos & Arquitetura

- **Multithreading Não-bloqueante (`threading` + `queue.Queue`)**: A interface permanece sempre fluida (60 FPS) mesmo durante operações pesadas de I/O em rede e processamento de documentos.
- **Sincronização Inteligente de Interface (`_sync_tree`)**: Algoritmo de renderização diferencial que atualiza itens do `ttk.Treeview` *in-place*, preservando seleção, foco e rolagem do usuário sem efeito de *flicker*.
- **Engenharia Reversa de Layout PDF**: Extração espacial com `PyMuPDF` (`fitz`), superando problemas de fluxos de texto não-lineares típicos de geradores de relatórios industriais.
- **Design Limpo e Modular**: Separação clara entre camada visual, lógica de negócios, persistência e adaptadores de sistema de arquivos.

---

## 📂 Estrutura do Projeto

```
Programa-Producao/
├── main.py                      # Ponto de entrada da aplicação
├── requirements.txt             # Dependências externas do projeto
├── Programa-Producao.spec       # Configuração de build do PyInstaller
└── programa_producao/
    ├── __init__.py
    ├── app.py                   # Janela principal, listagem com abas e controle de polling
    ├── detail.py                # Tela de Separação de Chapas e apontamento de produção
    ├── parser.py                # Extração de texto e tabelas por coordenadas do PDF
    ├── scanner.py               # Monitoramento de rede, fila assíncrona e renomeação segura
    ├── store.py                 # Persistência distribuída de estado compartilhado (JSON)
    ├── comments.py              # Sistema de chat/comentários e notificações Toast nativas
    ├── preview.py               # Renderizador e visualizador vetorial de PDFs
    └── config.py                # Gerenciamento de configurações locais em %APPDATA%
```

---

## 💻 Como Executar

### Pré-requisitos
- Python 3.8 ou superior (com suporte a Tkinter).

### Passo a passo
1. Clone o repositório ou baixe os fontes:
   ```bash
   git clone https://github.com/betolara1/Bartz-Producao.git
   cd Bartz-Producao
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Execute a aplicação:
   ```bash
   python main.py
   ```

> 💡 **Configuração Inicial**: Ao abrir o programa pela primeira vez, clique em **Configurações...** para definir o diretório de rede onde os PDFs são salvos. A configuração fica salva em `%APPDATA%\ProgramaProducao\config.json`.

---

## 📦 Gerando o Executável Standalone (.exe)

O projeto pode ser empacotado em um executável único e independente, sem necessidade de instalar o Python nos computadores finais:

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller --onefile --windowed --name ProgramaProducao main.py
```

Ou utilizando o arquivo de especificação já configurado com os hooks do PyMuPDF:
```bash
python -m PyInstaller Programa-Producao.spec
```

O executável final será gerado em:
```
dist/ProgramaProducao.exe
```

> 📌 **Compatibilidade com Windows 7 / 10 / 11**:
> Para gerar um binário compatível desde o Windows 7 até o Windows 11, execute a compilação utilizando o **Python 3.8 (32-bit)** com `PyMuPDF==1.23.26`. Para ambientes Windows 10/11 exclusivos, qualquer versão recente do Python 3.x é suportada.

---

## ⚙️ Configurações (`config.json`)

As configurações são salvas automaticamente em `%APPDATA%\ProgramaProducao\config.json`:

```json
{
  "root_path": "\\\\servidor\\compartilhamento\\PDF",
  "refresh_seconds": 10,
  "window_geometry": "980x560"
}
```

---

<p align="center">
  Desenvolvido com foco em <b>alta produtividade</b>, <b>baixo atrito operacional</b> e <b>performance em ambiente industrial</b>.
</p>
