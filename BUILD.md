# Building Celsius

Guia de build do Celsius com LLM local via `llama-cpp-python`.

## Pré-requisitos

1. **Python 3.10+** com dependências instaladas:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **Modelo GGUF** (quantizado, ~4-8 GB para modelos 7B):
   - Recomendado: `qwen2.5-vl-7b-q4_k_m.gguf` (suporte a visão)
   - Download: https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct-GGUF
   - Os modelos são baixados automaticamente pelo app no primeiro uso

3. **Para visão (imagens)**: arquivo `mmproj-*.gguf` na pasta `resources/`

## Estrutura de Diretórios

```
celsius/
├── resources/
│   ├── *.dll                    # Dependências do llama-cpp-python
│   ├── qwen2.5-vl-7b-q4_k_m.gguf
│   └── mmproj-Qwen2.5-VL-7B-*.gguf (opcional)
├── main.py
├── celsius.spec
└── ...
```

## Building

### Windows
```bash
pyinstaller celsius.spec --clean
```
Saída: `dist/Celsius.exe`

### macOS
```bash
pyinstaller celsius.spec --clean
```
Saída: `dist/Celsius.app`

### Linux
```bash
pyinstaller celsius.spec --clean
```
Saída: `dist/Celsius`

## Arquitetura

O app usa `llama-cpp-python` (bindings Python diretos) com aceleração GPU via Vulkan.

1. **App inicia** → `main.py` chama `get_llama()` para carregar o modelo
2. **Modelo carregado** → Inference direta via `Llama.chat_completion()`
3. **Fim do app** → `atexit` descarrega o modelo

## Configuração

O modelo padrão é configurado em `core/config.py`:
```python
default_llm_model: str = "qwen2.5vl:7b"  # Mapeia para qwen2.5-vl-7b-q4_k_m.gguf
```

## Troubleshooting

| Problema | Solução |
|----------|---------|
| "Modelo não encontrado" | Verifique se o `.gguf` está em `resources/` |
| GPU não detectada | Verifique se Vulkan está instalado; tente `n_gpu_layers=0` para CPU |
| Sem memória | Use quantização menor (Q3_K_M) ou modelo menor (3B) |
| Visão não funciona | Use modelo com visão (Qwen2.5-VL) e o `mmproj` correto |

## Recomendações de Modelos

| Modelo | Tamanho (Q4_K_M) | Visão | Velocidade | Qualidade |
|--------|-------------------|-------|------------|-----------|
| Qwen2.5-VL-7B | ~4.5 GB | Sim | Rápido | Excelente |
| Qwen2.5-VL-3B | ~2 GB | Sim | Muito rápido | Bom |
| Gemma 3 4B | ~2.5 GB | Sim | Muito rápido | Bom |
| Llama-3.2-3B-Instruct | ~2 GB | Não | Muito rápido | Bom |
| Qwen3.5-35B MoE | ~20 GB | Não | Lento | Excelente |
