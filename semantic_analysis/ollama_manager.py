"""
Ollama Model Manager

Ensures only one model type (LLM or embedding) is loaded in VRAM at a time.
On a 12GB GPU, having both loaded causes thrashing and makes generation unusable.

Also handles waiting for external Ollama users (e.g., vision model bots) to finish
before loading our own models.

Usage:
    from semantic_analysis.ollama_manager import ollama_manager
    
    ollama_manager.ensure_model("embed")  # before embedding calls
    ollama_manager.ensure_model("llm")    # before LLM generation calls
"""

import logging
import threading
import time
import requests

logger = logging.getLogger(__name__)

EMBED_MODEL = None
LLM_MODEL = None
OLLAMA_URL = "http://localhost:11434"

# Models that belong to Umbra — anything else loaded is an external user
KNOWN_MODELS = set()


def _get_embed_model() -> str:
    global EMBED_MODEL
    if EMBED_MODEL is None:
        from semantic_analysis.embeddings import DEFAULT_MODEL
        EMBED_MODEL = DEFAULT_MODEL
    KNOWN_MODELS.add(EMBED_MODEL)
    return EMBED_MODEL


def _get_llm_model() -> str:
    global LLM_MODEL
    if LLM_MODEL is None:
        from semantic_analysis.analyzer import DEFAULT_LLM_MODEL
        LLM_MODEL = DEFAULT_LLM_MODEL
    KNOWN_MODELS.add(LLM_MODEL)
    return LLM_MODEL


def _get_loaded_models() -> list[dict]:
    """Query Ollama /api/ps for currently loaded models."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/ps", timeout=10)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except requests.RequestException:
        return []


def _has_foreign_models(loaded: list[dict]) -> list[str]:
    """Return names of models loaded that don't belong to Umbra."""
    # Lazily populate known models
    _get_embed_model()
    _get_llm_model()

    foreign = []
    for m in loaded:
        name = m.get("name", "")
        if name and name not in KNOWN_MODELS:
            foreign.append(name)
    return foreign


class OllamaModelManager:
    """Serialize access to Ollama so only one model type is loaded at a time.
    
    Also waits for external programs (e.g., vision bots) to finish using Ollama
    before proceeding with model swaps.
    """

    # How long to wait for external models to finish
    FOREIGN_WAIT_TIMEOUT = 120  # 2 minutes max
    FOREIGN_POLL_INTERVAL = 5   # check every 5 seconds

    def __init__(self):
        self._active_type: str | None = None
        self._lock = threading.Lock()
        self._swap_count = 0

    def ensure_model(self, model_type: str) -> None:
        """Ensure the requested model type is the only one loaded.
        
        If a foreign model (not belonging to Umbra) is currently loaded,
        waits for it to be unloaded before proceeding.
        """
        if model_type not in ("llm", "embed"):
            raise ValueError(f"Unknown model_type: {model_type}")

        with self._lock:
            # Wait for any foreign models to finish
            self._wait_for_foreign_models()

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

    def wait_for_ollama_ready(self, timeout: int = 30) -> bool:
        """Wait for Ollama to be reachable. Returns True if ready."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = requests.get(f"{OLLAMA_URL}/api/version", timeout=5)
                if resp.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            time.sleep(2)
        return False

    def _wait_for_foreign_models(self) -> None:
        """Wait for any non-Umbra models to finish and unload."""
        deadline = time.time() + self.FOREIGN_WAIT_TIMEOUT
        waited = False

        while time.time() < deadline:
            loaded = _get_loaded_models()
            foreign = _has_foreign_models(loaded)

            if not foreign:
                if waited:
                    logger.info("Foreign models finished, proceeding")
                return

            if not waited:
                logger.info(
                    f"Waiting for foreign model(s) to finish: {', '.join(foreign)}"
                )
                waited = True

            time.sleep(self.FOREIGN_POLL_INTERVAL)

        # Timeout — log warning but proceed anyway
        loaded = _get_loaded_models()
        foreign = _has_foreign_models(loaded)
        if foreign:
            logger.warning(
                f"Timed out waiting for foreign models ({', '.join(foreign)}) "
                f"after {self.FOREIGN_WAIT_TIMEOUT}s, proceeding anyway"
            )

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

    def release(self) -> None:
        """Immediately unload whatever model is currently active.
        
        Call this when Umbra is done with Ollama to free VRAM for other programs.
        """
        with self._lock:
            if self._active_type is not None:
                model = self._model_name(self._active_type)
                self._unload(model)
                logger.info(f"Released {self._active_type} model ({model}) — VRAM freed")
                self._active_type = None

    @property
    def active_type(self) -> str | None:
        return self._active_type

    @property
    def swap_count(self) -> int:
        return self._swap_count


ollama_manager = OllamaModelManager()
