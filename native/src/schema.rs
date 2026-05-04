use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::error::DecodeError;

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
    Int8, Int16, Int32, Int64,
    UInt8, UInt16, UInt32, UInt64,
    Float32, Float64,
    Bool,
    Mailbox,
    Vector2, Vector3,
    Blob(LengthMode),
    Python(LengthMode),
    Str(LengthMode),
    UnicodeStr(LengthMode),
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
            other => Err(DecodeError::InvalidDescriptor(format!("unknown kind {other:?}"))),
        }
    }
}

#[pyfunction]
pub fn compile_schema(descriptor: &Bound<'_, PyDict>) -> PyResult<PySchema> {
    Ok(PySchema::from_descriptor(descriptor)?)
}
