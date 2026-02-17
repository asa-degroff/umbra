"""
Ollama Model Manager

Ensures only one model type (LLM or embedding) is loaded in VRAM at a time.
On a 12GB GPU, having both loaded causes thrashing and makes generation unusable.

Usage:
    from semantic_analysis.ollama_manager import ollama_manager
    
    ollama_manager.ensure_model("embed")  # before embedding calls
    ollama_manager.ensure_model("llm")    # before LLM generation calls
"""

import logging
import threading
import requests

logger = logging.getLogger(__name__)

EMBED_MODEL = None
LLM_MODEL = None
OLLAMA_URL = "http://localhost:11434"


def _get_embed_model() -> str:
    global EMBED_MODEL
    if EMBED_MODEL is None:
        from semantic_analysis.embeddings import DEFAULT_MODEL
        EMBED_MODEL = DEFAULT_MODEL
    return EMBED_MODEL


def _get_llm_model() -> str:
    global LLM_MODEL
    if LLM_MODEL is None:
        from semantic_analysis.analyzer import DEFAULT_LLM_MODEL
        LLM_MODEL = DEFAULT_LLM_MODEL
    return LLM_MODEL


class OllamaModelManager:
    """Serialize access to Ollama so only one model type is loaded at a time."""

    def __init__(self):
        self._active_type: str | None = None
        self._lock = threading.Lock()
        self._swap_count = 0

    def ensure_model(self, model_type: str) -> None:
        """Ensure the requested model type is the only one loaded."""
        if model_type not in ("llm", "embed"):
            raise ValueError(f"Unknown model_type: {model_type}")

        with self._lock:
            if self._active_type == model_type:
                return

            if self._active_type is not None:
                other_model = self._model_name(self._active_type)
                self._unload(other_model)
                self._swap_count += 1
                logger.info(
                    f"Model swap #{self._swap_count}: "
                    f"{self._active_type} -> {model_type} "
                    f"(unloaded {other_model})"
                )

            self._active_type = model_type

    def _model_name(self, model_type: str) -> str:
        if model_type == "embed":
            return _get_embed_model()
        elif model_type == "llm":
            return _get_llm_model()
        raise ValueError(f"Unknown model_type: {model_type}")

    def _unload(self, model_name: str) -> None:
        """Unload a model from VRAM via keep_alive: 0."""
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=30,
            )
            if resp.status_code == 200:
                logger.debug(f"Unloaded {model_name}")
            else:
                logger.warning(f"Unload {model_name}: status {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Unload {model_name} failed: {e}")

    @property
    def active_type(self) -> str | None:
        return self._active_type

    @property
    def swap_count(self) -> int:
        return self._swap_count


ollama_manager = OllamaModelManager()
