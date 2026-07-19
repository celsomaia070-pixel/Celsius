# Building Celsius with Embedded llama.cpp

This guide explains how to build the Celsius desktop app with an embedded local LLM using `llama-server` (llama.cpp).

## Prerequisites

1. **Python 3.10+** with dependencies installed:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **llama.cpp server binary** for your platform:
   - Download from: https://github.com/ggml-org/llama.cpp/releases
   - Or build from source: `cmake -B build && cmake --build build --target llama-server`
   - Rename to match your platform:
     - Windows: `llama-server.exe`
     - macOS: `llama-server-macos`
     - Linux: `llama-server-linux`

3. **GGUF Model file** (quantized, ~4-8GB for 7B models):
   - Recommended: `qwen2.5-vl-7b-q4_k_m.gguf` (supports vision)
   - Download from: https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct-GGUF
   - Or convert from Ollama: `ollama export qwen2.5vl:7b --format gguf`

## Directory Structure

Place files in `resources/` folder:

```
celsius/
├── resources/
│   ├── llama-server.exe          # Windows (or llama-server-macos / llama-server-linux)
│   └── qwen2.5-vl-7b-q4_k_m.gguf # Your GGUF model
├── main.py
├── celsius.spec
└── ...
```

## Building

### Windows
```bash
pyinstaller celsius.spec --clean
```
Output: `dist/Celsius.exe`

### macOS
```bash
pyinstaller celsius.spec --clean
```
Output: `dist/Celsius.app`

### Linux
```bash
pyinstaller celsius.spec --clean
```
Output: `dist/Celsius`

## Configuration

The app expects these files at runtime (bundled via PyInstaller):

| File | Path (bundled) | Description |
|------|----------------|-------------|
| llama-server binary | `resources/llama-server(.exe)` | llama.cpp server |
| Model | `resources/qwen2.5-vl-7b-q4_k_m.gguf` | GGUF model file |

Model name is configured in `core/config.py`:
```python
default_llm_model: str = "qwen2.5vl:7b"  # Maps to qwen2.5-vl-7b-q4_k_m.gguf
```

## How It Works

1. **App starts** → `main.py` calls `start_llama_server()`
2. **llama-server launches** → Loads GGUF model on `http://127.0.0.1:8080/v1`
3. **OpenAI client connects** → Uses `http://127.0.0.1:8080/v1` with dummy API key
4. **App exits** → `stop_llama_server()` terminates the process

## Future SaaS Migration

When migrating to web SaaS, only change the client config in `core/llama_server.py`:

```python
# Local (current)
def get_llama_client_config():
    return {"base_url": "http://127.0.0.1:8080/v1", "api_key": "dummy"}

# SaaS (future)
def get_llama_client_config():
    return {"base_url": "https://api.celsius.ai/v1", "api_key": os.getenv("CELSIUS_API_KEY")}
```

No other code changes needed - the OpenAI-compatible API is identical.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "llama-server binary not found" | Check `resources/` folder has correct binary for platform |
| "Model file not found" | Ensure `.gguf` file is in `resources/` and name matches config |
| Server fails to start | Check port 8080 is free; try `--port 8081` in `llama_server.py` |
| Out of memory | Use smaller quantization (Q3_K_M, Q2_K) or smaller model (1B-3B) |
| Vision not working | Ensure model supports vision (Qwen2.5-VL, LLaVA, etc.) |

## Model Recommendations

| Model | Size (Q4_K_M) | Vision | Speed | Quality |
|-------|---------------|--------|-------|---------|
| Qwen2.5-VL-7B | ~4.5 GB | ✅ | Fast | Excellent |
| Qwen2.5-VL-3B | ~2 GB | ✅ | Very Fast | Good |
| Llama-3.2-3B-Instruct | ~2 GB | ❌ | Very Fast | Good |
| Phi-3.5-mini | ~2 GB | ❌ | Very Fast | Decent |
| Gemma-2-2B | ~1.5 GB | ❌ | Very Fast | Decent |