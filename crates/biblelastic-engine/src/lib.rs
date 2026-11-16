//! The Biblelastic engine: reads compiled modules and answers queries.
//!
//! It has one small dependency (a zstd decoder) and never needs a whole module in memory, so that it can run
//! on low-end phones and (compiled to WebAssembly) in browsers.

pub mod api;
pub mod format;
pub mod library;
pub mod query;
