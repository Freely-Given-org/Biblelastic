//! The Biblelastic engine: reads compiled modules and answers queries.
//!
//! It has one small dependency (a zstd decoder) and never needs a whole module in memory (except the model for meaning-based search,
//! once that's asked for), so that it can run on low-end phones and (compiled to WebAssembly) in browsers.

pub mod api;
pub mod format;
pub mod library;
pub mod meaning;
pub mod query;
pub mod reference;
