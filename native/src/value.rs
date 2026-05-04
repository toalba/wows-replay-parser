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
    UserTypeMarker { alias: String, bytes: Vec<u8> },
    AutoPickleMarker(Vec<u8>),
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
            Value::UserTypeMarker { alias, bytes } => {
                let d = PyDict::new_bound(py);
                d.set_item("__alias__", alias)?;
                d.set_item("__bytes__", pyo3::types::PyBytes::new_bound(py, bytes))?;
                d.into_py(py)
            }
            Value::AutoPickleMarker(bytes) => {
                let d = PyDict::new_bound(py);
                d.set_item("__autopickle__", true)?;
                d.set_item("__bytes__", pyo3::types::PyBytes::new_bound(py, bytes))?;
                d.into_py(py)
            }
        })
    }
}
