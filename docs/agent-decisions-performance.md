# Encaminhamento, cancelamento e desempenho dos agentes

Verificação local em 02/10/2026, em `E:\PythonProjectCELSIUS`.

## Causas confirmadas

- O frontend Work acrescentava `TAREFA:` a qualquer mensagem e mantinha uma
  segunda classificação por palavras, diferente da classificação Python.
- O coordenador preparava modelo e memória antes de o respondedor reconhecer
  respostas simples. A identificação barata no modo não garantia o desvio no motor.
- Os filtros tratavam acentos, pontuação e saudações de maneiras distintas. A frase
  `quem é voce?` não era reconhecida pelo atalho do motor; `olá me diga as suas
  capacidades` também não era reconhecida pelo filtro central.
- Decisões lexicais já claras voltavam a passar pela classificação semântica.
- O cancelamento não chegava a todos os respondedores. Esperas por locks nativos
  eram ilimitadas, e erros durante streaming podiam conservar o lock.
- A interrupção de ciclos repetidos usava um motivo de pausa que permitia
  retomada automática. Uma consulta bem-sucedida também não comprovava uma
  movimentação solicitada no estoque.

O tempo anterior de 7 min 56 s foi informado pelo usuário, não reproduzido neste
trabalho. A coleta anterior mediu apenas reconhecimento dos filtros; não é uma
medição de latência completa comparável ao benchmark posterior.

## Alterações

`core/message_intent.py` centraliza normalização e distingue conversa, pergunta
geral, consulta com ferramentas, tarefa e controle. Os clientes web e WhatsApp,
o coordenador, o respondedor e os seletores de modos/ferramentas usam essa base.
Saudações compostas não eliminam a intenção restante. Anexos impedem o atalho.
Comandos explícitos de execução e as políticas de aprovação permanecem ativos.

`core/quick_response.py` responde identidade, capacidades, saudações, data e hora
antes de modelo, embeddings, memória, RAG e execução de tarefas. Perguntas gerais
continuam usando o modelo. Work deixa de prefixar qualquer pergunta e não inicia
vários agentes automaticamente. Operações de persistência da submissão web
executam fora do event loop HTTP.

Memória pessoal e RAG são consultados quando a intenção pede esse contexto.
Consultas claras de estoque podem selecionar ferramentas lexicais sem encoder.
Modos conhecidos não precisam repetir classificação semântica; empates e margens
semânticas insuficientes não forçam um especialista.

`core/operation_control.py` propaga cancelamento e prazo pelo contexto de execução,
inclusive ao respondedor comum e ao visual, com verificações antes/depois das
etapas demoradas. Esperas por locks verificam o controle a cada 50 ms; streams
liberam o lock em cancelamento, falha, encerramento e erro no fechamento.
O prazo padrão de perguntas gerais é 120 s; consultas usam o limite do modo;
tarefas e controles têm teto externo de 3.600 s, além dos orçamentos já existentes
da sessão. Chamadas diretas do desktop recebem os mesmos limites e respeitam
prazos externos mais restritivos. Expiração é informada, com progresso preservado.

Ciclos sem evidência nova são pausados com motivo explícito e sem retomada
automática. Respostas cortadas pelo limite de tokens são identificadas como
incompletas. Falhas e cancelamentos passam a deixar uma resposta no histórico.
Pedidos claros de entrada/saída no estoque exigem uma ferramenta de movimentação
bem-sucedida; consultar o estoque não basta. Relatórios de movimentações não são
confundidos com novas ordens de entrada. Os verificadores existentes de fontes e
arquivos gerados foram mantidos.

`core/turn_metrics.py` registra apenas números e rótulos conhecidos: encaminhamento,
classificação, memória, RAG, seleção de ferramentas, preparação, espera pelo modelo,
primeiro token bruto, primeiro texto visível e total. Distingue modelo não usado,
frio e carregado. Não acrescenta prompts, documentos, credenciais ou respostas aos
registros de desempenho.

## Medições reais

Hardware informado: Ryzen 5 5500, RX 7600, SSD 1 TB e RAM 32 GB. O benchmark usou
o GGUF configurado `qwen-heretic-q4_k_m`, com backend Vulkan disponível, contexto
16.384, GPU layers -1 e batch 1.024. Não foram trocados modelo ou configurações
globais, nem instaladas dependências.

| Medição | Resultado | Escopo |
| --- | ---: | --- |
| Identidade | mediana 146,95 ms | 25 submissões, coordenador e persistência reais |
| Capacidades | mediana 145,86 ms | 25 submissões, coordenador e persistência reais |
| Identidade com `TAREFA:` legado | mediana 146,52 ms | 25 submissões |
| Capacidades com `TAREFA:` legado | mediana 145,90 ms | 25 submissões |
| Encaminhamento barato | aproximadamente 0,05–0,06 ms | última amostra de cada grupo |
| Carregamento frio do GGUF | 4.351,71 ms | modelo real |
| Geração nativa fria, 160 tokens | 4.276,95 ms | atingiu limite de tokens; resposta incompleta |
| Geração nativa carregada, 160 tokens | 4.197,99 ms | atingiu limite de tokens; resposta incompleta |
| Pergunta geral simples pelo pipeline | 3.019,50 ms | modelo real carregado; resposta correta `4` |
| Primeiro token bruto / texto visível dessa pergunta | 1.625,59 / 2.868,98 ms | medidos separadamente |
| Cancelamento depois do primeiro chunk | 0,021 ms | observado; lock de inferência liberado |
| Carregamento frio do embedding local | 30.199,04 ms | `qwen3-embedding-0.6b`, CPU |
| Uma consulta no embedding carregado | 176,59 ms | vetor de dimensão 1.024 |

As 100 respostas rápidas não chamaram o modelo. A latência inclui persistência,
mas não inicialização do aplicativo, navegador ou transmissão até o celular.
O teste da pergunta geral usa o respondedor, ReAct, persistência e inferência reais,
com o roteamento de modelo fixado por um adaptador ao GGUF já configurado. Não
mede JEV, seleção entre modelos, tarefas complexas ou chamadas de ferramentas.
As medidas nativas têm uma amostra fria e uma carregada, não uma distribuição de
desempenho. O tempo de cancelamento não representa cancelamento durante prefill.

Evidências locais, sem conteúdo das respostas:

- `data/logs/intent-before.json`
- `data/logs/agent-latency-after.json`
- `data/logs/embedding-latency.json`

Reprodução: `.venv\Scripts\python.exe scripts\benchmark_agent_latency.py --model --pipeline`.
O benchmark usa diretórios temporários e não executa ferramentas externas ou
ações destrutivas.

## Testes

A seleção final de encaminhamento, controle, tarefas, coordenador, modos e
WhatsApp passou em 162 testes. Outros 90 testes passaram, cobrindo proteção de
inferência, warmup, orçamento de loops, recuperação de ferramentas e interrupção,
além de sete verificações offline. Esses testes usam mocks nas dependências
pesadas; não constituem medições de desempenho do modelo.

A execução ampliada anterior terminou com 1.385 aprovados, um ignorado e três
desselecionados em 81,84 s. As correções finais de verificação de estoque e prazo
direto foram validadas novamente pela seleção relevante acima. A suíte inteira
sem exclusões não foi validada: o `conftest.py` substitui `transformers` por mocks
incompatíveis com imports reais de `sentence_transformers`, afetando RAG,
embeddings, golden set e um teste de saída de documento. O ciclo de testes Qt
também pode abrir o diálogo modal de configuração inicial durante processamento
de eventos, bloqueando a execução conjunta.

Comando da execução ampliada:

```powershell
.venv\Scripts\python.exe -m pytest -q `
  --ignore=tests/test_rag.py --ignore=tests/test_golden_set.py `
  --ignore=tests/test_hybrid_rag.py --ignore=tests/test_embeddings.py `
  --ignore=tests/test_ui.py `
  --deselect=tests/test_chat_outputs.py::test_template_request_delivers_download_even_when_model_only_drafts_in_chat `
  --deselect=tests/test_offline.py::TestRAGOffline `
  --tb=short -o faulthandler_timeout=30 -W ignore::DeprecationWarning
```

Ruff nos arquivos alterados, verificação de sintaxe JavaScript por Node e
`git diff --check` passaram. A tentativa de avaliação semântica completa com o
encoder real não produziu relatório concluído; recall, precisão e sucesso de
tarefas complexas não são apresentados como medidos.

## Preservação e limites restantes

O diff inicial foi preservado em `data/logs/agent-performance-before.patch`.
As mudanças anteriores em `core/app_context.py`, `core/settings.py` e `analyze.py`
foram mantidas. As sobreposições em motor, ReAct, filtros, embeddings e testes
foram integradas; o carregamento estritamente local de embeddings foi preservado.
Não houve commit, push ou reinicialização do serviço em uso.

Cancelamento é cooperativo: carga nativa, prefill ou uma chamada bloqueante de
terceiros só devolvem o controle quando essa etapa retorna. A espera pelo lock e
a emissão de novos chunks são canceláveis; não é seguro liberar o lock enquanto
a operação nativa ainda o utiliza.

O encaminhamento barato não compreende todas as paráfrases possíveis. Pedidos
ambíguos ainda podem precisar de classificação semântica, cujo custo frio é alto
nesse setup. O filtro seletivo de memória exige referência pessoal/contextual;
recordações implícitas podem não ser recuperadas automaticamente. Verificação de
movimentação confirma execução da capacidade correta, não prova universalmente
todos os argumentos e efeitos de qualquer tarefa. Avaliação ampla de qualidade
com modelo real, interface Qt e recuperação RAG permanece necessária antes de
afirmar sucesso geral em tarefas complexas.

Para ativar o código em um processo já aberto, é necessário reiniciar esse
processo e recarregar a página web. O cache do JavaScript foi atualizado.
