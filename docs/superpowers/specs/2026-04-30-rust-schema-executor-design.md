# Rust Schema Executor — Design

**Branch**: `decode-rs`
**Date**: 2026-04-30
**Status**: Design approved, ready for implementation plan

## Goal

Replace Construct's per-field Python schema dispatch with a recursive Rust
executor inside `wows_native`. Construct's framework overhead (~1.7 s of pure
CPU on a 2.5 MB fixture replay, the largest single bucket in `parse_replay()`)
goes away. Pickle deserialization stays in Python — that's not the fight.

Target end-to-end speedup: **~1.5×** on the existing 4.0 s baseline. The 7-20×
microbench gain we already measured at the leaf level surfaces once Construct
isn't wrapping every primitive call.

## Architecture decisions

These are locked, captured here as the contract for the implementation plan.

### Path C — full recursive executor

Rust owns the entire schema walk: every primitive, `FIXED_DICT`, `ARRAY`,
`ARRAY<FIXED_DICT>`, `AllowNone` wrapper, alias chains. Python only sees the
final decoded tree plus marker dicts for things Python has to finish (pickle,
zlib, custom converters).

### USER_TYPE / pickle handling — markers

When Rust hits a `USER_TYPE` with `implementedBy`, or a `BLOB`/`PYTHON` field
that needs auto-pickle sniffing, it decodes the inner length-prefixed bytes and
returns a sentinel:

```python
{"__alias__": "ZIPPED_BLOB", "__bytes__": b"..."}        # implementedBy
{"__autopickle__": True, "__bytes__": b"..."}            # BLOB/PYTHON
```

Python does **one** post-walk over the result tree, converts every marker via
the existing `decode_blob` / `decode_zipped` / `decode_pickle` helpers in
`gamedata/blob_decoders.py`. One FFI hop per packet, regardless of how many
USER_TYPE fields are nested inside.

The same post-walk wraps every plain dict in `cs.Container` so downstream
`.field_name` access (e.g. `pos.x`, `state.health`) keeps working.

### Schema flow — Python descriptor → Rust handle

Python builds a JSON-like dict descriptor at startup, hands it to
`wows_native.compile_schema(descriptor)`, gets back an opaque `SchemaHandle`.
Decode calls take `(handle, payload_bytes)`.

Schema descriptors are **rebuilt per gamedata version** (multi-version replay
support is unchanged from today). One handle is cached per
`(version, schema_root)`.

A new `NativeDescriptorBuilder` lives alongside the existing `SchemaBuilder`.
As each Construct path is replaced with Rust, the corresponding helper in
`SchemaBuilder` is deleted in the same commit. Endgame: Construct disappears
from this module.

### Output objects — plain dicts, Python wraps in Container

Rust returns native Python `dict` and `list`. The same post-walk that converts
markers wraps every dict in `cs.Container` to preserve the existing
attribute-access contract. The wrap layer is a single function — replacing it
with a custom `__getattr__` dict subclass later (Path-C-of-original-design)
is a one-line swap.

### Error model — typed `DecodeError` → `PyErr`

Rust internally uses `Result<T, DecodeError>` with `?`-propagation everywhere.
`DecodeError` is a `thiserror`-derived enum:

```rust
#[derive(Debug, thiserror::Error)]
enum DecodeError {
    #[error("buffer underrun: need {need} bytes at offset {offset}")]
    BufferUnderrun { need: usize, offset: usize },
    #[error("unknown alias {0:?}")]
    UnknownAlias(String),
    #[error("schema mismatch at {path}: expected {expected}, got {got}")]
    SchemaMismatch { path: String, expected: String, got: String },
    #[error("invalid count prefix: {0}")]
    InvalidCount(u32),
    // … as we discover more
}

impl From<DecodeError> for PyErr {
    fn from(e: DecodeError) -> Self { PyValueError::new_err(e.to_string()) }
}
```

The `?` operator at the FFI boundary converts to `PyErr`. The existing decoder
catch sites (`_handle_method_call`, `_handle_property_update`,
`_try_parse_inline_state`) handle the exception as they do today: log at DEBUG
(now guarded with `isEnabledFor`), set `method_args=None` / fall through to
`RawEvent`. The CLAUDE.md "no silent drops" hard constraint is preserved.

### Scope — every SchemaBuilder output

All four call sites — method args, property values, inline ENTITY_CREATE state,
and the opt-in auto-detector trial parses — go through the Rust executor
uniformly. No mixed paths.

### Rollout — invasive on `decode-rs`

No runtime feature flag. Each Construct path is replaced with Rust in a
focused commit; the existing 1099-test suite is the contract. Tests must stay
green at every step.

The native test suite plus the 117 integration tests (which parse a real 2.5 MB
replay end-to-end) are sufficient correctness coverage — explicit parity
testing isn't needed. Construct helpers (`_RobustString`,
`_MethodBlobPrefixed`, etc.) get deleted as soon as their last consumer is
gone.

## Schema descriptor vocabulary

The descriptor is a tagged-union dict with these `kind` values:

**Fixed-width primitives** (already in `wows_native`):

```python
{"kind": "int8" | "int16" | "int32" | "int64"}
{"kind": "uint8" | "uint16" | "uint32" | "uint64"}
{"kind": "float32" | "float64"}
{"kind": "bool"}
{"kind": "vector2" | "vector3"}
{"kind": "mailbox"}                                       # 16-byte raw
```

**Variable-length primitives**:

```python
{"kind": "string", "mode": "method" | "u32"}
{"kind": "unicode_string", "mode": "method" | "u32"}
{"kind": "blob", "mode": "method" | "u32"}                # raw bytes
{"kind": "python", "mode": "method" | "u32"}              # raw bytes
```

**Composites**:

```python
{
    "kind": "fixed_dict",
    "fields": [
        {"name": "pos", "schema": {"kind": "vector3"}},
        {"name": "speed", "schema": {"kind": "float32"}},
    ],
}

{
    "kind": "array",
    "count_prefix": "uint8",                               # always uint8
    "element": <descriptor>,
}

{"kind": "tuple", "elements": [<descriptor>, ...]}        # 0 in current alias.xml
```

**Wrappers**:

```python
{"kind": "allow_none", "inner": <descriptor>}             # u8 flag prefix

{
    "kind": "user_type",                                   # implementedBy alias
    "alias": "ZIPPED_BLOB",
    "blob_mode": "method" | "u32",
}

{"kind": "auto_pickle_blob", "blob_mode": "method"}       # BLOB/PYTHON in method args
```

This vocabulary covers every node kind the existing `SchemaBuilder` produces.
Anything outside it is a bug in the descriptor builder.

## API surface

```python
# Build phase (once per gamedata version)
descriptor = native_descriptor_builder.build_property(entity_type, prop_id)
handle = wows_native.compile_schema(descriptor)

# Decode phase (many calls per replay)
result = wows_native.decode(handle, payload_bytes)        # raises DecodeError on failure

# Python post-process (single sweep over result tree)
result = post_process(result)        # marker conversion + Container wrap
```

`SchemaBuilder.build_method_schema(...)` etc. return small Python objects with
a compatible `.parse(bytes)` method that internally calls
`wows_native.decode(self._handle, bytes)` then `post_process(...)`. The call
sites in `decoder.py` don't change.

## Implementation phases

In order, each its own commit, tests green at every step:

1. **Skeleton**: `compile_schema` + `decode` accept the simplest descriptor
   (single primitive). Wire one method's schema through, prove the FFI shape.
2. **Fixed primitives + vector + mailbox**: extend `compile_schema` to handle
   all 14 fixed-width descriptors. No FIXED_DICT yet — the existing primitive
   call sites flip to native.
3. **Variable primitives**: `string` / `unicode_string` / `blob` / `python`
   with both modes. The `mode` parameter goes through the descriptor.
4. **FIXED_DICT (primitive-only fields)**: 24 candidate aliases per the audit.
   First composite. Tests prove single-record decode.
5. **`AllowNone` wrapper**: u8 flag → None or recursive decode.
6. **ARRAY (any element type)**: prefixed array, including `ARRAY<FIXED_DICT>`
   — the bulk hot path we've been chasing.
7. **`USER_TYPE` markers + post-walk**: implementedBy aliases produce
   `__alias__` markers. Python post-walk converts via `decode_blob`.
8. **`auto_pickle_blob` markers**: BLOB/PYTHON in method args. Python post-walk
   sniffs first byte.
9. **Recursive FIXED_DICT** (nested composites): full schema graph including
   FIXED_DICT containing FIXED_DICT, ARRAY of FIXED_DICT containing
   USER_TYPE, etc.
10. **`TUPLE`**: trivial once the rest is done. Zero in current alias.xml but
    the descriptor needs it for forward-compat.
11. **Cleanup**: delete now-dead Construct helpers (`_RobustString`,
    `_MethodBlobPrefixed`, `_NativeFixed`, `_NativeVarLen`,
    `_NativeArrayPrimitive`, `_AllowNone`, `_DecodedBlob`,
    `_AutoPickleBlob`). `SchemaBuilder` becomes a thin wrapper that produces
    descriptors. Update CLAUDE.md auto-detector paragraph.

Each phase ends green-tested. End-to-end benchmark recorded after phases 6
(arrays should now help on real replays) and 11 (final number).

## Out of scope

- Pickle in Rust (Python pickle protocol 2 with `find_class` mapping is
  genuinely Python's domain).
- Zlib in Rust (called from the marker post-walk, not on the Rust hot path).
- State tracker / event stream / packet routing — these are Python and stay
  Python; they're separate buckets in the profile.
- Migrating downstream `.field` access to `["field"]` — would buy us the right
  to drop the Container wrap, but the post-walk is not on the bottleneck path
  per the existing benchmark.
- Multi-version schema caching beyond what `_load_gamedata_cached` already does.

## Risks

- **Schema graph corner cases**: alias chains (e.g. `ENTITY_ID` →
  `INT32`), implementedBy on FIXED_DICT/ARRAY/TUPLE, nested AllowNone. The
  descriptor builder must handle every shape `SchemaBuilder` does today. Caught
  by tests since SchemaBuilder is well-exercised.
- **Container wrap cost**: on huge result trees the post-walk could itself
  become a bottleneck. Mitigation: profile after phase 9; if it's >5% drop the
  wrap and migrate `.field` consumers (pre-planned escape hatch).
- **Marker-walk pickle overhead unchanged**: pickle is the largest non-Rust
  cost remaining. If after phase 11 pickle dominates the budget more than
  expected, that's a separate project.

## Success criteria

- All 1099 existing tests green at each phase.
- End-to-end median parse time on the 2.5 MB fixture: **≤ 2.7 s** (from 4.0 s
  current). 35% improvement is the lower bound; closer to 50% if our profile
  estimates hold.
- No new failure modes vs Construct (parity is implicit via the existing
  test suite).
- Construct dependency stays for tests / fallback only — production parsing
  has zero `cs.parse(...)` calls on the hot path.
