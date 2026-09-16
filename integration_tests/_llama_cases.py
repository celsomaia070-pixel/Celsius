"""Real manager and native imports; only the model constructor is faked by default."""

import atexit
import hashlib
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


def imports():
    import llama_cpp
    from llama_cpp import llama_cpp as backend

    import core.llama_cpp as production

    assert Path(llama_cpp.__file__).is_file()
    assert Path(production.__file__).name == "llama_cpp.py"
    assert production.Llama is llama_cpp.Llama
    assert isinstance(backend.llama_supports_gpu_offload(), bool)
    assert backend._lib._handle
    print(f"Native llama binding: {llama_cpp.__file__}; library: {backend._lib._name}")


class FakeNative:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.fail_stream = False
        self.closed = False

    def create_completion(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return self._chunks()
        return {"choices": [{"text": "native boundary"}]}

    create_chat_completion = create_completion

    def _chunks(self):
        try:
            yield {"choices": [{"text": "first"}]}
            if self.fail_stream:
                raise RuntimeError("synthetic native stream failure")
            yield {"choices": [{"text": "second"}]}
        finally:
            self.closed = True

    def n_ctx(self):
        return self.kwargs["n_ctx"]

    def n_vocab(self):
        return 32


@contextmanager
def manager_fixture():
    import core.config as config
    import core.llama_cpp as production
    from core.settings import get_settings

    settings = get_settings()
    data = b"GGUF synthetic fixture: never passed into native model loading"
    model = config.GGUFModel(
        id="native-smoke-fixture",
        name="Native smoke",
        category="fast",
        filename="native-smoke.gguf",
        hf_repo="unused",
        hf_file="unused",
        size_gb=0,
        quant="test",
        sha256=hashlib.sha256(data).hexdigest(),
    )
    path = settings.resources_dir / model.filename
    path.write_bytes(data)
    manager = production.LlamaManager()
    # The actual integrity checker, settings, locks, metrics and iterator remain active.
    with (
        patch.object(config, "GGUF_MODELS", [model]),
        patch.object(production, "Llama", FakeNative),
    ):
        try:
            yield manager, model, path
        finally:
            manager.stop()
            atexit.unregister(manager.stop)


def lifecycle():
    import core.llama_cpp as production

    attempts = []

    def constructor(**kwargs):
        attempts.append(kwargs)
        if kwargs["n_gpu_layers"]:
            raise RuntimeError("synthetic GPU initialization failure")
        return FakeNative(**kwargs)

    with manager_fixture() as (manager, model, _), patch.object(production, "Llama", constructor):
        assert not manager.is_healthy()
        assert manager.start(model.id, n_gpu_layers=1, n_ctx=128, use_mlock=False)
        assert [entry["n_gpu_layers"] for entry in attempts] == [1, 0]
        assert attempts[-1]["flash_attn"] is False
        assert attempts[-1]["offload_kqv"] is False
        native = manager._llm
        assert manager.start(model.id) and manager._llm is native
        assert len(attempts) == 2
        assert manager.is_healthy()
        assert manager.get_model_info()["n_ctx"] == 128
        reply = manager.create_chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            tools=[{"type": "function"}],
            tool_choice="auto",
            max_tokens=4,
        )
        assert reply["choices"]
        assert native.calls[-1]["tool_choice"] == "auto"
        assert native.calls[-1]["tools"] == [{"type": "function"}]
        manager.stop()
        manager.stop()
        assert not manager.is_healthy()
        assert manager.current_model_id is None and manager.get_model_info() == {}


def stream_close():
    with manager_fixture() as (manager, model, _):
        manager.start(model.id, n_gpu_layers=0)
        native = manager._llm
        stream = manager.create_completion(prompt="hello", stream=True)
        assert next(stream)["choices"]
        entered, stopped = threading.Event(), threading.Event()

        def stop():
            entered.set()
            manager.stop()
            stopped.set()

        thread = threading.Thread(target=stop, daemon=True)
        thread.start()
        try:
            assert entered.wait(2)
            assert not stopped.wait(0.1), "Native context unloaded while stream still owns it"
            assert manager.is_healthy()
        finally:
            stream.close()
            stream.close()
            thread.join(3)
        assert stopped.is_set() and not thread.is_alive()
        assert native.closed and not manager.is_healthy()


def stream_error():
    with manager_fixture() as (manager, model, _):
        manager.start(model.id, n_gpu_layers=0)
        manager._llm.fail_stream = True
        stream = manager.create_chat_completion(messages=[], stream=True)
        next(stream)
        try:
            next(stream)
        except RuntimeError as exc:
            assert "synthetic native" in str(exc)
        else:
            raise AssertionError("Native streaming error was swallowed")
        assert not manager._inference_lock.locked()
        manager._llm.fail_stream = False
        assert len(list(manager.create_completion(prompt="hello", stream=True))) == 2
        assert not manager._inference_lock.locked()


def missing_model():
    with manager_fixture() as (manager, model, path):
        path.unlink()
        try:
            manager.start(model.id)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Missing GGUF was accepted")
        assert not manager.is_healthy() and not manager._inference_lock.locked()


def integrity():
    from core.model_downloader import ModelIntegrityError

    with manager_fixture() as (manager, model, path):
        path.write_bytes(b"corrupted fixture")
        try:
            manager.start(model.id)
        except ModelIntegrityError:
            pass
        else:
            raise AssertionError("Corrupted GGUF reached the constructor")
        assert manager._llm is None and not manager._inference_lock.locked()


def generation():
    from core.llama_cpp import LlamaManager

    path = Path(sys.argv[2]).resolve(strict=True)
    assert path.is_file() and path.suffix.lower() == ".gguf"
    manager = LlamaManager()
    # User-supplied artifact has no catalog identity. Bypass only catalog resolution/checking.
    with (
        patch.object(manager, "_get_model_path", return_value=path),
        patch.object(manager, "_get_mmproj_path", return_value=None),
        patch("core.model_downloader.verify_registered_model", return_value=True),
    ):
        try:
            assert manager.start(
                "local-smoke", n_gpu_layers=0, n_ctx=512, n_batch=64, n_threads=2, use_mlock=False
            )
            result = manager.create_completion(
                prompt="The capital of France is", max_tokens=8, temperature=0, seed=42
            )
            assert result["choices"][0]["text"].strip(), result
            assert result["usage"]["completion_tokens"] > 0
            print(f"Local generation produced {result['usage']['completion_tokens']} tokens")
        finally:
            manager.stop()
            atexit.unregister(manager.stop)
