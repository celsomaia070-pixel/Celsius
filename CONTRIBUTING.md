# Contribuicao

Obrigado por contribuir com o Celsius.

## Fluxo Recomendado

1. Crie uma branch curta e descritiva.
2. Rode os testes antes de abrir PR.
3. Atualize documentacao quando mudar comportamento.
4. Explique risco, validacao e impacto no PR.

## Ambiente Local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.in
```

## Checks Obrigatorios

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

## Boas Praticas

- Mantenha mudancas pequenas e focadas.
- Nao commite modelos, caches, logs, conversas, chaves ou licencas.
- Prefira configuracao em `core/settings.py` e `.env`.
- Inclua testes para comportamento novo ou correcao de bug.
- Preserve compatibilidade com Windows.

## Segurança

Nao abra issue publica com segredo, chave privada ou vulnerabilidade exploravel.
Use as instrucoes de `SECURITY.md`.
