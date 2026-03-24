"""
Post-processing decoders for BigWorld BLOB-based USER_TYPEs.

USER_TYPE aliases in alias.xml wrap BLOB with a custom converter
(implementedBy). On the wire they're just length-prefixed byte buffers.
This module provides decode functions that mirror the Python-side converters.

Usage:
    raw = schema.parse(data)  # returns bytes for BLOB fields
    decoded = decode_blob("ZIPPED_BLOB", raw)
"""

from __future__ import annotations

import logging
import pickle
import zlib
from typing import Any

log = logging.getLogger(__name__)

# Alias names that use each decoder
_ZIPPED_ALIASES = frozenset({"ZIPPED_BLOB", "CACHED_ZIPPED_BLOB"})
_MSGPACK_ALIASES = frozenset({"MSGPACK_BLOB"})
_PICKLE_ALIASES = frozenset({"PYTHON", "PICKLED_BLOB"})


def decode_blob(alias_name: str, data: bytes) -> Any:
    """Decode a BLOB value based on its alias name.

    Returns the decoded object, or the raw bytes if decoding fails.
    """
    if alias_name in _ZIPPED_ALIASES:
        return decode_zipped(data)
    if alias_name in _MSGPACK_ALIASES:
        return decode_msgpack(data)
    if alias_name in _PICKLE_ALIASES:
        return decode_pickle(data)
    return data


def decode_zipped(data: bytes) -> Any:
    """Decode a ZIPPED_BLOB: zlib-compressed pickled Python object."""
    if not data:
        return data
    try:
        decompressed = zlib.decompress(data)
        return pickle.loads(decompressed)  # noqa: S301
    except (zlib.error, pickle.UnpicklingError, Exception):
        log.debug("Failed to decode ZIPPED_BLOB (%d bytes)", len(data), exc_info=True)
        return data


def decode_msgpack(data: bytes) -> Any:
    """Decode a MSGPACK_BLOB: MessagePack-encoded data."""
    if not data:
        return data
    try:
        import msgpack
        return msgpack.unpackb(data, raw=False)
    except ImportError:
        log.debug("msgpack not installed — returning raw bytes")
        return data
    except Exception:
        log.debug("Failed to decode MSGPACK_BLOB (%d bytes)", len(data), exc_info=True)
        return data


def decode_pickle(data: bytes) -> Any:
    """Decode a PYTHON/PICKLED_BLOB: pickled Python object."""
    if not data:
        return data
    try:
        return pickle.loads(data)  # noqa: S301
    except Exception:
        log.debug("Failed to decode PICKLED_BLOB (%d bytes)", len(data), exc_info=True)
        return data
