# Migracao da interface para web local

## Objetivo

O Celsius continuara processando dados e modelos no computador da empresa. A interface passara a
consumir uma API local unica, usada pela janela instalada e, quando autorizado, pelo celular na
mesma rede.

## Arquitetura de transicao

1. **Aplicacao atual:** PySide6 continua sendo a interface principal durante a migracao.
2. **API local:** FastAPI publica contratos versionados em `/api/v1`.
3. **Eventos:** WebSocket entrega respostas, progresso, lembretes e mudancas dos modulos em tempo
   real.
4. **Interface web:** o shell responsivo do chat ja consome os contratos locais; os demais modulos
   serao migrados de forma incremental depois que seus contratos estiverem cobertos por testes.
5. **Janela instalada:** no fim da migracao, uma janela leve abrira a mesma interface web local sem
   depender de um navegador externo.

## Primeiros contratos

- `GET /api/v1/health`: disponibilidade e versao da API.
- `GET /api/v1/session`: identidade do Celsius e perfil resumido da empresa.
- `GET /api/v1/modules`: catalogo completo e configuracao dos modulos.
- `GET /api/v1/navigation`: modulos ativos que podem aparecer na navegacao.
- `WS /api/v1/events`: canal autenticado para atualizacoes em tempo real.
- `POST /api/v1/chat/messages`: cria uma resposta assincrona sem bloquear a interface.
- `POST /api/v1/chat/attachments`: recebe anexos locais vinculados a uma mensagem.
- `GET /api/v1/chat/jobs/{id}`: acompanha conclusao, falha ou cancelamento.
- `POST /api/v1/chat/jobs/{id}/cancel`: interrompe cooperativamente a resposta atual.
- `GET /api/v1/chat/conversations`: lista o mesmo historico persistido no computador.
- `DELETE /api/v1/chat/conversations/{id}`: exclui a conversa e seus backups locais, com bloqueio durante resposta ativa.
- `GET /api/v1/agenda`: lista os compromissos da mesma base usada pelo desktop e pelo LLM.
- `POST /api/v1/agenda`: cria compromissos locais com cliente, responsavel e lembrete.
- `PATCH /api/v1/agenda/{id}`: edita dados ou atualiza o status do compromisso.
- `DELETE /api/v1/agenda/{id}`: exclui um compromisso local.
- `GET /api/v1/agenda/reminders/due`: consulta lembretes que exigem confirmacao.
- `POST /api/v1/agenda/{id}/acknowledge`: confirma e desativa um lembrete.
- `GET /api/v1/documents`: lista arquivos gerenciados e documentos legados do RAG.
- `POST /api/v1/documents/upload`: armazena e agenda a indexacao local sem bloquear a pagina.
- `GET /api/v1/documents/jobs/{id}`: acompanha extracao e indexacao em segundo plano.
- `GET /api/v1/documents/search`: pesquisa trechos na base hibrida local.
- `POST /api/v1/documents/{id}/reindex`: refaz a extracao e o indice do arquivo armazenado.
- `GET /api/v1/documents/{id}/file`: recupera o arquivo original com autenticacao local.
- `DELETE /api/v1/documents/{id}`: remove arquivo, cadastro e trechos indexados.
- `GET /api/v1/customers`: lista e pesquisa clientes na base modular local.
- `POST /api/v1/customers`: cadastra clientes com dados comerciais e de contato.
- `PATCH /api/v1/customers/{id}`: atualiza o cadastro de um cliente.
- `DELETE /api/v1/customers/{id}`: remove um cliente da base local.
- `GET /api/v1/suppliers`: lista e pesquisa a mesma base de fornecedores usada pelo desktop.
- `POST /api/v1/suppliers`: cadastra fornecedores e condicoes de fornecimento.
- `PATCH /api/v1/suppliers/{id}`: atualiza o cadastro de um fornecedor.
- `DELETE /api/v1/suppliers/{id}`: remove um fornecedor da base local.
- `GET /api/v1/inventory`: lista itens, saldos, limites, localizacao e saude do estoque.
- `POST /api/v1/inventory`: cadastra um item na mesma base usada pelo desktop e pelo LLM.
- `PATCH /api/v1/inventory/{id}`: atualiza nome, categoria, limites e localizacao.
- `DELETE /api/v1/inventory/{id}`: remove um item do estoque local.
- `POST /api/v1/inventory/{id}/movements`: registra entrada ou saida com validacao de saldo.
- `GET /api/v1/inventory-movements`: consulta o historico local de movimentacoes.
- `GET /api/v1/products-services`: lista e pesquisa o catalogo comercial modular.
- `POST /api/v1/products-services`: cadastra produto, servico, pacote ou assinatura.
- `PATCH /api/v1/products-services/{id}`: atualiza preco, custo, SKU, fornecedor e status.
- `DELETE /api/v1/products-services/{id}`: remove um cadastro do catalogo local.
- `GET/POST/PATCH/DELETE /api/v1/quotes`: gerencia propostas, valores, validade e status.
- `GET/POST/PATCH/DELETE /api/v1/cases-deadlines`: acompanha processos, prioridades e prazos.
- `GET /api/v1/reports`: lista arquivos e modelos de relatorio locais.
- `POST /api/v1/reports/generate`: gera PDF, DOCX ou Markdown com dados operacionais reais.
- `GET /api/v1/reports/{id}/download`: entrega somente arquivos validados na pasta local de relatorios.
- `DELETE /api/v1/reports/{id}`: remove o cadastro e o arquivo gerado.
- `GET /api/v1/mobile/pairing`: gera o link HTTPS para a mesma interface responsiva e o QR Code protegido por token.
- `POST /api/v1/voice/transcribe`: recebe WAV do navegador e transcreve localmente no computador.

O perfil da empresa e o catalogo em `core.modules` continuam sendo a fonte unica de verdade. Chat e
Configuracoes permanecem obrigatorios.

Respostas publicam `chat.status`, `chat.chunk`, `chat.completed`, `chat.failed` e `chat.cancelled`
no WebSocket. O coordenador aceita somente uma inferencia ativa para proteger o contexto nativo do
llama.cpp.

## Executar durante o desenvolvimento

```powershell
.\.venv\Scripts\python.exe -m core.web_api
```

Por seguranca, o servidor aceita somente este computador (`127.0.0.1`) quando o acesso movel esta
desativado. Se o acesso pela rede estiver habilitado nas configuracoes, o servidor usa `0.0.0.0`;
tambem e possivel solicitar isso com `--host 0.0.0.0 --allow-lan`. O token continua obrigatorio.

Quando o Celsius desktop e iniciado, a API tambem sobe automaticamente em `127.0.0.1:8790` e usa o
mesmo modelo ja carregado pelo aplicativo. O comando acima permanece disponivel para desenvolvimento
sem abrir o PySide.

Com o servidor ativo, abra `http://127.0.0.1:8790/app` no navegador. A pagina local faz o pareamento
automatico neste computador, preserva a preferencia de tema e compartilha o mesmo historico de
conversas do aplicativo instalado.

## Shell web disponivel

- layout responsivo para computador e celular;
- tema claro como padrao e seletor persistente `LIGHT | GREEN | DARK`, com verde escuro e preto tratados como modos distintos;
- botao Parear celular com QR Code HTTPS para a mesma interface usada no computador;
- sidebar, modulos, conversas, temas, Jarvis e controles compartilhados entre computador e celular;
- botao de microfone no compositor para gravar, transcrever localmente e enviar perguntas por audio;
- continuidade da mesma conversa entre perguntas faladas e digitadas no celular;
- historico e criacao de conversas;
- exclusao de conversas com confirmacao e protecao durante respostas em andamento;
- cadastro e consulta das mesmas memorias locais usadas pelo chat desktop;
- anexos locais com validacao no servidor;
- resposta em streaming com estado de processamento;
- cancelamento cooperativo da resposta atual;
- selecao entre roteamento automatico e modelos GGUF instalados;
- modo voz com fila de reproducao e interrupcao imediata;
- Jarvis flutuante e arrastavel, com posicao persistente, limite de tela e cores proprias para os estados ocioso, pensando e falando;
- agenda responsiva com busca, filtro, criacao, edicao, status e exclusao;
- lembretes locais em tempo real com sinal visual, bip recorrente e confirmacao obrigatoria;
- biblioteca de documentos com importacao multipla, metadados, status e download;
- extracao e indexacao em segundo plano com atualizacao em tempo real;
- pesquisa na base de conhecimento e compatibilidade com documentos RAG antigos;
- clientes e fornecedores com indicadores, busca, filtros e cadastro responsivo;
- acesso do assistente aos clientes e fornecedores reais por ferramentas locais;
- atualizacao imediata dos cadastros pelo WebSocket, sem recarregar a pagina;
- estoque com indicadores, busca, alertas, limites, entrada, saida e historico;
- catalogo de produtos e servicos com SKU, preco, custo, margem, unidade e status;
- ferramentas locais para o assistente consultar e cadastrar ofertas comerciais reais;
- orcamentos com numeracao automatica, cliente, valor, margem, validade e etapas comerciais;
- processos e prazos com prioridade, responsavel, proximo passo e alertas de vencimento;
- relatorios executivos e por area exportados localmente em PDF, DOCX ou Markdown;
- ferramentas de leitura sempre disponiveis para o assistente consultar os bancos locais de estoque,
  agenda, clientes, fornecedores, catalogo, orcamentos, processos e documentos;
- geracao deterministica de relatorios empresariais pedidos no chat, usando a fonte local correspondente;
- reconexao do WebSocket e consulta HTTP como contingencia;
- token de pareamento mantido em cookie local protegido, sem ser exposto no HTML.

O modelo de linguagem, as conversas e as memorias permanecem locais. O provedor de voz atual e o
Edge TTS e depende de internet; a interface informa essa excecao ao ativar o modo voz. A abstracao
em `core.tts` permite substituir esse provedor por um motor totalmente local no futuro.

## Proximas etapas

1. Adicionar configuracao visual dos modulos e do perfil da empresa.
2. Migrar financeiro e canais de notificacao.
3. Separar a inferencia em um processo local supervisionado.
4. Empacotar o shell instalado e desativar o PySide somente apos equivalencia funcional.
