"""Select MLX or Stub architect backend."""
from __future__ import annotations

import os


def create_architect():
    backend = (os.environ.get("QWEN_ARCHITECT") or os.environ.get("ARCHITECT_BACKEND") or "auto").lower()
    if backend in {"stub", "cpu", "ci"}:
        from .stub import StubArchitect
        return StubArchitect()
    if backend in {"mlx", "qwen"}:
        from .architect import QwenArchitect
        return QwenArchitect()
    # auto: prefer stub when MLX unavailable
    try:
        import mlx  # noqa: F401
        from .architect import QwenArchitect
        return QwenArchitect()
    except Exception:
        from .stub import StubArchitect
        return StubArchitect()
