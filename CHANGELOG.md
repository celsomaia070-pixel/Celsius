# Changelog

## Em desenvolvimento

- Adicionado preenchimento real de formularios DOCX e PDFs AcroForm, incluindo
  deteccao de campos e caixas de selecao, copia de dados entre documentos,
  confirmacao antes da escrita e download persistente pelo chat.
- Implementado runtime multiagente real no modo Work, com contextos isolados,
  supervisor sem ferramentas, checkpoints SQLite e retomada após autorização.
- Endurecida a autenticação com tokens persistidos por hash, cookies `HttpOnly`,
  limitação de login, famílias de sessão e remoção do token do `localStorage`.
- Corrigidas pesquisa de notícias por semana-calendário, coerência das políticas
  de ferramentas, cache de memória SQLite/WAL e detecção do Ryzen 5 5500.
- Adicionados supervisor local do KEV/JEV, sandbox Docker automático, diretórios
  privados, agendamentos com lease/retry e detalhes de agentes no painel Work.
- Ruff, mypy, Bandit e auditoria de dependências foram convertidos em verificações
  reproduzíveis de CI; a exceção transitiva de `diskcache` permanece documentada
  até existir uma versão corrigida.

Todas as mudancas importantes do projeto devem ser registradas aqui.

O formato segue a ideia de secoes por versao:

- `Added`: novas funcionalidades.
- `Changed`: mudancas em comportamento existente.
- `Fixed`: correcoes de bugs.
- `Security`: correcoes de seguranca.

## [Unreleased]

### Added

- Documentacao organizada em `docs/`.
- Templates de issue e pull request no GitHub.
- Configuracao do Dependabot.

### Changed

- README simplificado como porta de entrada do projeto.
- Guia de build movido para `docs/BUILD.md`.
- Guia do iniciante movido para `docs/GUIA_INICIANTE.md`.

## [1.0.0] - 2026-09-26

### Fixed

- Corrigidos problemas de linting (whitespace em linhas vazias, imports nao utilizados, type annotations `Optional` -> `X | None`) em `ui/task_panel.py` e `ui/window.py`
- Corrigidos testes `test_file_security.py` para usar `pytest.raises` em vez de `assert False`
- Corrigido `scripts/jev_smoke_test.py` removendo variaveis nao utilizadas
- Corrigido `core/file_security.py` usando `raise ... from exc` para preservar cadeia de excecoes
- Corrigido `core/web_api/agents.py` usando operador ternario em vez de if-else

### Changed

- Validacao completa da arquitetura Jev/Kev: inicializacao, health check, fallback, roteamento automatico, escolha manual e preservacao de contexto
- Revisao da politica de ferramentas: confirmacoes indevidas corrigidas, acoes sensiveis protegidas, calibracao portugues, gate RAG revisado
- Validacao de seguranca e auditoria: sandbox, protecao de arquivos, allowlists, cancelamento, registros de auditoria
- Revisao da interface agentica: painel desktop, interface web, planos, etapas, confirmacao, cancelamento, historico
- Testes de voz e celular: comandos de modo, consulta, confirmacao, pausa, continuacao, cancelamento
- Testes ponta a ponta: tarefa completa no desktop, web e celular com Jev ativo e desligado

### Security

- Sandbox hardening: imports bloqueados, funcoes perigosas, atributos restritos
- Path traversal protection em `core/file_security.py`
- Tool approval system com one-time codes
- Audit logging para acoes de tarefas e decisoes Jev
