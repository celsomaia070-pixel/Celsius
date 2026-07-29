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

## Identidade do Assistente

```env
CELSIUS_ASSISTANT_OWNER_NAME=
```

A identidade do produto e fixa: **Celsius, Agente Multimodal Local de IA**.
`CELSIUS_ASSISTANT_OWNER_NAME` e mantido apenas por compatibilidade. Para novas
instalacoes, use o perfil do cliente/empresa abaixo.

## Perfil do Cliente/Empresa

O perfil informa ao Celsius para quem ele esta trabalhando naquela instalacao
local. Ele nao altera a identidade fixa do produto; apenas adiciona contexto
empresarial ao prompt.

O usuario pode preencher esse perfil pela tela **Configuracoes**. O Celsius salva
os dados localmente em:

```text
data/customer_profile.json
```

Tambem e possivel configurar por `.env`:

```env
CELSIUS_CUSTOMER_USER_NAME=Celso Maia
CELSIUS_CUSTOMER_COMPANY_NAME=Minha Empresa
CELSIUS_CUSTOMER_COMPANY_SECTOR=Varejo, servicos, estoque, financeiro
CELSIUS_CUSTOMER_COMPANY_SIZE=Pequena empresa
CELSIUS_CUSTOMER_USER_ROLE=Proprietario
CELSIUS_CUSTOMER_PREFERRED_TONE=profissional e direto
CELSIUS_CUSTOMER_BUSINESS_CONTEXT=Atende clientes locais, controla estoque e fornecedores.
CELSIUS_CUSTOMER_TIMEZONE=America/Sao_Paulo
CELSIUS_CUSTOMER_LOCAL_OFFLINE_REQUIRED=true
```

Variaveis de ambiente tem prioridade sobre o arquivo local. Quando o perfil esta
preenchido, o Celsius inclui no prompt um bloco com usuario, empresa, setor,
papel, tom preferido, privacidade e contexto de negocio.

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

## Estilo das Respostas

O Celsius usa `natural` por padrao para evitar respostas engessadas. A tela
**Configuracoes** tambem permite alterar essas preferencias, salvas localmente em
`data/celsius_settings.json`.

```env
CELSIUS_RESPONSE_MODE=natural
CELSIUS_RESPONSE_TEMPERATURE=0.45
CELSIUS_RESPONSE_TOP_P=0.9
CELSIUS_RESPONSE_SHORT_ANSWER_MAX_CHARS=180
CELSIUS_RESPONSE_MAX_SIMPLE_SENTENCES=3
```

Modos:

- `natural`: respostas curtas quando a pergunta for simples.
- `tecnico`: mais criterios, riscos, passos e verificacao.
- `relatorio`: mais estrutura executiva, tabelas e proximas acoes.

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
CELSIUS_SECURITY_ALLOWED_FILE_ROOTS=["E:/PythonProjectCELSIUS","E:/Empresa/Documentos"]
```

Quando `CELSIUS_SECURITY_ALLOWED_FILE_ROOTS` fica vazio, as ferramentas de
arquivo podem acessar apenas a pasta base do aplicativo. Use uma lista JSON para
autorizar outras pastas da empresa.

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
CELSIUS_UI_THEME=light
CELSIUS_UI_LANGUAGE=pt-BR
CELSIUS_UI_SHOW_SIDEBAR=true
CELSIUS_UI_JARVIS_ENABLED=true
CELSIUS_UI_JARVIS_PARTICLE_COUNT=800
CELSIUS_UI_JARVIS_FPS=60
```

## Voz

Configuracao padrao recomendada para portugues do Brasil:

```env
CELSIUS_VOICE_ENABLED=true
CELSIUS_VOICE_PROVIDER=edge-tts
CELSIUS_VOICE_VOICE=pt-BR-AntonioNeural
CELSIUS_VOICE_RATE=+5%
CELSIUS_VOICE_PITCH=-2Hz
CELSIUS_VOICE_VOLUME=+0%
CELSIUS_VOICE_MAX_PLAYBACK_MS=120000
```

Vozes uteis para testar:

- `pt-BR-AntonioNeural`: masculina, calma e adequada para assistente local.
- `pt-BR-FranciscaNeural`: feminina, natural e clara.
- `pt-BR-BrendaNeural`: feminina, mais leve.
- `pt-BR-DonatoNeural`: masculina, alternativa ao Antonio.

## Acesso Pelo Celular

O acesso pelo celular fica desligado por padrao. Em `Configuracoes > Celular`,
use `Parear celular` para ativar o acesso local e abrir o QR Code. O Celsius cria
um servidor local com token de pareamento e, por padrao, HTTPS local com
certificado autoassinado salvo em `data/mobile_access`. Use `Regenerar token`
quando quiser invalidar links antigos.

```env
CELSIUS_MOBILE_ENABLED=false
CELSIUS_MOBILE_HOST=0.0.0.0
CELSIUS_MOBILE_PORT=8787
CELSIUS_MOBILE_ALLOW_LAN=false
CELSIUS_MOBILE_VOICE_COMMANDS_ENABLED=true
CELSIUS_MOBILE_USE_HTTPS=true
CELSIUS_MOBILE_PAIRING_TOKEN=
```

Em rede local, o celular pode mostrar um aviso de certificado na primeira
abertura. Isso e esperado para certificado autoassinado. O token no link de
pareamento deve ser tratado como dado sensivel.

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
