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

- Analise estatica nao cobre todos os ataques de runtime.
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

Algumas vulnerabilidades transitivas podem ser aceitas temporariamente no CI
quando nao houver correcao compativel ou quando o pacote afetado nao for usado em
modo servidor/exposto. Essas excecoes devem ficar explicitas no workflow e ser
revisadas quando Dependabot abrir atualizacoes.

Antes de distribuir builds:

```powershell
python -m ruff check .
python -m pytest -q
python scripts\security_scan.py
```
