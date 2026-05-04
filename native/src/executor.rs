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
