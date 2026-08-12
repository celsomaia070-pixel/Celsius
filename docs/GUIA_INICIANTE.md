# Guia do Iniciante

Este guia e para quem esta comecando em programacao e quer rodar o Celsius no
Windows.

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
