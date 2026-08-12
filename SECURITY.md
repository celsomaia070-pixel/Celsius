# Security Policy

## Supported Versions

Enquanto o projeto estiver em fase beta, correcao de seguranca deve priorizar a
branch `main`.

| Version | Supported |
|---|---|
| `main` | Yes |
| Older local builds | Best effort |

## Reporting a Vulnerability

Nao publique segredos, chaves privadas, licencas ou payloads exploraveis em
issues publicas.

Preferencias:

1. Use o recurso de private vulnerability reporting do GitHub, se estiver
   habilitado no repositorio.
2. Caso contrario, abra uma issue sem detalhes exploraveis e marque como
   `security`.

Inclua, quando possivel:

- Versao/commit afetado.
- Sistema operacional.
- Passos gerais para reproduzir.
- Impacto esperado.
- Se envolve sandbox, arquivos locais, licencas, modelos ou rede.

## Security Scope

Areas sensiveis do Celsius:

- Sandbox de execucao de codigo.
- Processamento de anexos.
- Download de modelos.
- Licenciamento e chaves.
- Persistencia local de conversas, memoria e estoque.
- Automacao web.
- Telemetria e metricas.

## Sandbox

O Celsius executa codigo Python fornecido pelo usuario em ambiente restrito.
Toda execucao solicitada pelo LLM exige uma segunda confirmacao do usuario,
vinculada aos argumentos exibidos e com codigo de uso unico.

Camadas atuais:

| Camada | Unix/Linux | Windows |
|---|---|---|
| Analise AST | Bloqueia imports e atributos perigosos | Mesmo comportamento |
| Builtins restritos | Remove funcoes perigosas | Mesmo comportamento |
| CPU | `resource.RLIMIT_CPU` | Job Object/timeout |
| Memoria | `resource.RLIMIT_AS` | Job Object |
| Arquivos | Limites e validacao de caminho | Validacao e timeout |
| Rede | Imports/referencias bloqueados | Mesmo comportamento |

## Known Limitations

- A analise estatica e apenas uma camada; o subprocesso recebe builtins e imports
  reduzidos, e a execucao falha se os limites do Job Object nao forem aplicados.
- Windows nao oferece o mesmo isolamento de filesystem que containers dedicados.
- O sandbox reduz risco, mas nao deve ser tratado como ambiente seguro para
  codigo hostil de alta confianca.
- Modelos e dependencias externas devem ser tratados como cadeia de suprimentos.

## Supply Chain

Controles usados no repositorio:

- `ruff` para lint.
- `pytest` para regressao automatizada.
- `bandit` para varredura de seguranca em Python.
- `pip-audit` para vulnerabilidades conhecidas em dependencias.
- Dependabot para dependencias Python e GitHub Actions.
- `pylock.toml` (PEP 751) com versoes e hashes para builds reproduziveis.

Algumas vulnerabilidades transitivas podem ser aceitas temporariamente no CI
quando nao houver correcao compativel ou quando o pacote afetado nao for usado em
modo servidor/exposto. Essas excecoes devem ficar explicitas no workflow e ser
revisadas quando Dependabot abrir atualizacoes.

Excecao temporaria atual: `PYSEC-2026-2447` em `diskcache`, dependencia de
`llama-cpp-python`. Nao existe versao corrigida publicada; o Celsius nao fornece
caminhos de cache nao confiaveis a essa biblioteca.

`PYSEC-2026-311` em `chromadb` tambem e acompanhada: a vulnerabilidade exige o
servidor HTTP Chroma e seu endpoint de criacao de colecoes. O Celsius usa somente
o cliente persistente incorporado e nao inicia nem publica esse servidor.

Antes de distribuir builds:

```powershell
python -m ruff check .
python -m pytest -q
python scripts\security_scan.py
python tools\lock_requirements.py --check
```
