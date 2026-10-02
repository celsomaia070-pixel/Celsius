#!/usr/bin/env python
"""Dependency diagnostic and fix helper for sentence-transformers / huggingface-hub."""

import subprocess
import sys


def run(cmd: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    print("=== Dependency Diagnostic ===")
    code, out, err = run(
        [sys.executable, "-m", "pip", "show", "sentence-transformers", "huggingface-hub"]
    )
    print(out or err)

    print("\n=== Compatibility Matrix ===")
    print("sentence-transformers 3.4.x requires: huggingface-hub>=0.34.0,<1.0")
    print("Current: huggingface-hub 1.32.0 (INCOMPATIBLE)")
    print()
    print("Options:")
    print("1. Downgrade huggingface-hub to 0.34.0 <= x < 1.0")
    print("   pip install 'huggingface-hub>=0.34.0,<1.0'")
    print()
    print("2. Upgrade sentence-transformers to a version compatible with hf-hub 1.x")
    print("   pip install -U sentence-transformers")
    print("   (may require transformers upgrade too)")
    print()
    print("3. Use a compatible pair (recommended):")
    print("   pip install 'huggingface-hub==0.34.0' 'sentence-transformers==3.4.1'")
    print()

    # Test current encoder
    print("=== Encoder Test ===")
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("Qwen/Qwen3-Embedding-0.6B")
        emb = model.encode("teste de compatibilidade")
        print(f"SUCCESS: encoder works, dim={len(emb)}")
        return 0
    except Exception as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
