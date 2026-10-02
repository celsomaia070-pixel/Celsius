# Camada de Decisão Local (JEV / System One)

Estado: **implementada como camada opt-in, desligada por padrão.** Enquanto
`CELSIUS_DECISION_ENABLED` não for `true`, o Celsius se comporta exatamente
como antes (aprovação = allowlist `SENSITIVE_TOOLS`; RAG sem poda extra).

## 1. O que é

Uma camada de decisão de baixa latência e custo que roda **localmente** e
responde contratos estilo TypeSafe "System One" (`noul`, `choice`, `score`).
O objetivo é substituir (parcialmente) decisões que hoje exigem disparar o LLM
grande — que dominam a latência da sessão.

- Modelo: `jaredpalmer/kev-0.5b` (Qwen2.5-0.5B + LoRA, Apache-2.0, head
  pointer treinado para System One).
- Servidor: `kev.serve` (repositório `jaredpalmer/kev`), endpoint
  `POST /v1/systemone`.
- Download total: **~1.0 GB** (base Qwen2.5-0.5B 953 MB + adapter 51 MB).

## 2. Arquitetura

```
Celsius (py3.14)
  core/decisions.DecisionClient
      |-- provider = HttpDecisionProvider (base_url 127.0.0.1:8009)
      |
      v   POST /v1/systemone  (noul/choice/score)
kev-venv (venv própria)
  kev.serve --run jaredpalmer/kev-0.5b --port 8009
```

**Por que subprocesso HTTP em venv própria (e não em-processo):**

- `kev` pina `requires-python >=3.12,<3.14` e `torch >=2.6,<2.9`; no runtime
  do app (Python 3.14.4, torch 2.14.0) exigiria `--ignore-requires-python`.
- O servidor usa ~2.7 GB working set (~4.6 GB private); isolado, não infla o
  app.
- Falhas do servidor **degradam para o comportamento atual** (ver §5): nada
  quebra, nada é desaprovado/impedido por padrão.

**Ponto importante (design):** os gates só conseguem *adicionar* segurança (guard
de ferramenta) ou *remover* ruído (gate RAG) — nunca o contrário:

| Gate | Disabled / erro / resposta vazia | Ação |
|---|---|---|
| Guard de ferramenta | `requires_approval=False` | mantém allowlist atual |
| Gate RAG | `keep=True` | não poda chunk |
| Provider fora | fallback silencioso | log + métrica `status="error"` |

## 3. Componentes

| Arquivo | Papel |
|---|---|
| `core/decisions.py` | Contrato (`DecisionRequest`, `Noul/Choice/ScoreQuestion/Answer`), providers (`OffProvider`, `HttpDecisionProvider`), `DecisionClient`, `parse_answers`, gates `noul_gate`/`score_gate`, helpers `decide_tool_guard`, `decide_keep_chunk` e `decide_llm_model`, `get_decision_client`/`reset_decision_client` |
| `core/decision_calibration.py` | Registro de resultados (`DecisionRecorder` JSONL em `logs/decision_outcomes.jsonl`), `load_outcomes`, `accuracy`/`balanced_accuracy`, `recommend_guard_threshold`/`recommend_score_threshold` e `summarize_outcomes` para calibração gradual (§9) |
| `core/model_router.py` | `MultiModelManager.route_and_invoke`: cliente fixa modelo (`model_client_choice`) ou JEV escolhe entre os baixados; fallback para o roteador de keyword |
| `core/settings.py` | `DecisionLayerSettings` (prefixo `CELSIUS_DECISION_`) + campo `decision` no `Settings` |
| `core/metrics.py` | `celsius_decision_requests_total`, `celsius_decision_latency_seconds` |
| `ai/tools.py` | `executar_ferramenta(..., force_approval=False)` |
| `ai/react.py` | Guard de ferramenta no loop ReAct (apenas quando habilitado e ferramenta não-sensível) |
| `ai/rag.py` | `_rag_relevance_gate` no `search_context` |
| `requirements-kev.txt` | Pins do servidor (autônomo) |
| `scripts/kev-server.ps1` | Bootstrap da venv + subida do `kev.serve` |

## 4. Configuração

Todas com prefixo `CELSIUS_DECISION_`:

| Env | Default | Descrição |
|---|---|---|
| `CELSIUS_DECISION_ENABLED` | `false` | Liga a camada |
| `CELSIUS_DECISION_PROVIDER` | `local` | `off` ou `local` |
| `CELSIUS_DECISION_BASE_URL` | `http://127.0.0.1:8009` | Endpoint do `kev.serve` |
| `CELSIUS_DECISION_MODEL` | `kev-latest` | Nome aceito pelo servidor (`kev-latest`/`jev-latest`) |
| `CELSIUS_DECISION_TIMEOUT_MS` | `4000` | Timeout por request (falha = comportamento atual) |
| `CELSIUS_DECISION_GUARD_RISK_THRESHOLD` | `0.70` | Prob noul acima disso (com banda 0.15) ⇒ aprovação |
| `CELSIUS_DECISION_GUARD_UNCERTAINTY_BAND` | `0.15` | Faixa a menos do threshold considerada "incerto" |
| `CELSIUS_DECISION_RAG_RELEVANCE_THRESHOLD` | `0.60` | Score normalizado mínimo para manter chunk |
| `CELSIUS_DECISION_RAG_MAX_GATED_CHUNKS` | `5` | Cap de chunks pontuados (cada um ≈ 0.5 s) |
| `CELSIUS_DECISION_MODEL_ROUTING` | `true` | JEV escolhe o LLM baixado mais adequado por tarefa |
| `CELSIUS_DECISION_RECORD_OUTCOMES` | `true` | Grava cada gate/roteamento em `logs/decision_outcomes.jsonl` para calibração (§9) |

### 4.1 Roteamento de modelo (JEV) e pin do cliente

O Celsius roda com um único LLM carregado em GPU. O seletor de modelos na UI
tem duas naturezas:

1. **"Auto (JEV)"** (padrão): em cada mensagem, `MultiModelManager.route_and_invoke`
   faz uma passada de decisão (uma `ScoreQuestion` de 3 níveis por modelo baixado,
   "inadequado/adequado/ideal") e troca para o LLM com maior score normalizado
   (≥ `MIN_MODEL_ADEQUACY - 0.05`). Resultado fraco/erro/servidor fora ⇒ cai para
   o roteador de keyword (modelo único atual).
2. **Modelo específico**: escolher `qwen3-8b ...` etc. fixa o modelo (pin do
   cliente, `model_client_choice=true`), e o JEV de roteamento é ignorado até o
   usuário voltar para "Auto (JEV)". O pin persiste em `celsius_settings.json`
   (bloco `model`).

`CELSIUS_DECISION_MODEL_ROUTING=false` (ou `ENABLED=false`) mantém só o
roteador de keyword — comportamento antigo.

## 5. Subindo o servidor

```
powershell -ExecutionPolicy Bypass -File scripts\kev-server.ps1        # instala e sobe
powershell -ExecutionPolicy Bypass -File scripts\kev-server.ps1 -NoStart # só prepara
```

O script cria `kev-venv\`, instala `requirements-kev.txt` (torch CPU via
`--extra-index-url https://download.pytorch.org/whl/cpu`), clona o `kev` no
commit pinado `557598f` em `build\kev-src` e instala editável (com fallback
`--no-deps --ignore-requires-python` em Python ≥ 3.14).

Checagem rápida depois de subir:
`curl http://127.0.0.1:8009/v1/models` (lista os runs servidos).

## 6. Contratos System One usados

- `noul` — "sim/não": resposta `noul ∈ [0,1]` (probabilidade do sim). Usado no
  guard de ferramenta (4 perguntas: altera dados / irreversível / rede /
  destrutiva → `max(nouls)` → `noul_gate`).
- `score` — escala ordenada (níveis 0..n-1): resposta `score` = índice médio.
  Usado no gate RAG (3 níveis: irrelevante/parcial/relevante) → `score_gate`
  com `threshold - band` conservador.
- `state` + `questions` são enviados juntos por request; cada request é
  independente (~0.5 s no CPU deste projeto).

## 7. Medições (spike, CPU 6C/12T 32 GB, Windows, py3.14)

| Experimento | Resultado |
|---|---|
| Guard pt-BR (4×noul, 124 tokens) | média ≈ **558 ms**, p95 ≈ **587 ms** |
| RAG gate 1 chunk (`score`) | relevante ≈ 537 ms, irrelevante ≈ 468 ms |
| RAM do `kev.serve` | ~2.7 GB working set / ~4.6 GB private |
| Multichunk num único request | **colapsou** (todas as respostas idênticas) → usar requests individuais + cap |
| Sanity pt-BR (noul) | coerente: `modifica_dados` 0.77, `irreversivel` 0.53, `rede_externa` 0.19, `sem_pergunta` 0.25 |
| Sanity score | relevante 1.52 vs irrelevante 0.60 (escala 0–2) |
| Download | ≈ 1.0 GB (base + adapter, cache Hugging Face) |

**Ganho de latência estimado (nível de sessão — honesto):**

| Cenário | Estimativa |
|---|---|
| Passo de decisão isolado (guard/gate) | ≈ **−99%** (0.05 s vs 5–15 s do LLM) |
| Turnos com ferramentas | **−35 a −50%** |
| Mix da sessão (muitos turnos conversacionais) | **−5 a −15%** |
| Guardrails (latência) | ≈ 0% (o ganho aqui é segurança/custo) |

Caveat: o LLM grande ainda domina a geração de texto (baseline medido: mediana
12.6 s, média 31.7 s, p90 97.4 s). A camada corta *decisões*, não a redação da
resposta — os percentuais de sessão são limites superiores realistas.

## 8. Calibração e limitações (leia antes de habilitar)

- **Guard over-trigger**: com os defaults, o kev-0.5B marcou até
  `informacoes_sistema` (leitura) como alto risco (0.87). É seguro (só
  *adiciona* aprovação, nunca desaprova), mas gera ruído/atrito. Começar com
  `GUARD_RISK_THRESHOLD=0.85` e medir aprovações falsas.
- **Gate RAG ainda a calibrar**: no smoke real o kev pontuou um trecho
  *relevante* com 0.60 (norm 0.30) e o podaria com o default 0.60. O prompt/a
  escala são sensíveis ao enunciado — calibrar contra trechos reais da base
  (ajustar `RAG_RELEVANCE_THRESHOLD`, ou os critérios/enunciado da `ScoreQuestion`).
  Por isso o gate RAG vem desligado.
- **Modelo 0.5B treinado em inglês**: pt-BR funciona "razoável", mas esperar
  degradação. Elevar para `kev-0.6b` (Qwen3) se precisar de mais precisão
  (~1.2 GB); evitar `kev-0.8b`/`kev-4b` (backbone DeltaNet ruins em CPU).
- **Natureza do ganho**: a camada *reduz chamadas caras*; não substitui o
  julgamento do modelo grande em tarefas complexas.

## 9. Plano de ativação gradual

1. Subir o servidor (`scripts\kev-server.ps1`).
2. Habilitar apenas o guard de ferramentas (`ENABLED=true`,
   `RAG...` mantidos inativos via `RAG_MAX_GATED_CHUNKS=0`).
3. Medir taxa de aprovações falsas no dia a dia; ajustar `GUARD_RISK_THRESHOLD`.
4. Em staging, ligar o gate RAG com threshold baixo (ex.: 0.35) e trechos reais.
5. Acompanhar `celsius_decision_requests_total` / `celsius_decision_latency_seconds`.

**Ferramentas de calibração (criadas nesta etapa):** com
`CELSIUS_DECISION_RECORD_OUTCOMES=true` (default), cada decisão dos gates e do
roteamento é anexada a `logs/decision_outcomes.jsonl` (1 JSON por linha,
thread-safe, nunca quebra a chamada). Para o passo 3, basta sumarizar o log:

```python
from core.decision_calibration import load_outcomes, summarize_outcomes, default_outcomes_path
summary = summarize_outcomes(load_outcomes(default_outcomes_path()))
# {'tool_guard': {'n', 'predicted_true', 'rate', 'mean_value'}, ...}
```

Para calibrar os thresholds com um conjunto etiquetado de sondas (rotule as
entradas com `label: 1` = risco/relevante, `0` = seguro/irrelevante e o valor
medido em `probability`/`normalized`):

```python
from core.decision_calibration import recommend_guard_threshold, recommend_score_threshold, report_pretty
report = recommend_guard_threshold(sondas_noul)   # -> CELSIUS_DECISION_GUARD_RISK_THRESHOLD
report_rag = recommend_score_threshold(sondas_score)  # -> CELSIUS_DECISION_RAG_RELEVANCE_THRESHOLD
print(report_pretty(report), report_pretty(report_rag))
```

Os relatórios usam balanced accuracy (imune a desbalanceamento de classes),
com grid padrão 0.50–0.95 (guard) e 0.10–0.90 (RAG); grids custom via `grid=`.

## 11. Integração com modos agênticos e API

A camada de decisão agora opera dentro dos seis **modos agênticos** definidos em
`core/agent_modes.py`: `assistente`, `executor`, `documentos`, `estoque`,
`pesquisador` e `desenvolvedor`. Cada modo tem:

- Allowlist de ferramentas permitidas (o guard de decisão só roda para ferramentas
  dentro do allowlist do modo ativo).
- Flags `can_plan`, `network`, `confirm_before_write` e limites `max_steps`,
  `max_seconds` (aplicados em `ai/task_runtime.py`).
- Persistência por turno via `agent_mode` no prompt (`ChatJob.agent_mode` /
  `agent_tasks.AgentTaskStore.create(mode=...)`).

### 11.1 Superfícies suportadas

| Superfície | Como o modo é selecionado | Persistência |
|---|---|---|
| Desktop (Qt) | `ModernInputArea.mode_combo` + `change_mode` signal | `input_area.set_mode()` |
| Web (static) | `modeSelect` + `localStorage` `celsius-agent-mode` | por sessão do navegador |
| API HTTP | `POST /api/v1/agents/mode` (scope=conversation) | por conversa, emit event |
| Celular/voz | Comando `"modo <nome>"` → `_apply_mode_command()` | mesma sessão desktop |

O modo **assistente** (padrão) não planeja tarefas (`can_plan=False`) — `TAREFA:`
é rejeitado com mensagem orientativa. Os demais modos permitem tarefas de
múltiplos passos com budget congelado no momento da criação
(`resolve_task_limits` → `task["limits"]`).

### 11.2 Endpoints HTTP novos

```
GET  /api/v1/agents/modes              # catálogo completo
GET  /api/v1/agents/modes/{id}         # detalhe do modo
GET  /api/v1/agents/tools              # política por ferramenta (risk_label)
GET  /api/v1/agents/health             # estado Jev + detalhes
GET  /api/v1/agents/tasks              # lista tarefas da conversa (scope)
POST /api/v1/agents/mode               # seleciona modo (query scope, body {mode})
```

Todos exigem autenticação (`require_access` / pairing token).

### 11.3 Saúde exposta na UI
 
 `GET /agents/health` retorna `{ state: "off" | "available" | "unavailable",
 detail: "..." }`. O `app.js` carrega em `loadAgentHealth()` e exibe no
 `modeHealth` (badge verde/laranja).

## 12. Painel de Tarefas (Desktop e Web)

### 12.1 Desktop (Qt)
O painel de tarefas no desktop (`ui/task_panel.py`) exibe:
- Seletor de modo agêntico (6 modos: assistente, executor, documentos, estoque, pesquisador, desenvolvedor)
- Indicador do modo ativo
- Painel do plano da tarefa com passos numerados
- Etapa atual destacada
- Estado da tarefa (created/planning/waiting_confirmation/running/paused/cancelled/failed/completed)
- Lista de passos executados com:
  - Ferramenta usada
  - Argumentos (truncados)
  - Status (planejado/aguardando/autorizado/executando/sucesso/falha/cancelado)
  - Resultado ou erro
- Botões de ação: Confirmar, Cancelar, Pausar, Continuar
- Histórico de tarefas da conversa
- Indicador de tarefa aguardando confirmação
- Indicador de Jev indisponível ou em fallback

### 12.2 Web (HTTP API)
Novos endpoints em `/api/v1/agents/`:
- `GET /agents/tasks/{task_id}` — detalhes completos da tarefa (plano, passos, resultado)
- `GET /agents/tasks/{task_id}/plan` — plano da tarefa
- `GET /agents/tasks/{task_id}/steps` — todos os passos com status atual
- `POST /agents/tasks/{task_id}/confirm` — confirma ação pendente (approval_code)
- `POST /agents/tasks/{task_id}/cancel` — cancela tarefa
- `GET /agents/tasks/{task_id}/history` — log de execução
- `GET /agents/mode/current` — modo agêntico atual da conversa

Todos testados em `tests/test_web_agents.py`.

## 13. Integração Voz/Jarvis/Celular

Comandos de voz suportados (com e sem prefixo "Celsius"):
- "Celsius, entre no modo estoque" / "modo estoque"
- "Celsius, entre no modo executor" / "modo executor"
- "Consulte o andamento da tarefa" / "andamento da tarefa"
- "Cancele a tarefa" / "cancelar tarefa"
- "Confirma" / "confirmar" / "autorizar"
- "Não confirme" / "não confirmar" / "rejeitar"
- "Pause a tarefa" / "pausar tarefa"
- "Continue a tarefa" / "continuar tarefa" / "retomar tarefa"

Regras:
- Silêncio **nunca** é interpretado como confirmação
- Confirmação explícita obrigatória para ações sensíveis
- Funciona tanto no desktop quanto no celular
- Estado da tarefa informado por voz
- Erro compreensível quando não há tarefa ativa
- Confirmações não misturam tarefas diferentes

Implementado em `ui/window.py` (`_apply_task_voice_command`, `_queue_mobile_voice_command`).

## 14. Segurança Implementada

### 14.1 Sandbox de Execução (`core/sandbox.py`)
- Execução somente dentro da sandbox prevista
- Limite de tempo CPU (configurável, default 30s)
- Limite de memória (configurável, default 256 MB)
- Limite de saída (default 50 KB)
- Bloqueio de acesso à rede quando configurado (`network_disabled=True` no Docker)
- Cancelamento cooperativo via timeout
- Fallback seguro quando sandbox falha (retorna erro, não executa)

### 14.2 Proteção de Arquivos (`core/file_security.py`)
- Impede acesso fora das raízes permitidas (`set_allowed_roots`)
- Bloqueia travessia de caminho (`../etc/passwd` → erro)
- Exige confirmação antes de sobrescrever, mover ou excluir (`require_write_confirmation`)
- Rejeita caminhos ambíguos
- Testes em `tests/test_file_security.py`

### 14.3 Auditoria (`core/audit_log.py`)
Registro JSONL em `logs/audit.jsonl` com:
- Identificador da tarefa, modo, usuário, horário
- Etapa, ferramenta, argumentos resumidos
- Decisão do Jev, decisão da política determinística
- Confirmação recebida, resultado, erro, cancelamento
- Não grava segredos, tokens ou conteúdo sensível desnecessário

## 15. Política de Ferramentas por Modo

Garantias implementadas:
- Cada modo tem allowlist própria (`core/agent_modes.py`)
- Ferramentas fora da allowlist são bloqueadas (`filter_tools`)
- Ferramentas sensíveis sempre exigem confirmação (`CONFIRMING_RISKS`)
- Jev **só pode adicionar** confirmação, nunca remover (`evaluate_tool_call` monotonicidade)
- Fallback fail-closed para ações perigosas (servidor Jev fora → política determinística)
- Consultas simples não bloqueadas sem motivo (risk=READ → sem confirmação)
- Entradas e saídas de estoque mostram saldo anterior e posterior antes da confirmação

Testes para os 6 modos em `tests/test_agent_modes.py` e `tests/test_tool_policy.py`.

## 16. Smoke Test Real Jev/Kev

Script: `scripts/jev_smoke_test.py`

Valida:
- Health check (`GET /v1/models`)
- Decisão `noul` (sim/não)
- Decisão `score` (escala ordenada)
- Decisão `choice` (escolha múltipla)
- Roteamento entre 2+ modelos instalados
- Guard de ferramenta
- Gate RAG
- Fallback com servidor desligado

Registra latência, provedor, modelo, resposta e comportamento de fallback.
Resultados salvos em `jev_smoke_test_results.json`.

## 17. Testes e Isolamento

- Não usa `data/celsius_settings.json` real (conftest.py define `CELSIUS_PREFERENCES_FILE` temporário)
- Diretórios temporários via `tmp_path` fixture
- Modelo padrão explícito em cada fixture
- Testes com modelo fixado e "Auto (JEV)"
- Cobertura do modelo dinâmico `qwen-heretic-q4_k_m` (descoberto via `discover_installed_models`)
- Limpeza de temporários criados pelo conftest
- Suite completa: **1134 passed, 3 skipped, 0 failed**

## 18. Documentação Atualizada

### 18.1 Limitações Conhecidas
- Jev/Kev **não elimina alucinações** nem garante decisões corretas
- Resultados são **decisões estruturadas com probabilidades e confiança**
- Modelo 0.5B treinado em inglês: pt-BR funciona "razoável", esperar degradação
- Gate RAG ainda em calibração (desligado por padrão)
- Guard over-trigger com defaults: `informacoes_sistema` marcado como risco 0.87

### 18.2 Estado das Funcionalidades

| Funcionalidade | Estado |
|---|---|
| Roteamento Jev → MultiModelManager | **Implementada e habilitada** |
| Painel tarefas Desktop | **Implementada e habilitada** |
| Painel tarefas Web (API) | **Implementada e habilitada** |
| Comandos voz tarefas | **Implementada e habilitada** |
| Sandbox execução | **Implementada e habilitada** |
| Proteção arquivos | **Implementada e habilitada** |
| Auditoria JSONL | **Implementada e habilitada** |
| Política ferramentas por modo | **Implementada e habilitada** |
| Smoke test Jev/Kev | **Implementado (script)** |
| Isolamento testes | **Implementado** |
| Gate RAG | **Em calibração** (desligado por padrão) |
| Modelo Jev 0.6b+ | **Experimental** |

### 18.3 Exemplos de Comandos

**Texto:**
```
modo estoque
TAREFA: verificar itens abaixo do mínimo e gerar relatório
confirma ABC123
cancele a tarefa
```

**Voz:**
- "Celsius, entre no modo executor"
- "Consulte o andamento da tarefa"
- "Confirma"
- "Não confirme"
- "Pause a tarefa"
- "Continue a tarefa"

### 18.4 Como Executar com Jev/Kev

1. Subir servidor: `powershell -ExecutionPolicy Bypass -File scripts\kev-server.ps1`
2. Configurar `.env`:
   ```
   CELSIUS_DECISION_ENABLED=true
   CELSIUS_DECISION_BASE_URL=http://127.0.0.1:8009
   CELSIUS_DECISION_MODEL_ROUTING=true
   ```
3. No desktop: selecionar "Auto (JEV)" no seletor de modelos
4. No web: o modo "Auto (JEV)" é padrão quando a camada está habilitada

### 18.5 Diferenças entre Estados

| Estado | Descrição |
|---|---|
| **Implementada** | Código existe, testado, integrado |
| **Habilitada** | Funcionalidade ativa por padrão ou via config |
| **Em calibração** | Funcional mas precisa ajuste de thresholds (ex: gate RAG) |
| **Experimental** | Pode mudar, não recomendado para produção (ex: Jev 0.6b+) |