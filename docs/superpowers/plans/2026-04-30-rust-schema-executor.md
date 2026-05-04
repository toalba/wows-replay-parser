# Rust Schema Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Construct's per-field Python schema dispatch with a recursive Rust executor in `wows_native`, eliminating ~1.7 s of CPU time per replay parse and unlocking the 7-20× microbench gain we already measured at the leaf.

**Architecture:** Python `NativeDescriptorBuilder` walks the existing `AliasRegistry` / `EntityRegistry` to emit a tagged-dict schema descriptor. `wows_native.compile_schema(descriptor)` returns an opaque `SchemaHandle`. `wows_native.decode(handle, bytes)` returns plain Python `dict`/`list` plus marker dicts for USER_TYPE / auto-pickle blobs. A single Python post-walk converts markers via existing `decode_blob` / `decode_zipped` / `decode_pickle` helpers and wraps every dict in `cs.Container` to preserve `.field` access.

**Tech Stack:** Rust (pyo3 0.22, thiserror), Python 3.11+, maturin develop --profile release-native (RUSTFLAGS=`-C target-cpu=native`).

---

## File structure

**New (Rust, under `native/src/`):**
- `error.rs` — `DecodeError` enum + `From<DecodeError> for PyErr`
- `schema.rs` — `Schema` enum (compiled descriptor), `compile_schema` + tests
- `executor.rs` — recursive `decode_value(&Schema, &[u8], usize) -> Result<(Value, usize)>`
- `value.rs` — internal `Value` enum + `to_pyobject(py) -> PyObject`

**Modified (Rust):**
- `native/src/lib.rs` — register `compile_schema` + `decode`, expose `Schema` as `pyclass`
- `native/Cargo.toml` — add `thiserror = "1"`

**New (Python):**
- `src/wows_replay_parser/gamedata/native_descriptor.py` — `NativeDescriptorBuilder` + `post_process(value)`
- `native/tests/test_compile_schema.py`, `native/tests/test_executor.py`

**Modified (Python):**
- `src/wows_replay_parser/gamedata/schema_builder.py` — `build_method_schema` / `build_property_schema` return Rust-backed `_NativeSchema` objects instead of Construct trees (phase-by-phase)

---

## Task 1: Add `thiserror` dependency and `DecodeError` enum

**Files:**
- Modify: `native/Cargo.toml`
- Create: `native/src/error.rs`
- Modify: `native/src/lib.rs:1-3` (add `mod error;`)

- [ ] **Step 1: Add thiserror to Cargo.toml**

```toml
[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
thiserror = "1"
```

- [ ] **Step 2: Create error.rs**

```rust
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[derive(Debug, thiserror::Error)]
pub enum DecodeError {
    #[error("buffer underrun at offset {offset}: need {need} bytes, have {have}")]
    BufferUnderrun { offset: usize, need: usize, have: usize },

    #[error("unknown alias {0:?}")]
    UnknownAlias(String),

    #[error("schema mismatch at {path}: expected {expected}, got {got}")]
    SchemaMismatch { path: String, expected: String, got: String },

    #[error("invalid count prefix: {0}")]
    InvalidCount(u32),

    #[error("invalid descriptor: {0}")]
    InvalidDescriptor(String),
}

impl From<DecodeError> for PyErr {
    fn from(e: DecodeError) -> Self {
        PyValueError::new_err(e.to_string())
    }
}
```

- [ ] **Step 3: Wire module into lib.rs**

Add `mod error;` at the top of `native/src/lib.rs`, before the existing `use` statements.

- [ ] **Step 4: Build to confirm compile**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
```
Expected: clean build, no warnings about unused enum variants (allow if needed via `#[allow(dead_code)]` until later phases use them).

- [ ] **Step 5: Commit**

```bash
git add native/Cargo.toml native/src/error.rs native/src/lib.rs
git commit -m "Add DecodeError enum (thiserror)"
```

---

## Task 2: Skeleton `Schema` pyclass and `compile_schema` (single primitive)

**Files:**
- Create: `native/src/schema.rs`
- Modify: `native/src/lib.rs` (add `mod schema;`, register `compile_schema` + `Schema`)
- Create: `native/tests/test_compile_schema.py`

- [ ] **Step 1: Write failing test for compile_schema(int32)**

`native/tests/test_compile_schema.py`:
```python
def test_compile_schema_int32(native):
    handle = native.compile_schema({"kind": "int32"})
    assert handle is not None
    assert repr(handle).startswith("<wows_native.Schema")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/toalba/projects/wows/wows-replay-parser && uv run pytest native/tests/test_compile_schema.py::test_compile_schema_int32 -v
```
Expected: FAIL — `module 'wows_native' has no attribute 'compile_schema'`.

- [ ] **Step 3: Create schema.rs with skeleton**

```rust
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::error::DecodeError;

#[derive(Debug, Clone)]
pub enum Schema {
    Int32,
    // more variants land in later tasks
}

#[pyclass(name = "Schema", module = "wows_native")]
pub struct PySchema {
    pub schema: Schema,
}

impl PySchema {
    fn from_descriptor(d: &Bound<'_, PyDict>) -> Result<Self, DecodeError> {
        let kind: String = d
            .get_item("kind")
            .map_err(|_| DecodeError::InvalidDescriptor("missing kind".into()))?
            .ok_or_else(|| DecodeError::InvalidDescriptor("missing kind".into()))?
            .extract()
            .map_err(|_| DecodeError::InvalidDescriptor("kind must be string".into()))?;
        match kind.as_str() {
            "int32" => Ok(PySchema { schema: Schema::Int32 }),
            other => Err(DecodeError::InvalidDescriptor(format!("unknown kind {other:?}"))),
        }
    }
}

#[pyfunction]
pub fn compile_schema(descriptor: &Bound<'_, PyDict>) -> PyResult<PySchema> {
    Ok(PySchema::from_descriptor(descriptor)?)
}
```

- [ ] **Step 4: Register in lib.rs**

In `native/src/lib.rs`, add `mod schema;` near the top, then in the `#[pymodule]` body:
```rust
m.add_function(wrap_pyfunction!(schema::compile_schema, m)?)?;
m.add_class::<schema::PySchema>()?;
```

- [ ] **Step 5: Build, run test**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_compile_schema.py::test_compile_schema_int32 -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add native/src/schema.rs native/src/lib.rs native/tests/test_compile_schema.py
git commit -m "Add Schema pyclass + compile_schema skeleton (int32 only)"
```

---

## Task 3: Skeleton `decode` returning a single int32

**Files:**
- Create: `native/src/value.rs`, `native/src/executor.rs`
- Modify: `native/src/lib.rs`
- Create: `native/tests/test_executor.py`

- [ ] **Step 1: Write failing test**

`native/tests/test_executor.py`:
```python
import struct


def test_decode_int32(native):
    handle = native.compile_schema({"kind": "int32"})
    data = struct.pack("<i", -42)
    value, new_offset = native.decode(handle, data, 0)
    assert value == -42
    assert new_offset == 4
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest native/tests/test_executor.py::test_decode_int32 -v
```
Expected: FAIL — `module 'wows_native' has no attribute 'decode'`.

- [ ] **Step 3: Create value.rs**

```rust
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

#[derive(Debug)]
pub enum Value {
    None,
    Int(i64),
    UInt(u64),
    Float(f64),
    Bool(bool),
    Bytes(Vec<u8>),
    Str(String),
    Tuple2(f32, f32),
    Tuple3(f32, f32, f32),
    Dict(Vec<(String, Value)>),
    List(Vec<Value>),
    // markers added in later tasks
}

impl Value {
    pub fn to_pyobject(&self, py: Python<'_>) -> PyResult<PyObject> {
        Ok(match self {
            Value::None => py.None(),
            Value::Int(i) => i.into_py(py),
            Value::UInt(u) => u.into_py(py),
            Value::Float(f) => f.into_py(py),
            Value::Bool(b) => b.into_py(py),
            Value::Bytes(b) => pyo3::types::PyBytes::new_bound(py, b).into_py(py),
            Value::Str(s) => s.into_py(py),
            Value::Tuple2(x, y) => (*x, *y).into_py(py),
            Value::Tuple3(x, y, z) => (*x, *y, *z).into_py(py),
            Value::Dict(fields) => {
                let d = PyDict::new_bound(py);
                for (k, v) in fields {
                    d.set_item(k, v.to_pyobject(py)?)?;
                }
                d.into_py(py)
            }
            Value::List(items) => {
                let mut out = Vec::with_capacity(items.len());
                for it in items {
                    out.push(it.to_pyobject(py)?);
                }
                PyList::new_bound(py, out).into_py(py)
            }
        })
    }
}
```

- [ ] **Step 4: Create executor.rs**

```rust
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::error::DecodeError;
use crate::schema::{PySchema, Schema};
use crate::value::Value;

fn slice_at<'a>(buf: &'a [u8], offset: usize, size: usize) -> Result<&'a [u8], DecodeError> {
    buf.get(offset..offset + size).ok_or(DecodeError::BufferUnderrun {
        offset, need: size, have: buf.len(),
    })
}

pub fn decode_value(
    schema: &Schema,
    buf: &[u8],
    offset: usize,
) -> Result<(Value, usize), DecodeError> {
    match schema {
        Schema::Int32 => {
            let chunk = slice_at(buf, offset, 4)?;
            let v = i32::from_le_bytes(chunk.try_into().unwrap()) as i64;
            Ok((Value::Int(v), offset + 4))
        }
    }
}

#[pyfunction]
pub fn decode(
    py: Python<'_>,
    handle: &PySchema,
    data: &Bound<'_, PyBytes>,
    offset: usize,
) -> PyResult<(PyObject, usize)> {
    let (value, new_offset) = decode_value(&handle.schema, data.as_bytes(), offset)?;
    Ok((value.to_pyobject(py)?, new_offset))
}
```

- [ ] **Step 5: Register in lib.rs**

```rust
mod value;
mod executor;

// inside #[pymodule]:
m.add_function(wrap_pyfunction!(executor::decode, m)?)?;
```

- [ ] **Step 6: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py::test_decode_int32 -v
git add native/src/value.rs native/src/executor.rs native/src/lib.rs native/tests/test_executor.py
git commit -m "Add decode skeleton + Value enum (int32 only)"
```

Expected test result: PASS.

---

## Task 4: All 14 fixed-width primitives in Schema + executor

**Files:**
- Modify: `native/src/schema.rs`, `native/src/executor.rs`, `native/src/value.rs`
- Modify: `native/tests/test_compile_schema.py`, `native/tests/test_executor.py`

- [ ] **Step 1: Add tests for every fixed primitive**

Append to `native/tests/test_executor.py`:
```python
import struct
import pytest


@pytest.mark.parametrize("kind, fmt, sample", [
    ("int8",    "<b", -128),
    ("int16",   "<h", -32768),
    ("int32",   "<i", -2147483648),
    ("int64",   "<q", -9223372036854775808),
    ("uint8",   "<B", 255),
    ("uint16",  "<H", 65535),
    ("uint32",  "<I", 4294967295),
    ("uint64",  "<Q", 18446744073709551615),
    ("float32", "<f", 3.14),
    ("float64", "<d", 3.141592653589793),
])
def test_decode_fixed_primitive(native, kind, fmt, sample):
    handle = native.compile_schema({"kind": kind})
    data = struct.pack(fmt, sample)
    value, off = native.decode(handle, data, 0)
    if isinstance(sample, float):
        assert value == pytest.approx(sample)
    else:
        assert value == sample
    assert off == struct.calcsize(fmt)


def test_decode_bool(native):
    h = native.compile_schema({"kind": "bool"})
    assert native.decode(h, b"\x00", 0) == (False, 1)
    assert native.decode(h, b"\x42", 0) == (True, 1)


def test_decode_mailbox(native):
    h = native.compile_schema({"kind": "mailbox"})
    blob = bytes(range(16))
    value, off = native.decode(h, blob, 0)
    assert value == blob
    assert off == 16


def test_decode_vector2(native):
    h = native.compile_schema({"kind": "vector2"})
    data = struct.pack("<ff", 1.5, -2.5)
    assert native.decode(h, data, 0) == ((1.5, -2.5), 8)


def test_decode_vector3(native):
    h = native.compile_schema({"kind": "vector3"})
    data = struct.pack("<fff", 1.0, 2.0, 3.0)
    assert native.decode(h, data, 0) == ((1.0, 2.0, 3.0), 12)
```

- [ ] **Step 2: Run to verify failures**

```bash
uv run pytest native/tests/test_executor.py -v
```
Expected: existing `test_decode_int32` PASSes; new tests FAIL with `unknown kind` from `compile_schema`.

- [ ] **Step 3: Extend Schema enum**

In `native/src/schema.rs`:
```rust
#[derive(Debug, Clone)]
pub enum Schema {
    Int8, Int16, Int32, Int64,
    UInt8, UInt16, UInt32, UInt64,
    Float32, Float64,
    Bool,
    Mailbox,
    Vector2, Vector3,
}
```

- [ ] **Step 4: Extend compile_schema match**

```rust
match kind.as_str() {
    "int8" => Ok(PySchema { schema: Schema::Int8 }),
    "int16" => Ok(PySchema { schema: Schema::Int16 }),
    "int32" => Ok(PySchema { schema: Schema::Int32 }),
    "int64" => Ok(PySchema { schema: Schema::Int64 }),
    "uint8" => Ok(PySchema { schema: Schema::UInt8 }),
    "uint16" => Ok(PySchema { schema: Schema::UInt16 }),
    "uint32" => Ok(PySchema { schema: Schema::UInt32 }),
    "uint64" => Ok(PySchema { schema: Schema::UInt64 }),
    "float32" | "float" => Ok(PySchema { schema: Schema::Float32 }),
    "float64" => Ok(PySchema { schema: Schema::Float64 }),
    "bool" => Ok(PySchema { schema: Schema::Bool }),
    "mailbox" => Ok(PySchema { schema: Schema::Mailbox }),
    "vector2" => Ok(PySchema { schema: Schema::Vector2 }),
    "vector3" => Ok(PySchema { schema: Schema::Vector3 }),
    other => Err(DecodeError::InvalidDescriptor(format!("unknown kind {other:?}"))),
}
```

- [ ] **Step 5: Extend decode_value match**

In `native/src/executor.rs`, replace the body of `decode_value` with a macro-driven match. Reuse the `decode_fixed_le!` pattern already in `lib.rs`:

```rust
macro_rules! le_int { ($buf:ident, $off:ident, $ty:ty, $variant:expr) => {{
    const SZ: usize = std::mem::size_of::<$ty>();
    let chunk = slice_at($buf, $off, SZ)?;
    let v = <$ty>::from_le_bytes(chunk.try_into().unwrap());
    Ok(($variant(v.into()), $off + SZ))
}}}

pub fn decode_value(schema: &Schema, buf: &[u8], offset: usize) -> Result<(Value, usize), DecodeError> {
    match schema {
        Schema::Int8   => le_int!(buf, offset, i8,  |v: i64| Value::Int(v)),
        Schema::Int16  => le_int!(buf, offset, i16, |v: i64| Value::Int(v)),
        Schema::Int32  => le_int!(buf, offset, i32, |v: i64| Value::Int(v)),
        Schema::Int64  => le_int!(buf, offset, i64, |v: i64| Value::Int(v)),
        Schema::UInt8  => le_int!(buf, offset, u8,  |v: u64| Value::UInt(v)),
        Schema::UInt16 => le_int!(buf, offset, u16, |v: u64| Value::UInt(v)),
        Schema::UInt32 => le_int!(buf, offset, u32, |v: u64| Value::UInt(v)),
        Schema::UInt64 => le_int!(buf, offset, u64, |v: u64| Value::UInt(v)),
        Schema::Float32 => {
            let c = slice_at(buf, offset, 4)?;
            Ok((Value::Float(f32::from_le_bytes(c.try_into().unwrap()) as f64), offset + 4))
        }
        Schema::Float64 => {
            let c = slice_at(buf, offset, 8)?;
            Ok((Value::Float(f64::from_le_bytes(c.try_into().unwrap())), offset + 8))
        }
        Schema::Bool => {
            let c = slice_at(buf, offset, 1)?;
            Ok((Value::Bool(c[0] != 0), offset + 1))
        }
        Schema::Mailbox => {
            let c = slice_at(buf, offset, 16)?;
            Ok((Value::Bytes(c.to_vec()), offset + 16))
        }
        Schema::Vector2 => {
            let c = slice_at(buf, offset, 8)?;
            let x = f32::from_le_bytes(c[0..4].try_into().unwrap());
            let y = f32::from_le_bytes(c[4..8].try_into().unwrap());
            Ok((Value::Tuple2(x, y), offset + 8))
        }
        Schema::Vector3 => {
            let c = slice_at(buf, offset, 12)?;
            let x = f32::from_le_bytes(c[0..4].try_into().unwrap());
            let y = f32::from_le_bytes(c[4..8].try_into().unwrap());
            let z = f32::from_le_bytes(c[8..12].try_into().unwrap());
            Ok((Value::Tuple3(x, y, z), offset + 12))
        }
    }
}
```

(The macro `le_int!` adapts the fixed-width int branches; if it doesn't compile because of the closure-arg type, replace each with the explicit slice/from_le_bytes form like Float32/64.)

- [ ] **Step 6: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/tests/test_executor.py
git commit -m "Schema executor: all 14 fixed-width primitives"
```

Expected: 16+ tests pass.

---

## Task 5: Variable-length primitives (string / unicode_string / blob / python with mode)

**Files:**
- Modify: `native/src/schema.rs`, `native/src/executor.rs`
- Append: `native/tests/test_executor.py`

- [ ] **Step 1: Write failing tests**

```python
def test_decode_blob_method_mode(native):
    h = native.compile_schema({"kind": "blob", "mode": "method"})
    data = b"\x05hello"
    assert native.decode(h, data, 0) == (b"hello", 6)


def test_decode_blob_u32_mode(native):
    h = native.compile_schema({"kind": "blob", "mode": "u32"})
    data = (5).to_bytes(4, "little") + b"hello"
    assert native.decode(h, data, 0) == (b"hello", 9)


def test_decode_string_utf8(native):
    h = native.compile_schema({"kind": "string", "mode": "method"})
    payload = "héllo".encode("utf-8")
    data = bytes([len(payload)]) + payload
    assert native.decode(h, data, 0) == ("héllo", 1 + len(payload))


def test_decode_string_latin1_fallback(native):
    h = native.compile_schema({"kind": "string", "mode": "method"})
    data = b"\x02\xc3\x28"  # invalid utf-8
    value, off = native.decode(h, data, 0)
    assert value == "Ã("
    assert off == 3


def test_decode_unicode_string(native):
    h = native.compile_schema({"kind": "unicode_string", "mode": "u32"})
    payload = "test".encode("utf-8")
    data = (len(payload)).to_bytes(4, "little") + payload
    assert native.decode(h, data, 0) == ("test", 8)


def test_decode_python(native):
    h = native.compile_schema({"kind": "python", "mode": "method"})
    data = b"\x04\x80\x02ab"
    assert native.decode(h, data, 0) == (b"\x80\x02ab", 5)
```

- [ ] **Step 2: Run to verify failures**

Expected: `unknown kind` errors from `compile_schema`.

- [ ] **Step 3: Extend Schema and compile_schema**

In `schema.rs`:
```rust
#[derive(Debug, Clone, Copy)]
pub enum LengthMode { Method, U32 }

impl LengthMode {
    pub fn parse(s: &str) -> Result<Self, DecodeError> {
        match s {
            "method" => Ok(LengthMode::Method),
            "u32" => Ok(LengthMode::U32),
            other => Err(DecodeError::InvalidDescriptor(format!("unknown mode {other:?}"))),
        }
    }
}

#[derive(Debug, Clone)]
pub enum Schema {
    // … existing …
    Blob(LengthMode),
    Python(LengthMode),
    Str(LengthMode),
    UnicodeStr(LengthMode),
}
```

In the `compile_schema` match, add:
```rust
"blob" | "python" | "string" | "unicode_string" => {
    let mode_str: String = d.get_item("mode")
        .ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("missing mode".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("mode must be string".into()))?;
    let mode = LengthMode::parse(&mode_str)?;
    Ok(PySchema { schema: match kind.as_str() {
        "blob"           => Schema::Blob(mode),
        "python"         => Schema::Python(mode),
        "string"         => Schema::Str(mode),
        "unicode_string" => Schema::UnicodeStr(mode),
        _ => unreachable!(),
    }})
}
```

- [ ] **Step 4: Extend decode_value**

```rust
fn read_length(mode: LengthMode, buf: &[u8], offset: usize) -> Result<(usize, usize), DecodeError> {
    match mode {
        LengthMode::Method => {
            let first = slice_at(buf, offset, 1)?[0];
            if first < 0xFF {
                Ok((first as usize, offset + 1))
            } else {
                let len_bytes = slice_at(buf, offset + 1, 2)?;
                let length = u16::from_le_bytes(len_bytes.try_into().unwrap()) as usize;
                slice_at(buf, offset + 3, 1)?; // padding byte must exist
                Ok((length, offset + 4))
            }
        }
        LengthMode::U32 => {
            let len_bytes = slice_at(buf, offset, 4)?;
            Ok((u32::from_le_bytes(len_bytes.try_into().unwrap()) as usize, offset + 4))
        }
    }
}

fn decode_string_bytes(payload: &[u8]) -> String {
    let text = match std::str::from_utf8(payload) {
        Ok(s) => s.to_owned(),
        Err(_) => payload.iter().map(|&b| b as char).collect(),
    };
    if text.contains('\0') { text.replace('\0', "") } else { text }
}
```

In `decode_value`, add branches:
```rust
Schema::Blob(mode) | Schema::Python(mode) => {
    let (length, payload_start) = read_length(*mode, buf, offset)?;
    let payload = slice_at(buf, payload_start, length)?;
    Ok((Value::Bytes(payload.to_vec()), payload_start + length))
}
Schema::Str(mode) | Schema::UnicodeStr(mode) => {
    let (length, payload_start) = read_length(*mode, buf, offset)?;
    let payload = slice_at(buf, payload_start, length)?;
    Ok((Value::Str(decode_string_bytes(payload)), payload_start + length))
}
```

- [ ] **Step 5: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/tests/test_executor.py
git commit -m "Schema executor: variable-length primitives (blob/python/string/unicode_string)"
```

---

## Task 6: FIXED_DICT (primitive-only fields)

**Files:**
- Modify: `native/src/schema.rs`, `native/src/executor.rs`
- Append: `native/tests/test_executor.py`

- [ ] **Step 1: Write failing test**

```python
def test_decode_fixed_dict_primitives(native):
    descriptor = {
        "kind": "fixed_dict",
        "fields": [
            {"name": "x",  "schema": {"kind": "float32"}},
            {"name": "y",  "schema": {"kind": "float32"}},
            {"name": "id", "schema": {"kind": "uint16"}},
        ],
    }
    handle = native.compile_schema(descriptor)
    data = struct.pack("<ffH", 1.5, -2.5, 42)
    value, off = native.decode(handle, data, 0)
    assert value == {"x": 1.5, "y": -2.5, "id": 42}
    assert off == 10
```

- [ ] **Step 2: Run to verify failure**

Expected: `unknown kind 'fixed_dict'`.

- [ ] **Step 3: Extend Schema with FixedDict variant**

```rust
#[derive(Debug, Clone)]
pub enum Schema {
    // …
    FixedDict { fields: Vec<(String, Schema)> },
}
```

- [ ] **Step 4: Recursive descriptor parse**

Refactor `from_descriptor` so the body becomes a top-level helper that recurses on nested descriptors:

```rust
pub fn schema_from_dict(d: &Bound<'_, PyDict>) -> Result<Schema, DecodeError> {
    let kind: String = d.get_item("kind").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("missing kind".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("kind must be string".into()))?;
    match kind.as_str() {
        // … existing fixed primitives & variable primitives unchanged …
        "fixed_dict" => {
            let fields_obj = d.get_item("fields").ok().flatten()
                .ok_or_else(|| DecodeError::InvalidDescriptor("fixed_dict missing fields".into()))?;
            let fields_list = fields_obj.downcast::<pyo3::types::PyList>()
                .map_err(|_| DecodeError::InvalidDescriptor("fields must be list".into()))?;
            let mut out = Vec::with_capacity(fields_list.len());
            for item in fields_list.iter() {
                let item_dict = item.downcast::<PyDict>()
                    .map_err(|_| DecodeError::InvalidDescriptor("field must be dict".into()))?;
                let name: String = item_dict.get_item("name").ok().flatten()
                    .ok_or_else(|| DecodeError::InvalidDescriptor("field missing name".into()))?
                    .extract()
                    .map_err(|_| DecodeError::InvalidDescriptor("field name must be string".into()))?;
                let sub_dict = item_dict.get_item("schema").ok().flatten()
                    .ok_or_else(|| DecodeError::InvalidDescriptor("field missing schema".into()))?;
                let sub = schema_from_dict(sub_dict.downcast::<PyDict>()
                    .map_err(|_| DecodeError::InvalidDescriptor("schema must be dict".into()))?)?;
                out.push((name, sub));
            }
            Ok(Schema::FixedDict { fields: out })
        }
        other => Err(DecodeError::InvalidDescriptor(format!("unknown kind {other:?}"))),
    }
}

#[pyfunction]
pub fn compile_schema(descriptor: &Bound<'_, PyDict>) -> PyResult<PySchema> {
    Ok(PySchema { schema: schema_from_dict(descriptor)? })
}
```

- [ ] **Step 5: Extend decode_value**

```rust
Schema::FixedDict { fields } => {
    let mut out = Vec::with_capacity(fields.len());
    let mut cur = offset;
    for (name, sub) in fields {
        let (v, new_off) = decode_value(sub, buf, cur)?;
        out.push((name.clone(), v));
        cur = new_off;
    }
    Ok((Value::Dict(out), cur))
}
```

- [ ] **Step 6: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/tests/test_executor.py
git commit -m "Schema executor: FIXED_DICT (primitive-only fields)"
```

---

## Task 7: AllowNone wrapper

- [ ] **Step 1: Write failing test**

```python
def test_decode_allow_none_present(native):
    h = native.compile_schema({
        "kind": "allow_none",
        "inner": {"kind": "uint32"},
    })
    # flag=1, then 4 bytes
    data = b"\x01" + (42).to_bytes(4, "little")
    assert native.decode(h, data, 0) == (42, 5)


def test_decode_allow_none_absent(native):
    h = native.compile_schema({
        "kind": "allow_none",
        "inner": {"kind": "uint32"},
    })
    assert native.decode(h, b"\x00", 0) == (None, 1)
```

- [ ] **Step 2: Verify fail, add Schema variant**

```rust
Schema::AllowNone(Box<Schema>),
```

In `schema_from_dict`:
```rust
"allow_none" => {
    let inner_obj = d.get_item("inner").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("allow_none missing inner".into()))?;
    let inner = schema_from_dict(inner_obj.downcast::<PyDict>()
        .map_err(|_| DecodeError::InvalidDescriptor("inner must be dict".into()))?)?;
    Ok(Schema::AllowNone(Box::new(inner)))
}
```

- [ ] **Step 3: Extend decode_value**

```rust
Schema::AllowNone(inner) => {
    let flag = slice_at(buf, offset, 1)?[0];
    if flag == 0 {
        Ok((Value::None, offset + 1))
    } else {
        decode_value(inner, buf, offset + 1)
    }
}
```

- [ ] **Step 4: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/tests/test_executor.py
git commit -m "Schema executor: AllowNone wrapper"
```

---

## Task 8: ARRAY (count u8 + element schema)

- [ ] **Step 1: Write failing tests**

```python
def test_decode_array_uint16(native):
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "uint16"},
    })
    data = bytes([3]) + struct.pack("<HHH", 1, 2, 3)
    assert native.decode(h, data, 0) == ([1, 2, 3], 7)


def test_decode_array_of_fixed_dict(native):
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {
            "kind": "fixed_dict",
            "fields": [
                {"name": "x", "schema": {"kind": "float32"}},
                {"name": "id", "schema": {"kind": "uint16"}},
            ],
        },
    })
    rec = lambda x, i: struct.pack("<fH", x, i)
    data = bytes([2]) + rec(1.5, 10) + rec(-2.5, 20)
    value, off = native.decode(h, data, 0)
    assert value == [{"x": 1.5, "id": 10}, {"x": -2.5, "id": 20}]
    assert off == 1 + 2 * 6


def test_decode_array_empty(native):
    h = native.compile_schema({
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "int32"},
    })
    assert native.decode(h, b"\x00", 0) == ([], 1)
```

- [ ] **Step 2: Verify fail, add Schema variant**

```rust
Schema::Array { element: Box<Schema> },
```

(`count_prefix` is always `uint8` per BigWorld spec; we validate it but don't store it.)

In `schema_from_dict`:
```rust
"array" => {
    let count_prefix: String = d.get_item("count_prefix").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("array missing count_prefix".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("count_prefix must be string".into()))?;
    if count_prefix != "uint8" {
        return Err(DecodeError::InvalidDescriptor(
            format!("array count_prefix must be uint8, got {count_prefix}")));
    }
    let element_obj = d.get_item("element").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("array missing element".into()))?;
    let element = schema_from_dict(element_obj.downcast::<PyDict>()
        .map_err(|_| DecodeError::InvalidDescriptor("element must be dict".into()))?)?;
    Ok(Schema::Array { element: Box::new(element) })
}
```

- [ ] **Step 3: Extend decode_value**

```rust
Schema::Array { element } => {
    let count = slice_at(buf, offset, 1)?[0] as usize;
    let mut cur = offset + 1;
    let mut out = Vec::with_capacity(count);
    for _ in 0..count {
        let (v, new_off) = decode_value(element, buf, cur)?;
        out.push(v);
        cur = new_off;
    }
    Ok((Value::List(out), cur))
}
```

- [ ] **Step 4: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/tests/test_executor.py
git commit -m "Schema executor: ARRAY (any element schema)"
```

---

## Task 9: USER_TYPE marker + auto_pickle_blob marker

- [ ] **Step 1: Write failing tests**

```python
def test_decode_user_type_marker(native):
    h = native.compile_schema({
        "kind": "user_type",
        "alias": "ZIPPED_BLOB",
        "blob_mode": "method",
    })
    payload = b"hello"
    data = bytes([len(payload)]) + payload
    value, off = native.decode(h, data, 0)
    assert value == {"__alias__": "ZIPPED_BLOB", "__bytes__": b"hello"}
    assert off == 6


def test_decode_auto_pickle_marker(native):
    h = native.compile_schema({
        "kind": "auto_pickle_blob",
        "blob_mode": "method",
    })
    payload = b"\x80\x02..."
    data = bytes([len(payload)]) + payload
    value, off = native.decode(h, data, 0)
    assert value == {"__autopickle__": True, "__bytes__": payload}
    assert off == 1 + len(payload)
```

- [ ] **Step 2: Verify fail, extend Value enum**

In `value.rs`:
```rust
pub enum Value {
    // …
    UserTypeMarker { alias: String, bytes: Vec<u8> },
    AutoPickleMarker(Vec<u8>),
}
```

Add to `to_pyobject`:
```rust
Value::UserTypeMarker { alias, bytes } => {
    let d = PyDict::new_bound(py);
    d.set_item("__alias__", alias)?;
    d.set_item("__bytes__", PyBytes::new_bound(py, bytes))?;
    d.into_py(py)
}
Value::AutoPickleMarker(bytes) => {
    let d = PyDict::new_bound(py);
    d.set_item("__autopickle__", true)?;
    d.set_item("__bytes__", PyBytes::new_bound(py, bytes))?;
    d.into_py(py)
}
```

- [ ] **Step 3: Extend Schema variants**

```rust
Schema::UserType { alias: String, blob_mode: LengthMode },
Schema::AutoPickleBlob { blob_mode: LengthMode },
```

In `schema_from_dict`:
```rust
"user_type" => {
    let alias: String = d.get_item("alias").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("user_type missing alias".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("alias must be string".into()))?;
    let mode_s: String = d.get_item("blob_mode").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("user_type missing blob_mode".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("blob_mode must be string".into()))?;
    Ok(Schema::UserType { alias, blob_mode: LengthMode::parse(&mode_s)? })
}
"auto_pickle_blob" => {
    let mode_s: String = d.get_item("blob_mode").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("auto_pickle_blob missing blob_mode".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("blob_mode must be string".into()))?;
    Ok(Schema::AutoPickleBlob { blob_mode: LengthMode::parse(&mode_s)? })
}
```

- [ ] **Step 4: Extend decode_value**

```rust
Schema::UserType { alias, blob_mode } => {
    let (length, payload_start) = read_length(*blob_mode, buf, offset)?;
    let payload = slice_at(buf, payload_start, length)?;
    Ok((Value::UserTypeMarker { alias: alias.clone(), bytes: payload.to_vec() },
        payload_start + length))
}
Schema::AutoPickleBlob { blob_mode } => {
    let (length, payload_start) = read_length(*blob_mode, buf, offset)?;
    let payload = slice_at(buf, payload_start, length)?;
    Ok((Value::AutoPickleMarker(payload.to_vec()), payload_start + length))
}
```

- [ ] **Step 5: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/src/value.rs native/tests/test_executor.py
git commit -m "Schema executor: USER_TYPE and auto_pickle_blob markers"
```

---

## Task 10: Tuple (forward-compat, 0 in current alias.xml)

- [ ] **Step 1: Test**

```python
def test_decode_tuple(native):
    h = native.compile_schema({
        "kind": "tuple",
        "elements": [{"kind": "int32"}, {"kind": "string", "mode": "method"}],
    })
    data = struct.pack("<i", 7) + b"\x03foo"
    value, off = native.decode(h, data, 0)
    assert value == [7, "foo"]
    assert off == 4 + 4
```

- [ ] **Step 2: Implement**

```rust
Schema::Tuple { elements: Vec<Schema> },
```

`schema_from_dict`:
```rust
"tuple" => {
    let elems_obj = d.get_item("elements").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("tuple missing elements".into()))?;
    let elems_list = elems_obj.downcast::<pyo3::types::PyList>()
        .map_err(|_| DecodeError::InvalidDescriptor("elements must be list".into()))?;
    let mut out = Vec::with_capacity(elems_list.len());
    for item in elems_list.iter() {
        out.push(schema_from_dict(item.downcast::<PyDict>()
            .map_err(|_| DecodeError::InvalidDescriptor("element must be dict".into()))?)?);
    }
    Ok(Schema::Tuple { elements: out })
}
```

`decode_value`:
```rust
Schema::Tuple { elements } => {
    let mut out = Vec::with_capacity(elements.len());
    let mut cur = offset;
    for sub in elements {
        let (v, new_off) = decode_value(sub, buf, cur)?;
        out.push(v);
        cur = new_off;
    }
    Ok((Value::List(out), cur))
}
```

- [ ] **Step 3: Build, run, commit**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd .. && uv run pytest native/tests/test_executor.py -v
git add native/src/schema.rs native/src/executor.rs native/tests/test_executor.py
git commit -m "Schema executor: TUPLE"
```

---

## Task 11: Python `NativeDescriptorBuilder` skeleton

**Files:**
- Create: `src/wows_replay_parser/gamedata/native_descriptor.py`
- Create: `tests/test_native_descriptor.py`

- [ ] **Step 1: Write failing test for primitive descriptor**

```python
# tests/test_native_descriptor.py
import pytest

from wows_replay_parser.gamedata.alias_registry import AliasRegistry
from wows_replay_parser.gamedata.entity_registry import EntityRegistry
from wows_replay_parser.gamedata.native_descriptor import NativeDescriptorBuilder


def test_descriptor_for_int32():
    aliases = AliasRegistry({})
    registry = EntityRegistry({})
    b = NativeDescriptorBuilder(aliases, registry)
    assert b.descriptor_for_type("INT32") == {"kind": "int32"}
```

- [ ] **Step 2: Create native_descriptor.py**

```python
"""Builds wows_native schema descriptors from BigWorld entity defs.

Walks the AliasRegistry / EntityRegistry that SchemaBuilder also uses,
emitting the dict-descriptor format consumed by wows_native.compile_schema.
Reference: docs/superpowers/specs/2026-04-30-rust-schema-executor-design.md
"""
from __future__ import annotations

import re
from typing import Any

from wows_replay_parser.gamedata.alias_registry import AliasRegistry, TypeAlias
from wows_replay_parser.gamedata.entity_registry import EntityRegistry

_PRIMITIVE_KINDS = {
    "INT8": "int8", "INT16": "int16", "INT32": "int32", "INT64": "int64",
    "UINT8": "uint8", "UINT16": "uint16", "UINT32": "uint32", "UINT64": "uint64",
    "FLOAT": "float32", "FLOAT32": "float32", "FLOAT64": "float64",
    "BOOL": "bool", "MAILBOX": "mailbox",
    "VECTOR2": "vector2", "VECTOR3": "vector3",
}

_VARIABLE_PRIMITIVES = {"STRING", "UNICODE_STRING", "BLOB", "PYTHON"}

_VARIABLE_KIND_MAP = {
    "STRING": "string", "UNICODE_STRING": "unicode_string",
    "BLOB": "blob", "PYTHON": "python",
}


class NativeDescriptorBuilder:
    def __init__(self, aliases: AliasRegistry, registry: EntityRegistry) -> None:
        self._aliases = aliases
        self._registry = registry

    def descriptor_for_type(self, type_name: str, *, in_method: bool = True) -> dict[str, Any]:
        type_name = type_name.strip()
        if type_name in _PRIMITIVE_KINDS:
            return {"kind": _PRIMITIVE_KINDS[type_name]}
        if type_name in _VARIABLE_PRIMITIVES:
            mode = "method" if in_method else "u32"
            return {"kind": _VARIABLE_KIND_MAP[type_name], "mode": mode}
        # alias chain / composites added in subsequent tasks
        raise NotImplementedError(f"descriptor for {type_name!r} not yet implemented")
```

- [ ] **Step 3: Run, commit**

```bash
uv run pytest tests/test_native_descriptor.py -v
git add src/wows_replay_parser/gamedata/native_descriptor.py tests/test_native_descriptor.py
git commit -m "NativeDescriptorBuilder skeleton (fixed primitives)"
```

Expected: PASS.

---

## Task 12: Descriptor builder — inline ARRAY<of>X</of> + USER_TYPE alias resolution

- [ ] **Step 1: Failing tests**

Append to `tests/test_native_descriptor.py`:
```python
def test_descriptor_inline_array_uint16():
    b = NativeDescriptorBuilder(AliasRegistry({}), EntityRegistry({}))
    desc = b.descriptor_for_type("ARRAY<of>UINT16</of>", in_method=True)
    assert desc == {
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "uint16"},
    }


def test_descriptor_alias_to_primitive():
    aliases = AliasRegistry({"ENTITY_ID": TypeAlias(name="ENTITY_ID", base_type="INT32")})
    b = NativeDescriptorBuilder(aliases, EntityRegistry({}))
    assert b.descriptor_for_type("ENTITY_ID") == {"kind": "int32"}


def test_descriptor_alias_implementedby():
    alias = TypeAlias(
        name="ZIPPED_BLOB",
        base_type="BLOB",
        implemented_by="ZippedBlobConverter.converter",
    )
    aliases = AliasRegistry({"ZIPPED_BLOB": alias})
    b = NativeDescriptorBuilder(aliases, EntityRegistry({}))
    assert b.descriptor_for_type("ZIPPED_BLOB", in_method=True) == {
        "kind": "user_type", "alias": "ZIPPED_BLOB", "blob_mode": "method",
    }
```

(Adjust the `TypeAlias` constructor calls to match the actual `TypeAlias` dataclass — check `src/wows_replay_parser/gamedata/alias_registry.py` for the right field names; if the dataclass requires fields like `fields=()`, `element_type=None`, etc., supply them explicitly.)

- [ ] **Step 2: Implement**

Replace the `descriptor_for_type` body:
```python
def descriptor_for_type(self, type_name: str, *, in_method: bool = True) -> dict[str, Any]:
    type_name = type_name.strip()
    if type_name in _PRIMITIVE_KINDS:
        return {"kind": _PRIMITIVE_KINDS[type_name]}
    if type_name in _VARIABLE_PRIMITIVES:
        return {"kind": _VARIABLE_KIND_MAP[type_name], "mode": "method" if in_method else "u32"}

    # Inline ARRAY<of>X</of>
    m = re.match(r"^ARRAY<of>(.+)</of>$", type_name)
    if m:
        return {
            "kind": "array",
            "count_prefix": "uint8",
            "element": self.descriptor_for_type(m.group(1), in_method=in_method),
        }

    # Alias
    alias = self._aliases.resolve(type_name)
    if alias is not None:
        return self._descriptor_for_alias(alias, in_method=in_method)

    raise NotImplementedError(f"descriptor for {type_name!r} not yet implemented")

def _descriptor_for_alias(self, alias: TypeAlias, *, in_method: bool) -> dict[str, Any]:
    base = alias.base_type.strip()
    # USER_TYPE with implementedBy → marker (variable types only)
    if alias.has_implemented_by and base not in ("FIXED_DICT", "ARRAY", "TUPLE"):
        return {
            "kind": "user_type",
            "alias": alias.name,
            "blob_mode": "method" if in_method else "u32",
        }
    if base in _PRIMITIVE_KINDS:
        return {"kind": _PRIMITIVE_KINDS[base]}
    if base in _VARIABLE_PRIMITIVES:
        return {"kind": _VARIABLE_KIND_MAP[base], "mode": "method" if in_method else "u32"}
    # FIXED_DICT/ARRAY/TUPLE composites land in next tasks
    raise NotImplementedError(f"alias {alias.name} (base {base}) not yet supported")
```

- [ ] **Step 3: Run, commit**

```bash
uv run pytest tests/test_native_descriptor.py -v
git add src/wows_replay_parser/gamedata/native_descriptor.py tests/test_native_descriptor.py
git commit -m "NativeDescriptorBuilder: inline ARRAY + simple aliases + user_type"
```

---

## Task 13: Descriptor builder — FIXED_DICT, ARRAY alias, AllowNone, TUPLE

- [ ] **Step 1: Failing tests**

```python
def test_descriptor_fixed_dict():
    alias = TypeAlias(name="POS_PAIR", base_type="FIXED_DICT",
                      fields=[("x", "FLOAT32"), ("y", "FLOAT32")])
    aliases = AliasRegistry({"POS_PAIR": alias})
    b = NativeDescriptorBuilder(aliases, EntityRegistry({}))
    assert b.descriptor_for_type("POS_PAIR") == {
        "kind": "fixed_dict",
        "fields": [
            {"name": "x", "schema": {"kind": "float32"}},
            {"name": "y", "schema": {"kind": "float32"}},
        ],
    }


def test_descriptor_fixed_dict_allow_none():
    alias = TypeAlias(name="NULL_POS", base_type="FIXED_DICT",
                      fields=[("x", "FLOAT32")], allow_none=True)
    aliases = AliasRegistry({"NULL_POS": alias})
    b = NativeDescriptorBuilder(aliases, EntityRegistry({}))
    assert b.descriptor_for_type("NULL_POS") == {
        "kind": "allow_none",
        "inner": {
            "kind": "fixed_dict",
            "fields": [{"name": "x", "schema": {"kind": "float32"}}],
        },
    }


def test_descriptor_array_alias():
    alias = TypeAlias(name="POS_LIST", base_type="ARRAY", element_type="UINT32")
    aliases = AliasRegistry({"POS_LIST": alias})
    b = NativeDescriptorBuilder(aliases, EntityRegistry({}))
    assert b.descriptor_for_type("POS_LIST") == {
        "kind": "array",
        "count_prefix": "uint8",
        "element": {"kind": "uint32"},
    }
```

- [ ] **Step 2: Implement**

Extend `_descriptor_for_alias`:
```python
if base == "FIXED_DICT":
    inner = {
        "kind": "fixed_dict",
        "fields": [
            {"name": name, "schema": self.descriptor_for_type(t, in_method=in_method)}
            for name, t in alias.fields
        ],
    }
    return {"kind": "allow_none", "inner": inner} if alias.allow_none else inner

if base == "ARRAY" and alias.element_type:
    return {
        "kind": "array",
        "count_prefix": "uint8",
        "element": self.descriptor_for_type(alias.element_type, in_method=in_method),
    }

if base == "TUPLE" and alias.tuple_types:
    return {
        "kind": "tuple",
        "elements": [self.descriptor_for_type(t, in_method=in_method) for t in alias.tuple_types],
    }
```

- [ ] **Step 3: Run, commit**

```bash
uv run pytest tests/test_native_descriptor.py -v
git add src/wows_replay_parser/gamedata/native_descriptor.py tests/test_native_descriptor.py
git commit -m "NativeDescriptorBuilder: FIXED_DICT, ARRAY alias, AllowNone, TUPLE"
```

---

## Task 14: `post_process` (marker conversion + Container wrap)

**Files:**
- Modify: `src/wows_replay_parser/gamedata/native_descriptor.py`
- Append: `tests/test_native_descriptor.py`

- [ ] **Step 1: Failing tests**

```python
import construct as cs
from wows_replay_parser.gamedata.alias_registry import TypeAlias
from wows_replay_parser.gamedata.native_descriptor import post_process


def test_post_process_primitives():
    assert post_process(42) == 42
    assert post_process(b"x") == b"x"
    assert post_process(None) is None


def test_post_process_dict_wraps_container():
    out = post_process({"a": 1, "b": 2})
    assert isinstance(out, cs.Container)
    assert out.a == 1
    assert out.b == 2


def test_post_process_recursive():
    out = post_process({"outer": {"inner": 7}, "list": [{"k": 9}]})
    assert isinstance(out, cs.Container)
    assert isinstance(out.outer, cs.Container)
    assert out.outer.inner == 7
    assert isinstance(out.list[0], cs.Container)
    assert out.list[0].k == 9


def test_post_process_user_type_marker(monkeypatch):
    captured = {}
    fake_alias = TypeAlias(name="ZIPPED_BLOB", base_type="BLOB",
                           implemented_by="X.converter")
    aliases = {"ZIPPED_BLOB": fake_alias}

    def fake_decode_blob(alias, raw):
        captured["alias"] = alias.name
        return {"decoded": raw}

    from wows_replay_parser.gamedata import native_descriptor as nd
    monkeypatch.setattr(nd, "_lookup_alias", lambda name: aliases[name])
    monkeypatch.setattr(nd, "decode_blob", fake_decode_blob)

    raw = {"__alias__": "ZIPPED_BLOB", "__bytes__": b"hello"}
    out = post_process(raw)
    assert captured["alias"] == "ZIPPED_BLOB"
    assert isinstance(out, cs.Container)
    assert out.decoded == b"hello"
```

- [ ] **Step 2: Implement**

```python
import construct as cs

from wows_replay_parser.gamedata.blob_decoders import (
    decode_blob, decode_pickle, decode_zipped,
)


_alias_registry: AliasRegistry | None = None  # set via set_alias_registry()


def set_alias_registry(reg: AliasRegistry) -> None:
    """Install the alias registry used by post_process for USER_TYPE markers."""
    global _alias_registry
    _alias_registry = reg


def _lookup_alias(name: str) -> TypeAlias | None:
    if _alias_registry is None:
        return None
    return _alias_registry.resolve(name)


def post_process(value: Any) -> Any:
    """Walk a Rust-decoded tree, convert markers, wrap dicts in Container."""
    if isinstance(value, dict):
        # USER_TYPE marker
        alias_name = value.get("__alias__")
        if alias_name is not None:
            raw = value["__bytes__"]
            alias = _lookup_alias(alias_name)
            if alias is None:
                return raw  # unknown alias → raw bytes
            decoded = decode_blob(alias, raw)
            return post_process(decoded)
        # auto_pickle marker
        if value.get("__autopickle__"):
            raw = value["__bytes__"]
            if len(raw) >= 2:
                if raw[0] == 0x80:
                    return decode_pickle(raw)
                if raw[0] == 0x78:
                    return decode_zipped(raw)
            return raw
        # plain dict — recurse + wrap
        return cs.Container({k: post_process(v) for k, v in value.items()})
    if isinstance(value, list):
        return [post_process(v) for v in value]
    return value
```

- [ ] **Step 3: Run, commit**

```bash
uv run pytest tests/test_native_descriptor.py -v
git add src/wows_replay_parser/gamedata/native_descriptor.py tests/test_native_descriptor.py
git commit -m "post_process: marker conversion + Container wrap"
```

---

## Task 15: `_NativeSchema` parse-compatible wrapper

**Files:**
- Modify: `src/wows_replay_parser/gamedata/schema_builder.py`
- Append: `tests/test_native_descriptor.py`

- [ ] **Step 1: Failing test**

```python
def test_native_schema_parse_int32():
    from wows_replay_parser.gamedata.schema_builder import _NativeSchema
    import wows_native, struct
    handle = wows_native.compile_schema({"kind": "int32"})
    sch = _NativeSchema(handle)
    assert sch.parse(struct.pack("<i", -7)) == -7


def test_native_schema_parse_fixed_dict_returns_container():
    from wows_replay_parser.gamedata.schema_builder import _NativeSchema
    import wows_native, struct
    handle = wows_native.compile_schema({
        "kind": "fixed_dict",
        "fields": [
            {"name": "x", "schema": {"kind": "float32"}},
            {"name": "id", "schema": {"kind": "uint16"}},
        ],
    })
    sch = _NativeSchema(handle)
    out = sch.parse(struct.pack("<fH", 1.5, 42))
    import construct as cs
    assert isinstance(out, cs.Container)
    assert out.x == 1.5
    assert out.id == 42
```

- [ ] **Step 2: Add `_NativeSchema` to `schema_builder.py`**

Right under the existing native adapter classes, add:
```python
from wows_replay_parser.gamedata.native_descriptor import post_process


class _NativeSchema:
    """Drop-in replacement for a Construct schema. Calls into the Rust
    executor and runs post_process on the result.
    """

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def parse(self, data: bytes) -> Any:
        value, _ = wows_native.decode(self._handle, data, 0)
        return post_process(value)
```

- [ ] **Step 3: Run, commit**

```bash
uv run pytest tests/test_native_descriptor.py -v
git add src/wows_replay_parser/gamedata/schema_builder.py tests/test_native_descriptor.py
git commit -m "_NativeSchema parse-compatible wrapper"
```

---

## Task 16: First production wiring — `build_property_schema` returns native

**Files:**
- Modify: `src/wows_replay_parser/gamedata/schema_builder.py`

- [ ] **Step 1: Wire `build_property_schema` to use native path**

Locate the existing `SchemaBuilder.build_property_schema` (search via `grep -n "def build_property_schema" src/wows_replay_parser/gamedata/schema_builder.py`). Replace its body with:

```python
def build_property_schema(self, entity_type, prop_id):
    prop = self._registry.get_property(entity_type, prop_id)
    if prop is None:
        return None
    builder = NativeDescriptorBuilder(self._aliases, self._registry)
    descriptor = builder.descriptor_for_type(prop.type, in_method=False)
    handle = wows_native.compile_schema(descriptor)
    set_alias_registry(self._aliases)  # for post_process USER_TYPE markers
    return _NativeSchema(handle)
```

Add the import at the top of `schema_builder.py`:
```python
from wows_replay_parser.gamedata.native_descriptor import (
    NativeDescriptorBuilder,
    set_alias_registry,
)
```

- [ ] **Step 2: Run the project test suite**

```bash
uv run pytest tests/ --ignore=tests/fixtures -q
```
Expected: all 117 project tests pass.

If any fail with `NotImplementedError: descriptor for X not yet implemented`, that's a concrete-type gap in `NativeDescriptorBuilder._descriptor_for_alias`. Fix the gap (it's almost always a missing branch in the alias-resolution chain) and re-run.

- [ ] **Step 3: Delete dead Construct code paths in build_property_schema's old body**

Whatever Construct construct it used to return is now unreachable; remove it.

- [ ] **Step 4: Commit**

```bash
git add src/wows_replay_parser/gamedata/schema_builder.py
git commit -m "Wire build_property_schema through Rust executor"
```

---

## Task 17: Wire `build_method_schema` and `build_property_schema_from_def`

- [ ] **Step 1: Repeat the same migration for `build_method_schema`**

Find via `grep -n "def build_method_schema" ...`. The descriptor for a method is a `fixed_dict` of args:

```python
def build_method_schema(self, entity_type, method_id):
    method = self._registry.get_method(entity_type, method_id)
    if method is None:
        return None
    builder = NativeDescriptorBuilder(self._aliases, self._registry)
    descriptor = {
        "kind": "fixed_dict",
        "fields": [
            {"name": arg.name, "schema": builder.descriptor_for_type(arg.type, in_method=True)}
            for arg in method.args
        ],
    }
    handle = wows_native.compile_schema(descriptor)
    set_alias_registry(self._aliases)
    return _NativeSchema(handle)
```

- [ ] **Step 2: Same for `build_method_schema_from_def`**

```python
def build_method_schema_from_def(self, method):
    if not method.args:
        # Empty descriptor — emit an empty fixed_dict
        descriptor = {"kind": "fixed_dict", "fields": []}
    else:
        builder = NativeDescriptorBuilder(self._aliases, self._registry)
        descriptor = {
            "kind": "fixed_dict",
            "fields": [
                {"name": arg.name, "schema": builder.descriptor_for_type(arg.type, in_method=True)}
                for arg in method.args
            ],
        }
    return _NativeSchema(wows_native.compile_schema(descriptor))
```

- [ ] **Step 3: Run, commit**

```bash
uv run pytest tests/ --ignore=tests/fixtures -q
```
Expected: 117 pass. Fix any descriptor-builder gaps that surface.

```bash
git add src/wows_replay_parser/gamedata/schema_builder.py
git commit -m "Wire build_method_schema + build_method_schema_from_def through Rust executor"
```

---

## Task 18: Wire inline ENTITY_CREATE state

The `_try_parse_inline_state` path uses property schemas, which Task 16 already migrated. But it also uses some inline construct logic. Locate via `grep -n "_try_parse_inline_state\|_parse_inline_state" src/wows_replay_parser/packets/decoder.py` and confirm every `cs.parse` / `cs.Construct` reference there now goes through `_NativeSchema` (it should, since they all originate in `SchemaBuilder.build_property_schema`).

- [ ] **Step 1: Run full test suite, check inline-state path**

```bash
uv run pytest tests/ --ignore=tests/fixtures -v -k "entity_create or inline_state"
```
Expected: green.

- [ ] **Step 2: If anything fails, fix the descriptor builder**

Most likely cause: an alias type the inline-state code path encounters that wasn't covered by property-schema tests. The `NotImplementedError` will name it.

- [ ] **Step 3: Commit if any fixes**

```bash
git add -u
git commit -m "Inline ENTITY_CREATE state: descriptor coverage fixes"
```

---

## Task 19: End-to-end benchmark — record post-Task-18 number

- [ ] **Step 1: Run 10-iter bench**

```bash
uv run python -c "
import time, gc, statistics
from wows_replay_parser.api import parse_replay
REPLAY = '/home/toalba/projects/wows/wows-renderer/20260322_172639_PHSC710-Prins-Van-Oranje_56_AngelWings.wowsreplay'
GAMEDATA = '/home/toalba/projects/wows/wows-renderer/wows-gamedata/data/scripts_entity/entity_defs'
parse_replay(REPLAY, GAMEDATA)
times = []
for _ in range(10):
    gc.collect()
    t0 = time.perf_counter()
    parse_replay(REPLAY, GAMEDATA)
    times.append(time.perf_counter() - t0)
print(f'min={min(times)*1000:.1f} median={statistics.median(times)*1000:.1f} mean={statistics.mean(times)*1000:.1f}')
"
```

- [ ] **Step 2: Append result to design doc + commit**

Add an appendix to `docs/superpowers/specs/2026-04-30-rust-schema-executor-design.md`:

```markdown
## Benchmark log

- Pre-port baseline (median): 4058 ms
- After Task 18 (median): <number from above> ms
```

```bash
git add docs/superpowers/specs/2026-04-30-rust-schema-executor-design.md
git commit -m "Bench: post-executor-wiring numbers"
```

---

## Task 20: Cleanup — delete dead Construct helpers

**Files:**
- Modify: `src/wows_replay_parser/gamedata/schema_builder.py`

- [ ] **Step 1: Identify dead helpers**

These Construct adapter classes are no longer used by production code (verify via `grep -rn`):
- `_NativeFixed`, `_NativeVector`, `_NativeVarLen`, `_NativeArrayPrimitive`
- `_AllowNone`, `_DecodedBlob`, `_AutoPickleBlob`, `_RobustString`, `_MethodBlobPrefixed`
- The `FIXED_PRIMITIVES` dict
- `_BULK_ARRAY_DECODERS`
- The `_make_blob_construct`, `_bulk_array_decoder` methods on `SchemaBuilder`
- `_resolve_type`, `_resolve_alias` (now subsumed by `NativeDescriptorBuilder`)

Anything still imported by tests (e.g. `tests/test_chat.py` imports `_decode_string_bytes`, `_RobustString`, `_MethodBlobPrefixed`) needs care: either keep the helper definitions in `schema_builder.py`, or migrate the test to use `wows_native.decode_string` / `post_process` directly.

- [ ] **Step 2: For each dead helper, verify zero uses then delete**

```bash
grep -rn "_NativeFixed\|_NativeVector\|_NativeVarLen\|_NativeArrayPrimitive" src/ tests/ native/tests/
```

If only `schema_builder.py` references them, delete the class definitions and their references. Run `uv run pytest tests/ native/tests/ --ignore=tests/fixtures` after each batch of deletions.

- [ ] **Step 3: Migrate `tests/test_chat.py` if needed**

If the chat test still imports `_decode_string_bytes` etc., either:

(a) keep `_decode_string_bytes` as a thin wrapper around `wows_native.decode_string`'s logic (simpler), OR

(b) migrate the chat test to test the wire-decoded result through the full pipeline.

(a) is faster. Add this to `schema_builder.py`:
```python
def _decode_string_bytes(raw: bytes) -> str:
    """Tolerant str decode (utf-8 → latin-1 fallback, NUL strip).
    Preserved for tests/test_chat.py; production goes through wows_native.
    """
    if not isinstance(raw, (bytes, bytearray)):
        return raw  # type: ignore[return-value]
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        text = bytes(raw).decode("latin-1")
    return text.replace("\x00", "")
```

- [ ] **Step 4: Final test run, commit**

```bash
uv run pytest tests/ native/tests/ --ignore=tests/fixtures -q
```
Expected: all 1099+ tests green.

```bash
git add src/wows_replay_parser/gamedata/schema_builder.py
git commit -m "Cleanup: delete dead Construct helpers, executor is canonical"
```

---

## Task 21: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the schema-builder paragraph**

Find the `## Architecture / Data Flow` block. Update step 5 to:

> 5. → `SchemaBuilder` produces `wows_native` schema descriptors which are compiled to opaque `SchemaHandle` objects. The Rust executor in `wows_native` walks these handles to decode method args, property values, and inline ENTITY_CREATE state. A Python `post_process` sweep wraps results in `cs.Container` (for `.field` access) and converts USER_TYPE / auto-pickle markers via `gamedata/blob_decoders.py`.

Update the auto-detector paragraph to reflect that `auto_detect_methods` defaults to `False` (already the case) and the deterministic ordering covers Avatar/Vehicle.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "CLAUDE.md: document Rust schema executor as production decoder"
```

---

## Task 22: Final benchmark + memory update

- [ ] **Step 1: Run 10-iter bench (release-native build)**

```bash
cd native && RUSTFLAGS="-C target-cpu=native" uv run --project .. maturin develop --profile release-native
cd ..
uv run python -c "<same bench as Task 19>"
```

- [ ] **Step 2: Append result to design doc benchmark log**

Update the appendix:
```markdown
- Final (median): <number> ms (Δ from baseline: -X%)
```

- [ ] **Step 3: Update memory file**

Edit `/home/toalba/.claude/projects/-home-toalba-projects-wows/memory/project_rust_port.md`:
- Replace the "What's wired and shipped" section with: "Full schema executor in Rust. Construct removed from production hot path. <X>% e2e speedup vs pre-port."
- Replace the "Why no FIXED_DICT bulk decode" reasoning — now done.
- Add benchmark numbers.

- [ ] **Step 4: Final commit**

```bash
git add docs/superpowers/specs/2026-04-30-rust-schema-executor-design.md
git commit -m "Final benchmark + design doc update"
```

- [ ] **Step 5: Push**

```bash
git push origin decode-rs
```

---

## Self-review

**Spec coverage check:**
- ✅ Path C (full recursive executor): Tasks 2-10 build the executor; Tasks 16-18 wire it.
- ✅ USER_TYPE / auto-pickle markers: Task 9 + Task 14 (post_process).
- ✅ Schema descriptor flow: Tasks 11-13 build `NativeDescriptorBuilder`.
- ✅ `cs.Container` wrap during post-walk: Task 14.
- ✅ Typed `DecodeError` → `PyErr`: Task 1.
- ✅ All SchemaBuilder outputs covered: Tasks 16, 17, 18.
- ✅ Invasive rollout, no flag: each wiring task replaces Construct in place.
- ✅ Existing test suite as contract: every wiring task ends with full-suite run.
- ✅ Phase 6 (ARRAY incl. ARRAY<FIXED_DICT>): Task 8 + Task 13 array-alias branch.
- ✅ Phase 11 cleanup: Task 20.
- ✅ CLAUDE.md update: Task 21.
- ✅ Final bench / memory: Task 22.

**Placeholder scan:** all code blocks contain real code; no "TODO" or "implement later".

**Type consistency:** `Schema` enum variants and `compile_schema` match arms align across tasks. `_NativeSchema.parse(bytes)` mirrors Construct's API exactly so call sites in `decoder.py` don't change. `post_process` is the single conversion point.

Plan is complete. Saved to `docs/superpowers/plans/2026-04-30-rust-schema-executor.md`.
