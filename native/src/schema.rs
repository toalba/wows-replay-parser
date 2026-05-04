use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

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
    FixedDict { fields: Vec<(String, Schema)> },
    AllowNone(Box<Schema>),
}

#[pyclass(name = "Schema", module = "wows_native")]
pub struct PySchema {
    pub schema: Schema,
}

/// Recursive descriptor compilation. Used both by the top-level
/// compile_schema entry point and by nested fixed_dict / array fields.
pub fn schema_from_dict(d: &Bound<'_, PyDict>) -> Result<Schema, DecodeError> {
    let kind: String = d.get_item("kind").ok().flatten()
        .ok_or_else(|| DecodeError::InvalidDescriptor("missing kind".into()))?
        .extract()
        .map_err(|_| DecodeError::InvalidDescriptor("kind must be string".into()))?;
    match kind.as_str() {
        "int8" => Ok(Schema::Int8),
        "int16" => Ok(Schema::Int16),
        "int32" => Ok(Schema::Int32),
        "int64" => Ok(Schema::Int64),
        "uint8" => Ok(Schema::UInt8),
        "uint16" => Ok(Schema::UInt16),
        "uint32" => Ok(Schema::UInt32),
        "uint64" => Ok(Schema::UInt64),
        "float32" | "float" => Ok(Schema::Float32),
        "float64" => Ok(Schema::Float64),
        "bool" => Ok(Schema::Bool),
        "mailbox" => Ok(Schema::Mailbox),
        "vector2" => Ok(Schema::Vector2),
        "vector3" => Ok(Schema::Vector3),
        "blob" | "python" | "string" | "unicode_string" => {
            let mode_str: String = d.get_item("mode").ok().flatten()
                .ok_or_else(|| DecodeError::InvalidDescriptor("missing mode".into()))?
                .extract()
                .map_err(|_| DecodeError::InvalidDescriptor("mode must be string".into()))?;
            let mode = LengthMode::parse(&mode_str)?;
            Ok(match kind.as_str() {
                "blob"           => Schema::Blob(mode),
                "python"         => Schema::Python(mode),
                "string"         => Schema::Str(mode),
                "unicode_string" => Schema::UnicodeStr(mode),
                _ => unreachable!(),
            })
        }
        "fixed_dict" => {
            let fields_obj = d.get_item("fields").ok().flatten()
                .ok_or_else(|| DecodeError::InvalidDescriptor("fixed_dict missing fields".into()))?;
            let fields_list = fields_obj.downcast::<PyList>()
                .map_err(|_| DecodeError::InvalidDescriptor("fields must be list".into()))?;
            let mut out = Vec::with_capacity(fields_list.len());
            for item in fields_list.iter() {
                let item_dict = item.downcast::<PyDict>()
                    .map_err(|_| DecodeError::InvalidDescriptor("field must be dict".into()))?;
                let name: String = item_dict.get_item("name").ok().flatten()
                    .ok_or_else(|| DecodeError::InvalidDescriptor("field missing name".into()))?
                    .extract()
                    .map_err(|_| DecodeError::InvalidDescriptor("field name must be string".into()))?;
                let sub_dict_obj = item_dict.get_item("schema").ok().flatten()
                    .ok_or_else(|| DecodeError::InvalidDescriptor("field missing schema".into()))?;
                let sub_dict = sub_dict_obj.downcast::<PyDict>()
                    .map_err(|_| DecodeError::InvalidDescriptor("field schema must be dict".into()))?;
                let sub = schema_from_dict(sub_dict)?;
                out.push((name, sub));
            }
            Ok(Schema::FixedDict { fields: out })
        }
        "allow_none" => {
            let inner_obj = d.get_item("inner").ok().flatten()
                .ok_or_else(|| DecodeError::InvalidDescriptor("allow_none missing inner".into()))?;
            let inner_dict = inner_obj.downcast::<PyDict>()
                .map_err(|_| DecodeError::InvalidDescriptor("allow_none inner must be dict".into()))?;
            let inner = schema_from_dict(inner_dict)?;
            Ok(Schema::AllowNone(Box::new(inner)))
        }
        other => Err(DecodeError::InvalidDescriptor(format!("unknown kind {other:?}"))),
    }
}

#[pyfunction]
pub fn compile_schema(descriptor: &Bound<'_, PyDict>) -> PyResult<PySchema> {
    Ok(PySchema { schema: schema_from_dict(descriptor)? })
}
