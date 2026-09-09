"""Run CLI tools without flashing a Windows console (avoids stealing game focus)."""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def run_hidden(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    kwargs.setdefault("check", False)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return subprocess.run(command, **kwargs)
