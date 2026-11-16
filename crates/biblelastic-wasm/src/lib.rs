//! The engine as a WebAssembly module. It must run in a web worker, because it reads module files
//! synchronously (from the browser's Origin Private File System). `web/engine-worker.js` is the other half.
//!
//! The host provides one function, `storage_read`, and calls:
//! - `allocate` / `release`, to pass text in
//! - `add_module`, once for each installed module file (and `clear_modules` before starting again)
//! - `set_cache_bytes`, to limit how much of the modules is kept in memory
//! - `request`, with a request for `biblelastic_engine::api`. It returns a pointer to a 4-byte length
//!   and then that many bytes of JSON: `{"bytesRead": …, "cachedBytes": …, "response": {…}}`. That's valid until the next call.

#![cfg(target_arch = "wasm32")]

use std::cell::RefCell;

use biblelastic_engine::api;
use std::rc::Rc;

use biblelastic_engine::format::{Module, PageCache, Result, Storage, DEFAULT_CACHE_BYTES};
use biblelastic_engine::library::{Library, ModuleSource};

#[link(wasm_import_module = "biblelastic")]
extern "C" {
    /// Copy `length` bytes at `offset` of an open file to `pointer`, and return how many were copied.
    /// (The offset is a float so that JavaScript doesn't need BigInt: exact up to 2^53.)
    fn storage_read(file: u32, offset: f64, pointer: *mut u8, length: u32) -> u32;
}

struct File(u32);

impl Storage for File {
    fn read_at(&self, offset: u64, length: usize) -> Result<Vec<u8>> {
        let mut data = vec![0; length];
        let read = unsafe { storage_read(self.0, offset as f64, data.as_mut_ptr(), length as u32) };
        if read as usize != length { return Err(format!("only {read} of {length} bytes could be read at {offset}").into()); }
        Ok(data)
    }
}

struct Files(Vec<(String, u32)>);

impl ModuleSource for Files {
    fn names(&self) -> Result<Vec<String>> { Ok(self.0.iter().map(|(name, _)| name.clone()).collect()) }
    fn open(&self, name: &str, cache: &Rc<PageCache>) -> Result<Module> {
        let file = self.0.iter().find(|(known, _)| known == name).ok_or_else(|| format!("no module '{name}'"))?.1;
        Module::open_with(Box::new(File(file)), cache)
    }
}

#[derive(Default)]
struct State {
    files: Vec<(String, u32)>,
    /// Opened at the first request, then kept so that what's been read stays cached
    library: Option<Library>,
    response: Vec<u8>,
    /// How much of the modules may be kept in memory (0: the default)
    cache_bytes: usize,
}

thread_local! { static STATE: RefCell<State> = RefCell::default(); }

#[no_mangle]
pub extern "C" fn allocate(length: u32) -> *mut u8 {
    let mut buffer = Vec::<u8>::with_capacity(length as usize);
    let pointer = buffer.as_mut_ptr();
    std::mem::forget(buffer);
    pointer
}

/// # Safety
/// `pointer` must have come from `allocate(length)`.
#[no_mangle]
pub unsafe extern "C" fn release(pointer: *mut u8, length: u32) { drop(Vec::from_raw_parts(pointer, 0, length as usize)); }

unsafe fn text<'a>(pointer: *const u8, length: u32) -> &'a str {
    std::str::from_utf8(std::slice::from_raw_parts(pointer, length as usize)).unwrap_or("")
}

/// # Safety
/// `pointer` and `length` must describe the module's name (without `.blm`) in UTF-8.
#[no_mangle]
pub unsafe extern "C" fn add_module(pointer: *const u8, length: u32, file: u32) {
    let name = text(pointer, length).to_string();
    STATE.with_borrow_mut(|state| { state.files.push((name, file)); state.library = None; });
}

/// Takes effect the next time the modules are opened
#[no_mangle]
pub extern "C" fn set_cache_bytes(bytes: u32) { STATE.with_borrow_mut(|state| { state.cache_bytes = bytes as usize; state.library = None; }); }

#[no_mangle]
pub extern "C" fn clear_modules() { STATE.with_borrow_mut(|state| { state.files.clear(); state.library = None; }); }

/// # Safety
/// `pointer` and `length` must describe the request in UTF-8.
#[no_mangle]
pub unsafe extern "C" fn request(pointer: *const u8, length: u32) -> *const u8 {
    let request = text(pointer, length);
    STATE.with_borrow_mut(|state| {
        if request.trim() == "command=forget" { state.library = None; } // Drops everything that's cached (to measure a cold start)
        let mut before = 0;
        let json = match &state.library {
            Some(library) => { before = library.bytes_read(); Ok(()) }
            None => Library::open_with(&Files(state.files.clone()), if state.cache_bytes > 0 { state.cache_bytes } else { DEFAULT_CACHE_BYTES }).map(|library| state.library = Some(library)),
        };
        let json = match (json, &state.library) {
            (Ok(()), Some(library)) if request.trim() == "command=forget" => format!("{{\"bytesRead\":{},\"response\":{{\"ok\":true}}}}", library.bytes_read()),
            (Ok(()), Some(library)) => {
                let response = api::respond(library, request);
                format!("{{\"bytesRead\":{},\"cachedBytes\":{},\"response\":{response}}}", library.bytes_read() - before, library.cache.bytes())
            }
            (Err(error), _) => format!("{{\"bytesRead\":0,\"response\":{{\"ok\":false,\"error\":{}}}}}", api::quote(&error.to_string())),
            (Ok(()), None) => unreachable!(),
        };
        state.response = (json.len() as u32).to_le_bytes().into_iter().chain(json.bytes()).collect();
        state.response.as_ptr()
    })
}
