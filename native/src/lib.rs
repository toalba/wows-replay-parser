mod error;
mod schema;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

#[inline]
fn slice_at<'a>(data: &'a [u8], offset: usize, size: usize) -> PyResult<&'a [u8]> {
    data.get(offset..offset + size).ok_or_else(|| {
        PyValueError::new_err(format!(
            "buffer underrun: need {size} byte(s) at offset {offset}, have {}",
            data.len()
        ))
    })
}

macro_rules! decode_fixed_le {
    ($name:ident, $ty:ty) => {
        #[pyfunction]
        fn $name(data: &Bound<'_, PyBytes>, offset: usize) -> PyResult<($ty, usize)> {
            const SIZE: usize = std::mem::size_of::<$ty>();
            let buf = data.as_bytes();
            let chunk = slice_at(buf, offset, SIZE)?;
            let value = <$ty>::from_le_bytes(chunk.try_into().unwrap());
            Ok((value, offset + SIZE))
        }
    };
}

decode_fixed_le!(decode_int8, i8);
decode_fixed_le!(decode_uint8, u8);
decode_fixed_le!(decode_int16, i16);
decode_fixed_le!(decode_uint16, u16);
decode_fixed_le!(decode_int32, i32);
decode_fixed_le!(decode_uint32, u32);
decode_fixed_le!(decode_int64, i64);
decode_fixed_le!(decode_uint64, u64);
decode_fixed_le!(decode_float32, f32);
decode_fixed_le!(decode_float64, f64);

// ── Bulk ARRAY decoders ───────────────────────────────────────────────
//
// BigWorld ARRAY wire format: u8 count + count × element. Each ``decode_
// array_<primitive>`` reads the count, validates the buffer, and decodes
// every element in one Rust call — replacing Construct's per-element
// Python loop. The cost of a Python→Rust hop is amortized over the whole
// array instead of paid per element.

macro_rules! decode_array_le {
    ($name:ident, $ty:ty) => {
        #[pyfunction]
        fn $name(data: &Bound<'_, PyBytes>, offset: usize) -> PyResult<(Vec<$ty>, usize)> {
            const SIZE: usize = std::mem::size_of::<$ty>();
            let buf = data.as_bytes();
            let count = slice_at(buf, offset, 1)?[0] as usize;
            let payload_start = offset + 1;
            let payload = slice_at(buf, payload_start, count * SIZE)?;
            let mut out = Vec::with_capacity(count);
            for chunk in payload.chunks_exact(SIZE) {
                out.push(<$ty>::from_le_bytes(chunk.try_into().unwrap()));
            }
            Ok((out, payload_start + count * SIZE))
        }
    };
}

decode_array_le!(decode_array_int8, i8);
decode_array_le!(decode_array_uint8, u8);
decode_array_le!(decode_array_int16, i16);
decode_array_le!(decode_array_uint16, u16);
decode_array_le!(decode_array_int32, i32);
decode_array_le!(decode_array_uint32, u32);
decode_array_le!(decode_array_int64, i64);
decode_array_le!(decode_array_uint64, u64);
decode_array_le!(decode_array_float32, f32);
decode_array_le!(decode_array_float64, f64);

#[pyfunction]
fn decode_array_bool(data: &Bound<'_, PyBytes>, offset: usize) -> PyResult<(Vec<bool>, usize)> {
    let buf = data.as_bytes();
    let count = slice_at(buf, offset, 1)?[0] as usize;
    let payload_start = offset + 1;
    let payload = slice_at(buf, payload_start, count)?;
    let out: Vec<bool> = payload.iter().map(|&b| b != 0).collect();
    Ok((out, payload_start + count))
}

#[pyfunction]
fn decode_array_vector2(
    data: &Bound<'_, PyBytes>,
    offset: usize,
) -> PyResult<(Vec<(f32, f32)>, usize)> {
    const SIZE: usize = 8;
    let buf = data.as_bytes();
    let count = slice_at(buf, offset, 1)?[0] as usize;
    let payload_start = offset + 1;
    let payload = slice_at(buf, payload_start, count * SIZE)?;
    let mut out = Vec::with_capacity(count);
    for chunk in payload.chunks_exact(SIZE) {
        let x = f32::from_le_bytes(chunk[0..4].try_into().unwrap());
        let y = f32::from_le_bytes(chunk[4..8].try_into().unwrap());
        out.push((x, y));
    }
    Ok((out, payload_start + count * SIZE))
}

#[pyfunction]
fn decode_array_vector3(
    data: &Bound<'_, PyBytes>,
    offset: usize,
) -> PyResult<(Vec<(f32, f32, f32)>, usize)> {
    const SIZE: usize = 12;
    let buf = data.as_bytes();
    let count = slice_at(buf, offset, 1)?[0] as usize;
    let payload_start = offset + 1;
    let payload = slice_at(buf, payload_start, count * SIZE)?;
    let mut out = Vec::with_capacity(count);
    for chunk in payload.chunks_exact(SIZE) {
        let x = f32::from_le_bytes(chunk[0..4].try_into().unwrap());
        let y = f32::from_le_bytes(chunk[4..8].try_into().unwrap());
        let z = f32::from_le_bytes(chunk[8..12].try_into().unwrap());
        out.push((x, y, z));
    }
    Ok((out, payload_start + count * SIZE))
}

#[pyfunction]
fn decode_bool(data: &Bound<'_, PyBytes>, offset: usize) -> PyResult<(bool, usize)> {
    let buf = data.as_bytes();
    let chunk = slice_at(buf, offset, 1)?;
    Ok((chunk[0] != 0, offset + 1))
}

#[pyfunction]
fn decode_mailbox<'py>(
    py: Python<'py>,
    data: &Bound<'py, PyBytes>,
    offset: usize,
) -> PyResult<(Bound<'py, PyBytes>, usize)> {
    const SIZE: usize = 16;
    let buf = data.as_bytes();
    let chunk = slice_at(buf, offset, SIZE)?;
    Ok((PyBytes::new_bound(py, chunk), offset + SIZE))
}

#[pyfunction]
fn decode_vector2(data: &Bound<'_, PyBytes>, offset: usize) -> PyResult<((f32, f32), usize)> {
    const SIZE: usize = 8;
    let buf = data.as_bytes();
    let chunk = slice_at(buf, offset, SIZE)?;
    let x = f32::from_le_bytes(chunk[0..4].try_into().unwrap());
    let y = f32::from_le_bytes(chunk[4..8].try_into().unwrap());
    Ok(((x, y), offset + SIZE))
}

#[pyfunction]
fn decode_vector3(
    data: &Bound<'_, PyBytes>,
    offset: usize,
) -> PyResult<((f32, f32, f32), usize)> {
    const SIZE: usize = 12;
    let buf = data.as_bytes();
    let chunk = slice_at(buf, offset, SIZE)?;
    let x = f32::from_le_bytes(chunk[0..4].try_into().unwrap());
    let y = f32::from_le_bytes(chunk[4..8].try_into().unwrap());
    let z = f32::from_le_bytes(chunk[8..12].try_into().unwrap());
    Ok(((x, y, z), offset + SIZE))
}

// ── Variable-length primitives ────────────────────────────────────────
//
// BigWorld length-prefix encodings:
//
// "method" (inside ENTITY_METHOD payloads):
//     u8 length. If 0xFF then u16 LE length followed by 1 padding byte.
//
// "u32"   (property updates and inline state):
//     u32 LE length.

#[derive(Copy, Clone)]
enum LengthMode {
    Method,
    U32,
}

impl LengthMode {
    fn parse(s: &str) -> PyResult<Self> {
        match s {
            "method" => Ok(LengthMode::Method),
            "u32" => Ok(LengthMode::U32),
            other => Err(PyValueError::new_err(format!(
                "unknown length-prefix mode {other:?}; expected 'method' or 'u32'"
            ))),
        }
    }
}

/// Read a length prefix according to *mode* and return the payload's
/// (length, payload_start_offset).
fn read_length_prefix(buf: &[u8], offset: usize, mode: LengthMode) -> PyResult<(usize, usize)> {
    match mode {
        LengthMode::Method => {
            let first = slice_at(buf, offset, 1)?[0];
            if first < 0xFF {
                Ok((first as usize, offset + 1))
            } else {
                let len_bytes = slice_at(buf, offset + 1, 2)?;
                let length = u16::from_le_bytes(len_bytes.try_into().unwrap()) as usize;
                // u8 sentinel + u16 length + 1 padding byte
                slice_at(buf, offset + 3, 1)?; // verify padding byte exists
                Ok((length, offset + 4))
            }
        }
        LengthMode::U32 => {
            let len_bytes = slice_at(buf, offset, 4)?;
            let length = u32::from_le_bytes(len_bytes.try_into().unwrap()) as usize;
            Ok((length, offset + 4))
        }
    }
}

fn read_var_payload<'a>(
    buf: &'a [u8],
    offset: usize,
    mode: LengthMode,
) -> PyResult<(&'a [u8], usize)> {
    let (length, payload_start) = read_length_prefix(buf, offset, mode)?;
    let payload = slice_at(buf, payload_start, length)?;
    Ok((payload, payload_start + length))
}

#[pyfunction]
fn decode_blob<'py>(
    py: Python<'py>,
    data: &Bound<'py, PyBytes>,
    offset: usize,
    mode: &str,
) -> PyResult<(Bound<'py, PyBytes>, usize)> {
    let mode = LengthMode::parse(mode)?;
    let buf = data.as_bytes();
    let (payload, end) = read_var_payload(buf, offset, mode)?;
    Ok((PyBytes::new_bound(py, payload), end))
}

#[pyfunction]
fn decode_python<'py>(
    py: Python<'py>,
    data: &Bound<'py, PyBytes>,
    offset: usize,
    mode: &str,
) -> PyResult<(Bound<'py, PyBytes>, usize)> {
    decode_blob(py, data, offset, mode)
}

/// Tolerant UTF-8 → str decode that mirrors `_decode_string_bytes` in
/// `schema_builder.py`: try strict UTF-8, fall back to latin-1 (1:1
/// byte-to-codepoint, never raises), strip embedded NULs.
fn decode_string_bytes(payload: &[u8]) -> String {
    let text = match std::str::from_utf8(payload) {
        Ok(s) => s.to_owned(),
        Err(_) => payload.iter().map(|&b| b as char).collect(),
    };
    if text.contains('\0') {
        text.replace('\0', "")
    } else {
        text
    }
}

#[pyfunction]
fn decode_string(
    data: &Bound<'_, PyBytes>,
    offset: usize,
    mode: &str,
) -> PyResult<(String, usize)> {
    let mode = LengthMode::parse(mode)?;
    let buf = data.as_bytes();
    let (payload, end) = read_var_payload(buf, offset, mode)?;
    Ok((decode_string_bytes(payload), end))
}

#[pyfunction]
fn decode_unicode_string(
    data: &Bound<'_, PyBytes>,
    offset: usize,
    mode: &str,
) -> PyResult<(String, usize)> {
    decode_string(data, offset, mode)
}

#[pymodule]
fn wows_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decode_int8, m)?)?;
    m.add_function(wrap_pyfunction!(decode_uint8, m)?)?;
    m.add_function(wrap_pyfunction!(decode_int16, m)?)?;
    m.add_function(wrap_pyfunction!(decode_uint16, m)?)?;
    m.add_function(wrap_pyfunction!(decode_int32, m)?)?;
    m.add_function(wrap_pyfunction!(decode_uint32, m)?)?;
    m.add_function(wrap_pyfunction!(decode_int64, m)?)?;
    m.add_function(wrap_pyfunction!(decode_uint64, m)?)?;
    m.add_function(wrap_pyfunction!(decode_float32, m)?)?;
    m.add_function(wrap_pyfunction!(decode_float64, m)?)?;
    m.add_function(wrap_pyfunction!(decode_bool, m)?)?;
    m.add_function(wrap_pyfunction!(decode_mailbox, m)?)?;
    m.add_function(wrap_pyfunction!(decode_vector2, m)?)?;
    m.add_function(wrap_pyfunction!(decode_vector3, m)?)?;
    m.add_function(wrap_pyfunction!(decode_blob, m)?)?;
    m.add_function(wrap_pyfunction!(decode_python, m)?)?;
    m.add_function(wrap_pyfunction!(decode_string, m)?)?;
    m.add_function(wrap_pyfunction!(decode_unicode_string, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_int8, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_uint8, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_int16, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_uint16, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_int32, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_uint32, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_int64, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_uint64, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_float32, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_float64, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_bool, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_vector2, m)?)?;
    m.add_function(wrap_pyfunction!(decode_array_vector3, m)?)?;
    m.add_function(wrap_pyfunction!(schema::compile_schema, m)?)?;
    m.add_class::<schema::PySchema>()?;
    Ok(())
}
