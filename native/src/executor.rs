use pyo3::prelude::*;
use pyo3::types::PyBytes;

use crate::error::DecodeError;
use crate::schema::{LengthMode, PySchema, Schema};
use crate::value::Value;

fn slice_at<'a>(buf: &'a [u8], offset: usize, size: usize) -> Result<&'a [u8], DecodeError> {
    buf.get(offset..offset + size).ok_or(DecodeError::BufferUnderrun {
        offset, need: size, have: buf.len(),
    })
}

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

pub fn decode_value(schema: &Schema, buf: &[u8], offset: usize) -> Result<(Value, usize), DecodeError> {
    match schema {
        Schema::Int8 => {
            let c = slice_at(buf, offset, 1)?;
            Ok((Value::Int(i8::from_le_bytes(c.try_into().unwrap()) as i64), offset + 1))
        }
        Schema::Int16 => {
            let c = slice_at(buf, offset, 2)?;
            Ok((Value::Int(i16::from_le_bytes(c.try_into().unwrap()) as i64), offset + 2))
        }
        Schema::Int32 => {
            let c = slice_at(buf, offset, 4)?;
            Ok((Value::Int(i32::from_le_bytes(c.try_into().unwrap()) as i64), offset + 4))
        }
        Schema::Int64 => {
            let c = slice_at(buf, offset, 8)?;
            Ok((Value::Int(i64::from_le_bytes(c.try_into().unwrap())), offset + 8))
        }
        Schema::UInt8 => {
            let c = slice_at(buf, offset, 1)?;
            Ok((Value::UInt(c[0] as u64), offset + 1))
        }
        Schema::UInt16 => {
            let c = slice_at(buf, offset, 2)?;
            Ok((Value::UInt(u16::from_le_bytes(c.try_into().unwrap()) as u64), offset + 2))
        }
        Schema::UInt32 => {
            let c = slice_at(buf, offset, 4)?;
            Ok((Value::UInt(u32::from_le_bytes(c.try_into().unwrap()) as u64), offset + 4))
        }
        Schema::UInt64 => {
            let c = slice_at(buf, offset, 8)?;
            Ok((Value::UInt(u64::from_le_bytes(c.try_into().unwrap())), offset + 8))
        }
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
        Schema::AllowNone(inner) => {
            let flag = slice_at(buf, offset, 1)?[0];
            if flag == 0 {
                Ok((Value::None, offset + 1))
            } else {
                decode_value(inner, buf, offset + 1)
            }
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
