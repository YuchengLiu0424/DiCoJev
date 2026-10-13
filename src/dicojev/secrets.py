"""User-scoped secret persistence for the native application."""

from __future__ import annotations

import base64
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(value: bytes, *, decrypt: bool) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("Secure settings storage currently requires Windows DPAPI.")
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if decrypt:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
        )
    else:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), "DiCoJev", None, None, None, 0, ctypes.byref(target)
        )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


class SecretStore:
    """Small DPAPI-backed key store; ciphertext is decryptable only by this Windows user."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "credentials.json"

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def get(self, name: str) -> str | None:
        encoded = self._read().get(name)
        if not encoded:
            return None
        return _dpapi(base64.b64decode(encoded), decrypt=True).decode("utf-8")

    def set(self, name: str, value: str) -> None:
        payload = self._read()
        if value:
            encrypted = _dpapi(value.encode("utf-8"), decrypt=False)
            payload[name] = base64.b64encode(encrypted).decode("ascii")
        else:
            payload.pop(name, None)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def has(self, name: str) -> bool:
        return bool(self._read().get(name))
