# Programa Produção — Localizador de Planos de Corte

Aplicação de desktop (Windows 7 / 10 / 11) que monitora a pasta de rede onde o
ERP (PromobERP) salva os PDFs de plano de corte (ex:
`\\pc-henrique\DXF\LOTE-644\lote644.pdf`) e lista automaticamente todos os
PDFs encontrados, mais recentes primeiro, permitindo buscar por número de
lote e visualizar o conteúdo do PDF dentro do próprio programa.

## Como rodar (modo desenvolvimento)

Requer Python 3.8+ com Tkinter (já vem incluído na instalação padrão do
Python para Windows).

```bash
pip install -r requirements.txt
python main.py
```

Na primeira execução, a pasta monitorada é `\\pc-henrique\DXF`. Para mudar,
use o botão **Configurações...** dentro do programa e clique em **Procurar...**
para escolher a pasta pelo explorador de arquivos do Windows (ou cole o
caminho de rede direto no campo). O caminho é salvo em
`%APPDATA%\ProgramaProducao\config.json` e será usado nas próximas vezes.

## Funcionalidades

- Monitora continuamente a pasta configurada (a cada 10 segundos, ajustável
  em `config.json`, chave `refresh_seconds`) e também sob demanda pelo botão
  **Atualizar agora**.
- **Renomeia automaticamente** cada PDF novo pelo número do lote lido de
  dentro do arquivo (o ERP salva tudo como `PP5928.pdf`; o programa lê o
  campo "Lote:" do conteúdo e renomeia para ex. `3409.pdf`). Se dois PDFs
  tiverem o mesmo lote, vira `3409_2.pdf` etc. Arquivos com menos de 5
  segundos de vida não são mexidos (a impressora pode ainda estar gravando).
- Lista com colunas Lote, **Status** (Pendente/Concluído), **Responsável**,
  arquivo, data e tamanho. Concluídos ficam verdes; recém-chegados, amarelos.
- Busca/filtra por número de lote; ordena por qualquer coluna.
- **Abrir** (ou duplo clique): abre a tela de Separação de Chapas com os
  dados extraídos do PDF como campos nativos — Código, Descrição, Metros,
  Quantidade — e campos editáveis de **Responsável**, **Qtde Chapas Real** e
  **Obs**. O botão **Concluir** exige Responsável e Qtde Chapas Real
  preenchidos. Um botão discreto "Ver PDF original" mostra o PDF renderizado,
  se precisar conferir.
- **Compartilhado entre usuários**: o que um usuário preenche/conclui é
  salvo em JSON na subpasta `_controle` dentro da própria pasta de rede, e
  todos os outros usuários veem o mesmo status na lista e na tela de
  detalhe (atualiza no ciclo de varredura). Em caso de dois salvarem ao
  mesmo tempo, vale a última gravação.
- A varredura roda em segundo plano (thread separada), então a interface não
  trava mesmo se a rede estiver lenta; se a pasta estiver indisponível, isso
  aparece na barra de status e a aplicação tenta de novo no próximo ciclo.

## Gerando o executável (.exe)

Importante para **Windows 7**: o suporte oficial da Python Software
Foundation ao Windows 7 terminou na série **3.8**. Para gerar um `.exe` que
funcione nas três versões do Windows, gere-o usando **Python 3.8 (32-bit)**
— um executável assim funciona em Windows 7, 10 e 11. Se só precisar rodar
em Windows 10/11, qualquer Python 3.x recente serve.

Atenção: a versão do `PyMuPDF` em `requirements.txt` foi testada num Python
mais novo. Ao montar o ambiente com Python 3.8, se `pip install PyMuPDF`
reclamar de incompatibilidade, use uma versão um pouco mais antiga (ex:
`PyMuPDF==1.23.26`, a última com suporte oficial ao 3.8).

Passos:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name ProgramaProducao main.py
```

O executável final fica em `dist\ProgramaProducao.exe` — é um arquivo único,
não precisa instalar Python nas máquinas de produção. Copie esse `.exe` para
os computadores que vão usar o programa (ex: área de trabalho, ou uma pasta
compartilhada).

## Estrutura do projeto

```
main.py                     - ponto de entrada
programa_producao/
  app.py                    - tela principal (lista compartilhada)
  detail.py                 - tela de Separação de Chapas (campos + Concluir)
  parser.py                 - extrai lote/descrição/itens do conteúdo do PDF
  scanner.py                - varredura da pasta + renomeação automática
  store.py                  - estado compartilhado em _controle/*.json na rede
  preview.py                - visualização do PDF renderizado (secundária)
  config.py                 - leitura/gravação de config.json em %APPDATA%
```

## Observações

- Os PDFs não precisam seguir nenhum padrão de nome de pasta/arquivo — o
  programa lê o texto de dentro do PDF para achar o número do lote (campo
  "Lote:" do relatório). Só é preciso apontar a pasta raiz onde a impressora
  PDF salva os arquivos (configurável em **Configurações...**).
- Se existir mais de uma pasta raiz/servidor onde PDFs podem cair, me avise
  para adicionar suporte a múltiplas pastas monitoradas.
