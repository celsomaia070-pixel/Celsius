# Preenchimento de documentos a partir de fontes

O Celsius preenche uma nova cópia de um modelo DOCX com informações extraídas de
um ou mais documentos de origem. O modelo continua sendo a base do arquivo:
parágrafos, tabelas, estilos, imagens, cabeçalhos e rodapés não são reconstruídos
a partir de texto. Os originais e arquivos de saída já existentes não são sobrescritos.

## Como usar no chat

1. Anexe o documento de origem e o modelo DOCX.
2. Indique os papéis dos arquivos, por exemplo: “Use os dados de origem.docx para
   preencher modelo.docx. Deixe sem preenchimento os campos sem informação.”
3. Para conhecer o plano antes de criar a cópia, peça “Analise os campos e mostre
   de onde virá cada informação antes de preencher”.
4. Quando o Celsius solicitar a autorização já prevista para essa ferramenta,
   revise a ação e autorize na conversa.
5. Baixe o documento anexado e confira os campos que ficaram pendentes.

Em Work, os anexos são copiados para `data/agent_workspaces/<tarefa>/inputs`,
mantendo o nome amigável no contexto do agente. Assim a retomada de uma tarefa
continua tendo acesso aos arquivos após a limpeza dos uploads temporários.
Essas cópias de entrada não contam como documentos gerados.

Reinicie o Celsius após atualizar o código para carregar a ferramenta e as
instruções novas. O fluxo utiliza o modelo local e as bibliotecas existentes;
não exige uma API externa ou um segundo modelo dedicado.

## Etapas e integração

| Etapa | Implementação reaproveitada | Responsabilidade |
| --- | --- | --- |
| Anexos | `core/chat_attachments.py`, `ai/task_runtime.py` | Preparar caminhos e conservar entradas de tarefas |
| Extração | `core/document_intake.py` | Ler fatos rotulados e registrar documento e posição de origem |
| Inspeção | `core/document_forms.py` | Localizar campos no modelo sem modificá-lo |
| Correspondência | `core/document_mapping.py` | Relacionar rótulos conservadoramente e detectar ambiguidades |
| Planejamento | `core/document_pipeline.py` | Consultar o modelo local, validar referências e produzir o plano |
| Escrita | `core/document_forms.py` | Modificar texto/XML selecionado em uma cópia e validar o arquivo |
| Entrega | `ai/tools.py`, `core/chat_outputs.py` | Disponibilizar o resultado real para download no chat |

A ferramenta existente `preencher_documento_com_fontes` recebe `caminho_modelo`,
`caminhos_fontes`, `caminho_saida` opcional e `usar_modelo` opcional. O novo
`somente_analisar=true` retorna o plano sem criar arquivo. A escrita mantém a
política existente de confirmação; a análise não modifica documentos.

O resultado informa `mapping`, `conflicts`, `rejected`, `still_open`,
`needs_review`, `written` e, quando há escrita, `output` e `applied_count`.
Cada correspondência aceita registra destino, referência de origem, evidência,
método e confiança. As fontes e o modelo recebem hashes para detectar alterações
entre planejamento e escrita.

## Dados e confiança

O modelo de linguagem propõe referências, por exemplo:

```json
{"mapeamentos": [{"destino": "Observações:", "origem": "anotacao", "confianca": 0.95}]}
```

O código busca o valor na extração original. Um valor livre devolvido pelo modelo
não é utilizado. Referências inexistentes, confiança abaixo de 0,90, valores
conflitantes e destinos ambíguos permanecem pendentes. Esse índice é um critério
de correspondência, não uma probabilidade estatística calibrada de acerto.

As caixas de seleção exigem uma resposta correspondente às opções reais e um
rótulo de origem relacionado, ou uma referência semântica validada. Um “Sim”
isolado de outro assunto não basta. Marcadores vazios na origem não contam como
informações. Os documentos entram como dados; instruções escritas neles não
ganham autorização para executar ferramentas.

Se o modelo local estiver indisponível ou o contexto exceder o limite seguro,
as correspondências determinísticas continuam funcionando e a limitação é
registrada em `llm_note`. Sem nenhum preenchimento aplicado, a ferramenta
retorna `written=false` e não entrega um arquivo como concluído.

## Cobertura e limites desta versão

A versão validada cobre DOCX → DOCX e importação de modelos ODT para saída DOCX.
Para ODT, as ferramentas do Celsius usam o LibreOffice instalado no computador
com um perfil temporário isolado. Se ele estiver ausente ou a conversão falhar,
o Celsius pede uma cópia em DOCX e não afirma que o arquivo foi preenchido.
Ela cobre pares rótulo/valor, campos em
parágrafos, tabelas aninhadas, placeholders `{{campo}}` e `[[campo]]`,
grupos `( ) Sim ( ) Não`, cabeçalhos/rodapés, controles Word nomeados simples,
itens numerados em seções e respostas em linhas abaixo de títulos.
Controles bloqueados, vinculados a XML externo, listas, datas especiais ou
estruturas complexas exigem revisão e não são reescritos automaticamente.

Somente as partes XML alteradas são substituídas no pacote DOCX; as demais
partes são preservadas byte a byte. Isso preserva estilos, imagens e relações,
mas textos maiores podem mudar a paginação ou ultrapassar células com altura
fixa. É necessário conferir o resultado visualmente no Word.

Texto narrativo sem rótulos, caixas de texto gráficas, múltiplas pessoas no mesmo
documento e campos repetidos sem identificação exigem organização das fontes
ou revisão. A ferramenta não inventa dados ausentes nem redige avaliações novas
a partir de suposições. O modelo real escolar enviado em ODT foi preenchido
com 30 correspondências da fonte da biblioteca e convertido em DOCX. O conteúdo
das cinco tabelas com dados foi comparado com a fonte; o ODT original permaneceu
inalterado. Os exemplos reproduzíveis abaixo continuam sendo fictícios.

Em solicitações explícitas de preenchimento, a seleção de ferramentas permite
ler os arquivos locais e as fontes da biblioteca usando caminhos reais.
Quando origem e destino são inequívocos, uma resposta textual do modelo aciona
o preenchimento físico. O chat apresenta o resumo de campos e o arquivo para
download; rascunhos sem preenchimento não substituem a entrega. Um relatório
genérico gerado separadamente não conclui uma tarefa de preenchimento.

O suporte anterior a PDF e outras fontes não foi ampliado nesta entrega.
A evolução para PDF deve separar formulários AcroForm, PDF textual e documentos
escaneados, com testes próprios de coordenadas e OCR.

## Verificação reproduzível

`tests/fixtures/document_fill` contém `origem.docx`, `modelo.docx`,
`resultado_esperado.docx`, `resultado.docx` e o plano em `validacao.json`.
O resultado esperado foi preparado independentemente da implementação.
O exemplo preenche cinco campos, marca “Sim” e deixa “Telefone” sem preenchimento.

Para criar e validar outro conjunto em uma pasta vazia, na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe scripts/document_fill_demo.py --output-dir data/cache/document_fill_demo_novo
```

O script compara o conteúdo com o resultado esperado e verifica que as partes
não editadas do pacote permanecem idênticas. Os testes em
`tests/test_document_fill_reliability.py` também cobrem referências semânticas
com um modelo simulado, conflito entre fontes, revisão, preservação de elementos
Word e a disputa de nomes de saída. Os testes de tarefas verificam retomada com
as entradas conservadas após a remoção dos uploads.

A comparação estrutural foi executada com documentos DOCX reais. A revisão de
paginação por imagens está pendente: o renderizador LibreOffice fornecido pelo
ambiente não está disponível neste computador. A suíte não representa uma
validação visual no Word nem uma avaliação do acerto de um modelo local em uso.
