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
