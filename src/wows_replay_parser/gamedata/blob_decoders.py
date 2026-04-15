"""
Post-processing decoders for BigWorld BLOB-based USER_TYPEs.

USER_TYPE aliases in alias.xml wrap BLOB with a custom converter
(implementedBy). On the wire they're just length-prefixed byte buffers.
This module provides decode functions that mirror the Python-side converters.

Usage:
    raw = schema.parse(data)  # returns bytes for BLOB fields
    decoded = decode_blob(alias, raw)
"""

from __future__ import annotations

import io
import logging
import pickle
import struct
import zlib
from typing import Any

from wows_replay_parser.gamedata.alias_registry import TypeAlias

log = logging.getLogger(__name__)

# Alias names that use each decoder
_ZIPPED_ALIASES = frozenset({"ZIPPED_BLOB", "CACHED_ZIPPED_BLOB"})
_MSGPACK_ALIASES = frozenset({"MSGPACK_BLOB"})
_PICKLE_ALIASES = frozenset({"PYTHON", "PICKLED_BLOB"})


class _AttrObject:
    """Reconstructed pickle class instance with unknown module."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.state: Any = None

    def __setstate__(self, state: Any) -> None:
        self.state = state
        if isinstance(state, dict):
            self.__dict__.update(state)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.__dict__}>"


class _PermissiveUnpickler(pickle.Unpickler):
    """Unpickler that reconstructs unknown classes as _AttrObject subclasses,
    preserving the original class name and all state data."""

    def __init__(self, fp: io.BytesIO) -> None:
        super().__init__(fp, encoding="latin-1")

    def find_class(self, module: str, name: str) -> type:
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError):
            return type(name, (_AttrObject,), {"_pickle_module": module, "_pickle_class": name})


def decode_blob(alias: TypeAlias, data: bytes) -> Any:
    """Decode a BLOB value based on its alias.

    Returns the decoded object, or the raw bytes if decoding fails
    or no decoder is available.  Never raises.
    """
    name = alias.name
    if name in _ZIPPED_ALIASES:
        return decode_zipped(data)
    if name in _MSGPACK_ALIASES:
        return decode_msgpack(data)
    if name in _PICKLE_ALIASES:
        return decode_pickle(data)

    decoder = _FIXED_STRUCT_DECODERS.get(name)
    if decoder is not None:
        try:
            return decoder(data)
        except Exception:
            log.debug("Failed to decode %s (%d bytes)", name, len(data) if data else 0, exc_info=True)
            return data

    # No known decoder — log at DEBUG if this alias has an implementedBy
    if alias.has_implemented_by:
        log.debug(
            "Unhandled implementedBy=%s alias=%s (%d bytes)",
            alias.implemented_by, name, len(data) if data else 0,
        )
    return data


def decode_zipped(data: bytes) -> Any:
    """Decode a ZIPPED_BLOB: zlib-compressed pickled Python object."""
    if not data:
        return data
    try:
        decompressed = zlib.decompress(data)
    except zlib.error:
        log.debug("Failed to decompress ZIPPED_BLOB (%d bytes)", len(data), exc_info=True)
        return data
    try:
        return pickle.loads(decompressed)  # noqa: S301
    except Exception:
        pass
    try:
        return _PermissiveUnpickler(io.BytesIO(decompressed)).load()
    except Exception:
        log.debug("Failed to unpickle ZIPPED_BLOB (%d bytes)", len(data), exc_info=True)
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
    # Optimistic: standard unpickler handles builtins, dicts, lists fine
    try:
        return pickle.loads(data)  # noqa: S301
    except Exception:
        pass
    # Fallback: class instances with unknown modules (common in WoWS BLOBs)
    try:
        return _PermissiveUnpickler(io.BytesIO(data)).load()
    except Exception:
        log.debug("Failed to decode pickle BLOB (%d bytes)", len(data), exc_info=True)
        return data


# ── Fixed-size implementedBy decoders ─────────────────────────────────


def decode_consumable_usage_params(data: bytes) -> Any:
    """CONSUMABLE_USAGE_PARAMS: 2 bytes — slot_id (u8) + consumable_id (u8)."""
    if len(data) < 2:
        return data
    slot_id, consumable_id = struct.unpack_from("<BB", data)
    return {"slot_id": slot_id, "consumable_id": consumable_id}


def decode_gun_directions(data: bytes) -> Any:
    """GUN_DIRECTIONS: u32 packed bitfield — 2 bits per gun barrel.

    Each 2-bit value encodes rotation direction for one turret.
    The exact semantics depend on the number of turrets on the ship.
    """
    if len(data) < 4:
        return data
    packed = struct.unpack_from("<I", data, 0)[0]
    return {"packed": packed}


def decode_flat_vector(data: bytes) -> Any:
    """FLAT_VECTOR: 8 bytes — 2x f32 (x, z horizontal plane)."""
    if len(data) < 8:
        return data
    x, z = struct.unpack_from("<ff", data)
    return {"x": x, "z": z}


def decode_nullable_vector3(data: bytes) -> Any:
    """NULLABLE_VECTOR3: 12 bytes — 3x f32 (x, y, z)."""
    if len(data) < 12:
        return data
    x, y, z = struct.unpack_from("<fff", data)
    return {"x": x, "y": y, "z": z}


# TODO: QUICK_COMMAND — 3 bytes (command_id u8 + u16) or
# 13 bytes (+ entity_id i64 + position 2xf32). Needs more samples.


def decode_gameparams(data: bytes) -> Any:
    """GAMEPARAMS: u32 GameParams entity ID (resolved against GameParams.data)."""
    if len(data) < 4:
        return data
    return struct.unpack_from("<I", data)[0]


def decode_ship_config(data: bytes) -> Any:
    """SHIP_CONFIG: binary ship loadout blob.

    Format (all u32 LE, count-prefixed arrays of GameParamIds):
      Header: version + ship_params_id + element_count
      Units: 14 fixed slots (hull, engine, fire_control, etc.)
      [v13.2+: extra u32]
      Modernization: upgrades (slot 1-6)
      Exteriors: signals, camos, flags
      SupplyState: u32
      ColorSchemes: (slot, scheme) pairs
      Abilities: consumable GameParamIds
      Ensigns: ensign items
      Ecoboosts: economic boosts
      NavalFlag: u32
      IsOwned: u32
      LastBoardedCrew: commander/captain GameParamId

    """
    if len(data) < 12:
        return data

    off = [0]

    def r32() -> int:
        v = struct.unpack_from("<I", data, off[0])[0]
        off[0] += 4
        return v

    def read_array() -> list[int]:
        count = r32()
        return [r32() for _ in range(count)]

    try:
        _version = r32()
        ship_params_id = r32()
        _element_count = r32()

        units = read_array()

        # v13.2+ added an extra u32 after unit slots.
        # All current replays (v13.2+) include this field.
        _v13_2_extra = r32()

        modernization = read_array()
        exteriors = read_array()

        _supply_state = r32()

        color_scheme_count = r32()
        color_schemes = [(r32(), r32()) for _ in range(color_scheme_count)]

        abilities = read_array()
        ensigns = read_array()
        ecoboosts = read_array()

        naval_flag = r32()
        _is_owned = r32()
        last_boarded_crew = r32()

        return {
            "ship_params_id": ship_params_id,
            "units": units,
            "hull": units[0] if units else 0,
            "modernization": modernization,
            "exteriors": exteriors,
            "abilities": abilities,
            "ensigns": ensigns,
            "ecoboosts": ecoboosts,
            "naval_flag": naval_flag,
            "last_boarded_crew": last_boarded_crew,
            "color_schemes": color_schemes,
        }
    except struct.error:
        log.debug("Failed to decode SHIP_CONFIG (%d bytes)", len(data), exc_info=True)
        return data


_FIXED_STRUCT_DECODERS: dict[str, Any] = {
    "CONSUMABLE_USAGE_PARAMS": decode_consumable_usage_params,
    "GUN_DIRECTIONS": decode_gun_directions,
    "FLAT_VECTOR": decode_flat_vector,
    "NULLABLE_VECTOR3": decode_nullable_vector3,
    "GAMEPARAMS": decode_gameparams,
    "SHIP_CONFIG": decode_ship_config,
}
