# Documentacao do Celsius

Use este indice para encontrar rapidamente o guia certo.

## Para Usar o Projeto

- [Guia do iniciante](GUIA_INICIANTE.md): instalacao, venv, dependencias e testes.
- [Configuracao](CONFIGURATION.md): `.env`, modelos, RAG, memoria, voz e seguranca.

## Para Desenvolver

- [Desenvolvimento](DEVELOPMENT.md): fluxo local, testes, lint e boas praticas.
- [Arquitetura](ARCHITECTURE.md): visao dos modulos e fluxo interno.
- [Modulos empresariais](MODULES.md): estrutura dos cadastros, fluxos e areas por empresa.
- [Migracao web local](WEB_MIGRATION.md): API local, eventos e transicao incremental da interface.
- [Privacidade e protecao de dados](PRIVACY.md): postura local, recursos externos e lacunas LGPD.

## Para Distribuir

- [Build e instalador](BUILD.md): PyInstaller, Inno Setup, modelos e licencas.
- [Politica de seguranca](../SECURITY.md): sandbox, vulnerabilidades e supply chain.

## Arquivos Importantes na Raiz

- `README.md`: resumo publico do projeto.
- `pyproject.toml`: metadados e configuracao de ferramentas.
- `pyproject.toml`: fonte unica das dependencias e configuracoes de ferramentas.
- `requirements.txt`: lista de execucao gerada para compatibilidade com `pip -r`.
- `requirements-dev.in`: lista de desenvolvimento gerada para compatibilidade.
- `.env.example`: exemplo de configuracao local.
- `.gitignore`: arquivos que nao devem entrar no Git.
