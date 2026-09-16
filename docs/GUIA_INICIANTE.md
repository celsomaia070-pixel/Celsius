# Guia do Iniciante

Este guia e para quem esta comecando em programacao e quer rodar o Celsius no
Windows.

## Abrir a interface web (projeto ja instalado)

Na pasta `E:\PythonProjectCELSIUS`, execute `abrir_web.bat` com dois cliques,
ou use no terminal do PyCharm/PowerShell:

```powershell
cd E:\PythonProjectCELSIUS
.\.venv\Scripts\python.exe -m core.web_api --host 127.0.0.1 --port 8790 --http
```

Deixe o terminal aberto. No navegador, abra <http://127.0.0.1:8790/app>.
O endereco e digitado na barra do navegador, nao como comando Python.
Use HTTP nesse acesso ao proprio PC. `/api/docs` e a documentacao tecnica;
a interface de trabalho fica em `/app`.

No primeiro acesso, crie a conta principal. Ela sera administradora.
Novas contas sao cadastradas por esse administrador.
Para encerrar o servidor, pressione `Ctrl+C` no terminal.

Se a porta 8790 ja estiver ocupada pelo Celsius, abra o mesmo endereco.
Para uma segunda instancia, troque `--port 8790` por `--port 8791` e abra
<http://127.0.0.1:8791/app>. O acesso pelo celular exige servidor LAN com HTTPS;
o comando acima atende somente o computador local.

O arquivo `.env.example` mostra configuracoes opcionais. Em `.env`, os campos
agrupados usam dois sublinhados, como `CELSIUS_WEB__PORT=8790`.

## 1. Instalar o Python

1. Acesse https://www.python.org/downloads/
2. Baixe a versao mais recente do Python.
3. Abra o instalador.
4. Marque a opcao `Add python.exe to PATH`.
5. Clique em `Install Now`.

Para testar:

```powershell
python --version
```

## 2. Abrir o PowerShell

1. Pressione `Windows + R`.
2. Digite `powershell`.
3. Pressione Enter.

## 3. Entrar na Pasta do Projeto

No seu caso:

```powershell
cd E:\PythonProjectCELSIUS
```

## 4. Criar o Ambiente Virtual

O ambiente virtual e uma pasta isolada com as bibliotecas do projeto.

```powershell
python -m venv .venv
```

## 5. Ativar o Ambiente Virtual

```powershell
.\.venv\Scripts\Activate.ps1
```

Quando funcionar, o terminal vai mostrar algo parecido com:

```text
(.venv) PS E:\PythonProjectCELSIUS>
```

Se aparecer erro de permissao:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

## 6. Instalar Dependencias

Use `python -m pip`, porque funciona mesmo quando o comando `pip` sozinho nao e
reconhecido.

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.in
python -m playwright install chromium
```

Quer reduzir a instalacao inicial? Instale o pacote so com o nucleo e adicione
extras conforme precisar:

```powershell
python -m pip install -e .
python -m pip install -e ".[all]"        # reativa PDF/OCR, voz, web e Docker
python -m pip install -e ".[documents]"  # apenas processamento de documentos
python -m pip install -e ".[voice]"      # apenas transcricao e TTS
```

O guia abaixo assume `requirements.txt` (conjunto completo), que e o
recomendado para uso diario.

## 7. Rodar o Projeto

```powershell
python main.py
```

## 8. Testar se Esta Tudo Certo

```powershell
python -m ruff check .
python -m pytest -q
```

Resultado esperado:

```text
All checks passed!
<todos os testes executados sem falhas>
```

## 9. Comandos Uteis

| Objetivo | Comando |
|---|---|
| Ativar venv | `.\.venv\Scripts\Activate.ps1` |
| Instalar dependencia | `python -m pip install nome-do-pacote` |
| Atualizar pip | `python -m pip install --upgrade pip` |
| Rodar app | `python main.py` |
| Rodar testes | `python -m pytest -q` |
| Rodar lint | `python -m ruff check .` |
| Sair da venv | `deactivate` |

## 10. Gerar Instalador

Instale antes o Inno Setup em https://jrsoftware.org/isdl.php.

Depois rode:

```powershell
installer\build.bat
```

O instalador final fica em:

```text
dist\Celsius-Setup-v1.0.0.exe
```

## Problemas Frequentes

### `pip` nao e reconhecido

Use:

```powershell
python -m pip install -r requirements.txt
```

### `python` nao e reconhecido

Reinstale o Python e marque `Add python.exe to PATH`.

### PowerShell bloqueou a venv

Use:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Teste falhou

Copie a parte vermelha do erro e veja qual arquivo falhou. Rode novamente:

```powershell
python -m pytest -q
```
