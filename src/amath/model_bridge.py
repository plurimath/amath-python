"""Optional thin consumer of the canonical Rust stage's model JSON ABI.

This module does not construct Python LML classes. The native stage owns all
model construction and semantic validation; Python returns its portable data.
"""
from __future__ import annotations
import ctypes
from functools import lru_cache
import json
import os
from pathlib import Path
from .native_library import packaged_library_path

class ModelRuntimeUnavailable(RuntimeError):
    """The separately installed canonical stage ABI could not be loaded."""

class ModelParseError(ValueError):
    """The canonical stage rejected the input; ``error`` retains its payload.

    For ``dialect="pma"`` refusals, ``refusal_category`` is one of the 14 pma
    taxonomy categories and ``byte_offset``/``char_offset`` locate the position
    in the caller input (pma has no preprocessing)."""
    def __init__(self, error):
        self.error = error
        self.refusal_category = error.get("refusal_category")
        self.byte_offset = error.get("byte_offset")
        self.char_offset = error.get("char_offset")
        super().__init__(str(error.get("message", "canonical model parse rejected")))

class ModelResourceError(RuntimeError):
    """A typed native parser budget abort, distinct from syntax rejection."""
    def __init__(self, error):
        self.error = error
        self.category = error["category"]
        self.depth = error.get("depth")
        self.max_depth = error.get("max_depth")
        super().__init__(str(error.get("message", self.category)))

@lru_cache(maxsize=4)
def _load(path):
    target = Path(path)
    if not target.is_absolute():
        raise ModelRuntimeUnavailable("AMATH_MODEL_CDYLIB must be an absolute library path")
    try:
        library = ctypes.CDLL(str(target))
        library.amath_abi_version.argtypes = []
        library.amath_abi_version.restype = ctypes.c_uint32
        library.amath_parse_model_json_v1.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
        library.amath_parse_model_json_v1.restype = ctypes.c_void_p
        dialect_entry = getattr(library, "amath_parse_model_dialect_json_v1", None)
        if dialect_entry is not None:
            dialect_entry.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
            dialect_entry.restype = ctypes.c_void_p
        library.amath_free_json_v1.argtypes = [ctypes.c_void_p]
        library.amath_free_json_v1.restype = None
        if library.amath_abi_version() != 1:
            raise ModelRuntimeUnavailable("unsupported amath model ABI version")
    except (OSError, AttributeError) as error:
        raise ModelRuntimeUnavailable(f"cannot load canonical amath model ABI: {error}") from error
    return library

def _library_path():
    path = os.environ.get("AMATH_MODEL_CDYLIB") or packaged_library_path()
    if not path:
        raise ModelRuntimeUnavailable("native library missing; install a platform wheel or set AMATH_MODEL_CDYLIB")
    return path

DIALECTS = ("legacy", "pma")

def parse_model_json(source: str, *, decimal: str = ".", dialect: str = "legacy") -> dict:
    """Return canonical model JSON as a Python dict through ABI v1.

    ``dialect="legacy"`` (the default, dialect L) is unchanged and returns a
    ``Document``. ``dialect="pma"`` (dialect P) returns a ``PmaDocument``; it is
    only ever selected explicitly, has no decimal option ("." only) and never
    falls back to dialect L.

    The platform wheel supplies the canonical Rust stage cdylib. An absolute
    ``AMATH_MODEL_CDYLIB`` path remains an optional override. This is
    JSON model data, not Python classes.
    """
    from . import _validate
    if dialect not in DIALECTS:
        raise ValueError(f"unknown dialect {dialect!r}; expected 'legacy' or 'pma'")
    if dialect == "pma":
        if not isinstance(source, str):
            raise TypeError("input must be a str")
        if "\x00" in source:
            raise ValueError("input must not contain NUL (C ABI string boundary)")
        if decimal != ".":
            raise ValueError("dialect 'pma' has no decimal option in version 1; numbers use the full stop")
    else:
        _validate(source, decimal)
    library = _load(_library_path())
    encoded, marker = source.encode("utf-8"), decimal.encode("utf-8")
    if dialect == "legacy":
        pointer = library.amath_parse_model_json_v1(encoded, len(encoded), marker, len(marker))
    else:
        entry = getattr(library, "amath_parse_model_dialect_json_v1", None)
        if entry is None:
            raise ModelRuntimeUnavailable("installed native library has no pma dialect entrypoint")
        name = dialect.encode("utf-8")
        pointer = entry(encoded, len(encoded), marker, len(marker), name, len(name))
    if not pointer:
        raise ModelRuntimeUnavailable("canonical amath ABI returned a null result")
    try:
        try:
            result = json.loads(ctypes.string_at(pointer).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelRuntimeUnavailable("invalid canonical model ABI JSON encoding") from error
    finally:
        library.amath_free_json_v1(ctypes.c_void_p(pointer))
    if not isinstance(result, dict) or result.get("abi_version") != 1:
        raise ModelRuntimeUnavailable("invalid canonical amath ABI result envelope")
    if result.get("ok") is False and isinstance(result.get("error"), dict):
        if result["error"].get("category") in ("recursion_limit", "call_depth_limit"):
            raise ModelResourceError(result["error"])
        raise ModelParseError(result["error"])
    if result.get("ok") is not True or not isinstance(result.get("model"), dict):
        raise ModelRuntimeUnavailable("invalid canonical amath model payload")
    return result["model"]
