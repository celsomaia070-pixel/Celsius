# Build e Instalador

Este guia explica como gerar o executavel e o instalador do Celsius.

## Pre-requisitos

- Python 3.10 ou superior.
- Dependencias instaladas em um ambiente virtual.
- PyInstaller.
- Inno Setup 6, apenas para instalador Windows.
- Espaco em disco para `build/`, `dist/` e modelos locais.

Instalacao basica:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

## Modelos GGUF

O instalador padrao nao embute modelos. O aplicativo baixa os modelos sob
demanda no primeiro uso para `%LOCALAPPDATA%\Celsius\models`, usando a
configuracao de `core/config.py` e `core/settings.py`.

Isso deixa o instalador menor e evita distribuir arquivos de varios GB pelo Git.

Para um pacote offline com modelos embutidos:

```powershell
installer\build.bat offline installer
```

O pacote offline inclui o Qwen2.5 VL 7B e o projetor visual. Ele e muito maior,
mas nao depende de download do LLM no computador do cliente.

Arquivos `.gguf`, `resources/`, caches e dados locais devem continuar fora do Git.

## Gerar Executavel

```powershell
installer\build.bat thin exe
```

Saida esperada:

```text
dist/Celsius/Celsius.exe
```

## Gerar Instalador Windows

```powershell
installer\build.bat thin installer
```

Saida esperada:

```text
dist/Celsius-Setup-v1.0.0.exe
```

Se precisar chamar o Inno Setup manualmente:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\celsius.iss
```

## Licenciamento e Trial

O codigo de licenciamento esta preparado, mas a ativacao comercial deve ser
habilitada apenas depois de criar um par de chaves real. A chave privada nunca
pode entrar no repositorio, no executavel ou no instalador.

Gerar par de chaves:

```powershell
python tools\generate_license.py keypair --output keys
```

Gerar licenca:

```powershell
python tools\generate_license.py license `
  --customer "Nome do Cliente" `
  --email "cliente@email.com" `
  --days 365 `
  --private-key keys\private_key.pem `
  --save licenses.json
```

Copie somente `keys\public_key.pem` para
`resources\license_public_key.pem` antes do build comercial. Guarde
`private_key.pem` fora do projeto e com backup seguro.

Verificar trials:

```powershell
python tools\generate_license.py trials
```

Arquivos como `keys/`, `licenses.json` e `*.pem` nao devem ser commitados.

## Checklist Antes de Distribuir

- `python -m ruff check .`
- `python -m pytest -q`
- `python tools\release_preflight.py --flavor thin`
- Abrir `dist/Celsius/Celsius.exe` localmente.
- Conferir `%LOCALAPPDATA%\Celsius\logs\self-test.json`.
- Testar primeira execucao sem modelo baixado.
- Testar ativacao/trial.
- Confirmar que nenhum segredo foi incluido no commit.

## Problemas Comuns

| Problema | Possivel solucao |
|---|---|
| Modelo nao encontrado | Rode o app online uma vez ou coloque o GGUF em `resources/` |
| GPU nao detectada | Verifique driver/Vulkan ou use fallback CPU |
| Sem memoria | Use modelo menor ou quantizacao menor |
| Visao nao funciona | Confirme modelo multimodal e `mmproj` correto |
| Inno Setup nao encontrado | Instale o Inno Setup ou corrija o caminho do `ISCC.exe` |

## Dados do Cliente

Builds instalados gravam configuracoes e dados em `%LOCALAPPDATA%\Celsius`.
Atualizacoes e desinstalacoes nao removem automaticamente estoque, conversas,
agenda, documentos indexados ou perfil da empresa.

Principais pastas:

```text
%LOCALAPPDATA%\Celsius\data
%LOCALAPPDATA%\Celsius\models
%LOCALAPPDATA%\Celsius\logs
```
