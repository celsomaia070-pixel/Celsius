# Configuracao

O Celsius usa `core/settings.py` como fonte principal de configuracao. Valores
podem ser sobrescritos por variaveis de ambiente ou por um arquivo `.env`.

## Criar `.env`

```powershell
Copy-Item .env.example .env
```

O `.env` e local e nao deve ser commitado.

## Prefixos

As variaveis usam o prefixo `CELSIUS_`.

Exemplos:

```env
CELSIUS_ENVIRONMENT=development
CELSIUS_MODEL_LLM_MODEL=qwen2.5-vl-7b-q4km
CELSIUS_MODEL_NUM_CTX=16384
CELSIUS_TELEMETRY_ENABLED=false
```

## Modelos

Configuracoes principais:

```env
CELSIUS_MODEL_DEFAULT_LLM_MODEL=qwen2.5-vl-7b-q4km
CELSIUS_MODEL_LLM_MODEL=qwen2.5-vl-7b-q4km
CELSIUS_MODEL_FAST_LLM_MODEL=llama3.2-3b-q5km
CELSIUS_MODEL_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
CELSIUS_MODEL_NUM_CTX=16384
CELSIUS_MODEL_NUM_PREDICT=2500
CELSIUS_MODEL_N_GPU_LAYERS=-1
```

## Hardware

```env
CELSIUS_HARDWARE_AUTO_DETECT=true
CELSIUS_HARDWARE_FORCE_MODE=auto
CELSIUS_HARDWARE_PREFER_MULTIMODAL=true
```

Modos esperados:

- `auto`: detecta automaticamente.
- `leve`: prioriza modelos menores.
- `completo`: prioriza qualidade.
- `custom`: usa valores definidos manualmente.

## RAG

```env
CELSIUS_RAG_CHUNK_SIZE=600
CELSIUS_RAG_CHUNK_OVERLAP=80
CELSIUS_RAG_TOP_K=5
CELSIUS_RAG_ENABLE_HYBRID_SEARCH=true
CELSIUS_RAG_BM25_WEIGHT=0.3
CELSIUS_RAG_DENSE_WEIGHT=0.7
```

## Memoria

```env
CELSIUS_MEMORY_MAX_HISTORY_SESSION=16
CELSIUS_MEMORY_MEMORY_THRESHOLD=0.15
CELSIUS_MEMORY_TOP_MEMORIES=10
```

## Arquivos

```env
CELSIUS_FILE_MAX_FILE_SIZE_MB=50
CELSIUS_FILE_DOC_TEXT_LIMIT=12000
```

## Seguranca

```env
CELSIUS_SECURITY_SANDBOX_ENABLED=true
CELSIUS_SECURITY_SANDBOX_MAX_MEMORY_MB=256
CELSIUS_SECURITY_SANDBOX_MAX_CPU_SECONDS=30
```

## Telemetria

A telemetria vem desligada por padrao.

```env
CELSIUS_TELEMETRY_ENABLED=false
CELSIUS_TELEMETRY_OTLP_ENDPOINT=http://localhost:4317
CELSIUS_TELEMETRY_METRICS_ENABLED=true
CELSIUS_TELEMETRY_METRICS_PORT=9090
```

## UI

```env
CELSIUS_UI_THEME=system
CELSIUS_UI_LANGUAGE=pt-BR
CELSIUS_UI_SHOW_SIDEBAR=true
```

## Feature Flags

```env
CELSIUS_FEATURE_RAG=true
CELSIUS_FEATURE_MEMORY=true
CELSIUS_FEATURE_WEB_SEARCH=true
CELSIUS_FEATURE_WEB_BROWSER=true
CELSIUS_FEATURE_CODE_EXECUTION=true
CELSIUS_FEATURE_VOICE_INPUT=true
CELSIUS_FEATURE_VOICE_OUTPUT=true
CELSIUS_FEATURE_IMAGE_ANALYSIS=true
```
