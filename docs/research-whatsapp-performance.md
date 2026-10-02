# Pesquisa, relatórios e WhatsApp — 02/10/2026

## Diagnóstico confirmado na conversa mais recente

- O pedido WhatsApp `TAREFA: Gere uma relatório do meu estoque` levou
  279.360 ms (4min39s). A seleção de ferramentas consumiu 229.752 ms,
  antes do primeiro token. Ela codificava o catálogo de ferramentas usando
  o modelo de embeddings na CPU. Esse tempo não era geração na GPU.
- A resposta misturava um rascunho com campos fictícios e tabelas do estoque.
  O PDF existia, mas a ferramenta não devolvia seu caminho na resposta de
  sucesso. A verificação de entregáveis marcava a tarefa como falha.
- A interface web não renderizava tabelas Markdown. O WhatsApp recebia o
  Markdown bruto, dividido por comprimento, inclusive no meio de tabelas.
- A entrega era realizada depois de marcar a entrada WhatsApp como concluída.
  Uma falha de transporte podia perder a resposta sem recuperar a entrega.
- O pedido de notícias da semana retornava páginas de produtos. Um atalho
  devolvia a busca bruta, sem notícias datadas ou síntese.
- O navegador esperava um Chromium do Playwright ausente neste computador.
  A leitura de acessibilidade também usava uma API antiga.
- A identidade composta `quem é voce e o que voce pode realizar?` não era
  reconhecida como pergunta rápida e carregava o modelo.

## Alterações

- Relatório completo e simples do estoque: plano determinístico que executa
  a ferramenta real, mantém política/autorização, verifica o PDF e devolve um
  resumo curto com números confirmados. Não carrega modelo ou embeddings.
  Pedidos filtrados, históricos, compostos ou com envio a contatos continuam
  no fluxo de ferramentas e agentes. O PDF inclui todos os itens.
  O modo Trabalho também evita múltiplos agentes para esse plano simples,
  respeitando as permissões dos agentes selecionados.
- Caminho real e nome legível retornados pela ferramenta de relatórios;
  metadados dos anexos persistidos atomicamente.
- Listagem simples de notícias: pesquisa real e apresentação de títulos,
  datas, resumos disponíveis e links, sem uma chamada desnecessária ao modelo.
  Análise e comparação continuam com o modelo, precedidas pela busca real.
- Busca de notícias pelo provedor disponível, com fallback Google News RSS
  quando necessário. Datas são filtradas pelo período pedido; semana passada
  significa segunda a domingo anteriores. Sem notícias fora do período como
  substituição. Priorização simples por impacto e até duas notícias por fonte.
- Pesquisa explícita usa ferramentas de busca/navegação diretamente, sem
  codificar o catálogo semântico. Continuações de notícias recuperam a consulta
  anterior do usuário, sem seguir instruções de resultados web.
- Navegação tenta leitura HTTP limitada primeiro, validando destinos e
  redirecionamentos públicos. Páginas dinâmicas usam Playwright; se faltar seu
  Chromium, tentam Edge/Chrome já instalados em contexto separado.
  Fechamento em falhas, verificações de cancelamento e API atual de leitura.
- Perguntas gerais recebem instruções mais compactas e continuam usando o
  modelo. Identidade e capacidades compostas entram no respondedor rápido.
- Tabelas reais e roláveis na web; listas com campos identificados no WhatsApp.
  Divisão das mensagens respeita parágrafos e linhas quando possível.
- Fila de saída WhatsApp persistente, independente da execução da tarefa.
  Desconexão antes do envio permite retomada. Entrega sem confirmação fica
  incerta e exige `REENVIAR RESULTADO`, sem repetir efeitos de estoque.
  `STATUS` mostra a etapa atual; a interface mostra entregas pendentes/incertas.
- Informações de execução do modelo na API: disponibilidade de backend GPU,
  camadas configuradas e fallback CPU. Não equivalem a uma medição de GPU.

## Medições reais

Sem alterar o modelo, seus parâmetros globais ou instalar dependências.
Relatórios gerados sobre cópia isolada dos dez itens atuais: nenhuma alteração
no estoque real. Nenhuma mensagem de teste enviada pelo WhatsApp.

| Caso | Antes | Depois | Escopo |
|---|---:|---:|---|
| Relatório simples de estoque | 279,36 s no histórico | 2,86 s / 2,46 s | Coordenador, ferramenta e PDF reais, armazenamento isolado |
| Notícias de IA desta semana | Resposta rápida, mas sem notícias verificadas | 3,28 s, oito fontes datadas | Rede real, busca, tarefa e apresentação; sem modelo |
| Notícias de IA da semana passada | Sem medição comparável | 4,28 s, oito fontes datadas | Rede real, busca, tarefa e apresentação; sem modelo |
| Pergunta geral `Quanto é 2 + 2?` | 3,02 s no benchmark anterior | 2,98 s, resposta correta | Respondedor e modelo reais, roteamento mantido fixo |
| Página estática example.com | Sem medição anterior | 105 ms | HTTP real, conteúdo verificado |
| Página via navegador instalado | Chromium ausente | 1,01 s | Edge real, incluindo inicialização e acessibilidade |

Os números são amostras locais, não garantia de latência. O tempo de envio pela
rede WhatsApp não está incluído no benchmark do relatório. A busca pode variar
com disponibilidade, bloqueios e qualidade dos provedores.

O diagnóstico nativo identificou **AMD Radeon RX 7600 / Vulkan0**, com
**34/34 camadas na GPU**, 4.812 MiB de pesos e 512 MiB de cache KV na GPU.
Os contadores Windows do processo de benchmark mostraram Compute 0 próximo
de 100%. O gráfico 3D não representa necessariamente a inferência.
Isso confirma a GPU neste teste; não prova qual backend estava ativo em toda
execução antiga. A etapa lenta de embeddings observada no histórico era CPU.

Carregamento frio: 4,48 s. Geração nativa: aproximadamente 24 tokens/s nesse
teste com diagnóstico e monitoramento ativos. Os dois ensaios de 160 tokens
atingiram o limite: não são medições de respostas completas.
Cancelamento foi observado entre chunks, com liberação do lock; não torna
preenchimento de contexto/carregamento nativos imediatamente interrompíveis.

Evidências locais, excluídas do Git:

- `data/logs/research-delivery-after.json`
- `data/logs/agent-latency-research-after.json`
- `data/logs/gpu-benchmark.stderr.log`
- `data/logs/gpu-benchmark-counters.json`
- `data/logs/chat-table-after.png`

## Validação

- Suíte ampliada: **1.423 passaram, um skip, três deselections**, 115,99 s.
  Foram excluídos os cinco arquivos de RAG/embeddings/UI mencionados abaixo
  e os dois grupos de casos incompatíveis com essa execução conjunta.
- Seleção final: **290 passaram**, incluindo relatórios, WhatsApp, API,
  cancelamento, encaminhamento, ferramentas e locks de inferência.
- Após corrigir o pareamento de mensagens de chamada/resultado da pesquisa
  antecipada, **21 testes de pesquisa/navegador passaram**, inclusive análise
  que consulta uma fonte antes da chamada ao modelo.
- Depois da verificação das permissões e do caminho rápido no modo Trabalho,
  **78 testes passaram**, incluindo a execução real do PDF com vários agentes
  selecionados e a manutenção das restrições de ferramentas.
- Ruff nos arquivos desta etapa, sintaxe JavaScript e verificação do diff.
- Edge real validou DOM de tabela, pipe escapado, numeração e HTML tratado
  como texto. Navegação HTTP e navegador reais foram exercitados.
- Serviço atualizado ativado na porta 8790; health OK e WhatsApp conectado,
  com conversa própria disponível e pareamento preservado.

Comando da suíte ampliada:

```powershell
python -m pytest -q --ignore=tests/test_rag.py --ignore=tests/test_golden_set.py --ignore=tests/test_hybrid_rag.py --ignore=tests/test_embeddings.py --ignore=tests/test_ui.py --deselect=tests/test_chat_outputs.py::test_template_request_delivers_download_even_when_model_only_drafts_in_chat --deselect=tests/test_offline.py::TestRAGOffline
```

Os módulos excluídos têm incompatibilidades anteriores entre mocks de
transformers e dependências reais, ou configuração inicial Qt que pode bloquear
a execução conjunta. Esta execução não equivale à suíte completa. Os testes
de fila/transporte WhatsApp usam simulação; a reconexão do serviço real foi
observada, mas o envio completo pelo celular precisa ser validado com um pedido
do usuário. O teste de análise de notícias usa modelo simulado; a medição
de pergunta geral usa o GGUF real.

## Limitações restantes

- Importância das notícias usa critérios simples; não é uma avaliação editorial
  exaustiva. A apresentação informa quando recebeu só títulos e resumos.
- Análises longas ainda dependem da qualidade e velocidade do GGUF local.
  A mudança não tornou toda resposta instantânea. Solicitações ambíguas que
  exigem classificação semântica ainda podem pagar pelo encoder na CPU.
- Falhas de entrega incertas não são repetidas automaticamente, evitando
  duplicidade. O usuário precisa conferir a conversa e pedir reenvio.
- A integração atual depende de WhatsApp comum via Baileys e da sessão
  conectada. Os testes não garantem estabilidade do serviço externo.
- Não houve commit, push, troca de modelo, instalação ou reversão das
  alterações existentes do usuário/OpenCode.

## Verificação de 02/10: YouTube e consulta ao TecUnimar

A última conversa web (`2cc267b65d07`) pediu uma relação com o TecUnimar nas
memórias. O atalho de `core.commands` tratou `procure nas memorias` como busca
web por `nas memorias` e devolveu resultados brutos sobre NAS/armazenamento.
Foi uma troca indevida de fonte. O registro local observado antes dos testes
dizia que o projeto Celsius faz parte da incubadora do TecUnimar, com origem
`usuario`; isso é um registro do usuário, não uma confirmação externa.

No ensaio posterior com o GGUF realmente configurado (`qwen-heretic-q4_k_m`),
o modelo também acrescentou uma afiliação ao IFMA ausente desse registro.
Esse ensaio não passou no critério de fidelidade, apesar de mencionar a
incubadora corretamente. Consultas simples às memórias agora retornam os
registros encontrados diretamente, como citações, sem gerar detalhes extras.
Pedidos de análise continuam usando o modelo e contexto local. Nenhum modelo
ou parâmetro global foi trocado nesta intervenção.

Mudanças desta etapa:

- Fonte local explícita impede o atalho de pesquisa web e a pesquisa antecipada.
- Consulta simples de memória dispensa modelo, RAG, seleção semântica e equipe
  de agentes. A resposta vem dos registros consultados; não é um texto fixo
  substituindo uma pergunta geral. Consulta sem resultado informa essa ausência,
  sem concluir que a relação não existe.
- Contexto de memória já consultado não causa leitura ou geração duplicada.
  Análises e pedidos compostos conservam o fluxo normal e as permissões.
- Abertura simples do YouTube usa uma etapa direta e preserva a pesquisa.
  Confirmação, escopo, expiração e rejeição continuam obrigatórios conforme
  a política existente. Checkpoints antigos podem continuar sem duplicar a ação.
- Recusa do navegador produz falha; solicitação aceita informa somente que
  a abertura foi solicitada. Não afirma que leu a página ou reproduziu um vídeo.
  Abertura não recebe repetição automática, pois produz um efeito externo.

Medições locais finais, 25 amostras por caminho:

| Caminho | Mediana | P95 | Escopo |
|---|---:|---:|---|
| Preparar abertura do YouTube/confirmar | 168,13 ms | 175,06 ms | Coordenador e persistência reais; abertura do sistema simulada |
| Executar abertura autorizada | 142,97 ms | 147,40 ms | Mesma simulação, uma chamada por autorização |
| Consultar registro do TecUnimar | 176,50 ms | 185,26 ms | Memória real, conversas isoladas, sem modelo, encoder, rede ou envio WhatsApp |

O pedido YouTube original (`8d275811a5da`) gastou 223,08 s antes da confirmação,
dos quais 213,98 s em seleção de ferramentas. Não executou nenhuma abertura.
O teste real de geração de memória, anterior ao caminho direto, gastou 4,10 s
com modelo carregado e 4,59 s no carregamento frio; sua resposta acrescentou
um fato sem suporte. Não é usado como evidência de correção semântica.

Relatórios sem conteúdo das memórias: `data/logs/youtube-routing-after.json`,
`data/logs/memory-grounded-after.json` e
`data/logs/memory-model-verified-after.json` (ensaio que revelou a alucinação).
Abertura física e entrega WhatsApp não foram usadas para as medições.

### Incidente de isolamento dos testes de memória

Durante esta validação, os testes antigos de compatibilidade em
`tests/test_memory.py` chamaram o singleton global sem aplicar `temp_settings`,
substituindo a base real por dados de teste. Corrigido com singleton temporário
por teste e `CELSIUS_MEMORIAS_FILE` temporário configurado antes dos imports em
`tests/conftest.py`. A última execução foi acompanhada por uma assinatura lógica
SHA-256 da base real, idêntica antes/depois, com dois registros.

O registro exato do TecUnimar, lido nesta sessão antes do incidente, foi
recuperado sem inventar sua data original. A base após o incidente foi
preservada em `backups/memorias-before-recovery-20261002.db`; backups históricos
foram mantidos. Não havia snapshot integral imediatamente anterior, portanto
não foi possível confirmar a recuperação de todos os outros registros.
Backups antigos não foram incorporados automaticamente: podem conter dados
removidos anteriormente pelo usuário ou pelo mesmo defeito antigo de testes.

A seleção ampliada final passou em **436 testes**, em 28,54 s. Após o novo caminho de
consulta direta, os 88 testes específicos de memória, conversa e navegador
também passaram; a seleção ampliada final está registrada em
`data/logs/youtube-memory-grounded-final-tests.log`. A suíte inteira não foi
executada nesta etapa. Simulações verificam permissões, cancelamento e
contexto; a medição de consulta direta usa a memória real. Perguntas analíticas
ainda podem produzir extrapolações do GGUF e precisam de avaliação contínua.
