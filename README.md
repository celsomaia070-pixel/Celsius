# Celsius

Assistente de IA para Windows que roda modelos GGUF no próprio computador. O Celsius reúne chat, voz, leitura de arquivos, busca em documentos, agentes com ferramentas e módulos de gestão em uma aplicação desktop feita com Python e PySide6.

O processamento de documentos, a busca local (RAG) e a inferência funcionam sem conexão com a internet. Pesquisa na web, navegação e integrações externas são recursos opcionais e precisam de rede quando usados.

> **Estado do projeto:** em desenvolvimento ativo. Algumas funções dependem de modelos, programas ou serviços adicionais configurados pelo usuário.

## O que o Celsius faz

- **Conversa local:** usa modelos GGUF por meio de `llama-cpp-python`, com aceleração por GPU quando disponível e alternativa em CPU.
- **Documentos e conhecimento:** lê PDF, DOCX, planilhas, formatos OpenDocument, imagens e áudio; indexa conteúdo e combina busca vetorial local com BM25.
- **Formulários e relatórios:** inspeciona e preenche formulários DOCX e PDF em uma nova cópia, além de gerar documentos, relatórios e gráficos.
- **Voz:** transcreve áudio localmente e oferece síntese de fala. Alguns provedores de voz podem precisar de internet.
- **Agentes com limites:** oferece os modos assistente, executor, documentos, estoque, pesquisador e desenvolvedor. Tarefas podem ser acompanhadas, pausadas, retomadas ou canceladas; operações de escrita sujeitas à política de segurança exigem confirmação.
- **Gestão da empresa:** inclui estoque em Kanban, clientes, fornecedores, produtos e serviços, orçamentos, agenda e processos. Os módulos exibidos podem ser escolhidos nas configurações.
- **Acesso local pelo navegador e celular:** além da interface desktop, oferece uma interface web no PC e pareamento opcional com celular na mesma rede local.
- **Pesquisa e automação web:** disponíveis quando configuradas, com acesso à rede apenas para essas ações.

O projeto também contém suporte a integrações externas, incluindo WhatsApp. Elas são opcionais e não fazem parte do fluxo local de inferência e documentos.

## Requisitos

- Windows 10 ou 11 e Python 3.10 ou superior.
- Espaço em disco e memória compatíveis com o modelo GGUF escolhido. O repositório não inclui modelos.
- FFmpeg para funções de áudio.
- Git para clonar o código; Chromium do Playwright para navegação automatizada.
- GPU compatível é recomendada, mas a execução em CPU é possível.

## Começar

No PowerShell:

```powershell
git clone https://github.com/celsomaia070-pixel/Celsius.git
cd Celsius
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

Configure ou obtenha um modelo GGUF antes de usar o chat. Os modelos e outros recursos grandes ficam fora do Git. Veja o [guia do iniciante](docs/GUIA_INICIANTE.md) e a [configuração](docs/CONFIGURATION.md) para os próximos passos.

Se o PowerShell impedir a ativação do ambiente virtual, execute `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` e tente ativá-lo novamente.

### Interface web local

```powershell
python -m core.web_api
```

Abra `http://127.0.0.1:8790/app` no próprio computador. O acesso pelo celular é ativado separadamente nas configurações, com token de pareamento; ele fica desligado por padrão.

## Configuração e privacidade

As configurações usam variáveis com prefixo `CELSIUS_` e podem ser definidas em um `.env` local criado a partir de `.env.example`:

```powershell
Copy-Item .env.example .env
```

Conversas, modelos, índices, dados da empresa e credenciais locais não devem ser enviados ao repositório. O núcleo de documentos, RAG e inferência não faz chamadas de rede. Recursos como pesquisa web, integrações e alguns serviços de voz têm requisitos próprios de conexão. Consulte [Privacidade](docs/PRIVACY.md) e [Segurança](SECURITY.md).

## Desenvolvimento

Instale também as dependências de desenvolvimento e rode as verificações antes de enviar alterações:

```powershell
python -m pip install -r requirements-dev.in
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

`pyproject.toml` é a fonte de verdade das dependências; `requirements.txt` e `requirements-dev.in` são arquivos gerados para instalação. Veja [Desenvolvimento](docs/DEVELOPMENT.md), [Arquitetura](docs/ARCHITECTURE.md) e [Como contribuir](CONTRIBUTING.md). Para colaborar, crie uma branch, valide a mudança e abra um pull request.

## Organização do código

| Pasta | Conteúdo |
| --- | --- |
| `ai/` | Motor de IA, agentes, RAG e ferramentas |
| `core/` | Configuração, segurança, persistência, serviços e API web |
| `processors/` | Leitura e extração de conteúdo de arquivos |
| `workers/` | Tarefas em segundo plano para manter a interface responsiva |
| `ui/` | Interface desktop PySide6 |
| `tests/` | Testes automatizados |
| `docs/` | Guias e detalhes técnicos |
| `installer/` | Empacotamento para Windows |

Consulte o [índice da documentação](docs/README.md) para os demais guias.

## Licença

MIT.
