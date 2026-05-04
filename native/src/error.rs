use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[allow(dead_code)]
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
