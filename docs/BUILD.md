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
demanda no primeiro uso, usando a configuracao de `core/config.py` e
`core/settings.py`.

Isso deixa o instalador menor e evita distribuir arquivos de varios GB pelo Git.

Para um pacote offline com modelos embutidos:

```powershell
$env:CELSIUS_BUNDLE_MODELS = "1"
pyinstaller celsius.spec --clean
```

Arquivos `.gguf`, `resources/`, caches e dados locais devem continuar fora do Git.

## Gerar Executavel

```powershell
pyinstaller celsius.spec --clean
```

Saida esperada:

```text
dist/Celsius/Celsius.exe
```

## Gerar Instalador Windows

```powershell
installer\build.bat
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

O Celsius inclui trial local de 3 dias e ativacao por chave.

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

Verificar trials:

```powershell
python tools\generate_license.py trials
```

Arquivos como `keys/`, `licenses.json` e `*.pem` nao devem ser commitados.

## Checklist Antes de Distribuir

- `python -m ruff check .`
- `python -m pytest -q`
- Abrir `dist/Celsius/Celsius.exe` localmente.
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
