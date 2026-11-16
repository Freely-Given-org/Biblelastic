//! The engine as a native library (`libbiblelastic.so` etc.) with a C interface, for apps to call (e.g., from Dart).
//!
//! There are two functions:
//! - `biblelastic_request(folder, request, cache_bytes)` answers a request for `biblelastic_engine::api` from the modules in a folder.
//!   It returns JSON text: `{"bytesRead": …, "cachedBytes": …, "response": {…}}`, which the caller must give back to
//! - `biblelastic_free(text)`.
//!
//! The opened modules are kept (for each thread) until a request names a different folder, or is `command=forget`
//! (which an app must send after it adds or removes module files). Always call from the same thread, to keep what's been read.

use std::cell::RefCell;
use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::PathBuf;

use biblelastic_engine::api;
use biblelastic_engine::format::DEFAULT_CACHE_BYTES;
use biblelastic_engine::library::{Folder, Library};

thread_local! { static OPENED: RefCell<Option<(PathBuf, Library)>> = const { RefCell::new(None) }; }

fn answer(folder: &str, request: &str, cache_bytes: usize) -> String {
    OPENED.with(|opened| {
        let mut opened = opened.borrow_mut();
        let folder = PathBuf::from(folder);
        if request.lines().any(|line| line.trim() == "command=forget") {
            *opened = None;
            return "{\"bytesRead\":0,\"cachedBytes\":0,\"response\":{\"ok\":true}}".to_string();
        }
        if opened.as_ref().is_none_or(|(known, _)| *known != folder) {
            match Library::open_with(&Folder(folder.clone()), if cache_bytes == 0 { DEFAULT_CACHE_BYTES } else { cache_bytes }) {
                Ok(library) => *opened = Some((folder, library)),
                Err(error) => return format!("{{\"bytesRead\":0,\"cachedBytes\":0,\"response\":{{\"ok\":false,\"error\":{}}}}}", api::quote(&error.to_string())),
            }
        }
        let library = &opened.as_ref().expect("just opened").1;
        let before = library.bytes_read();
        // A module file that can't be read makes the engine panic (for now): turn that into an error, and open the modules afresh next time
        match catch_unwind(AssertUnwindSafe(|| api::respond(library, request))) {
            Ok(response) => format!("{{\"bytesRead\":{},\"cachedBytes\":{},\"response\":{response}}}", library.bytes_read() - before, library.cache.bytes()),
            Err(_) => {
                *opened = None;
                "{\"bytesRead\":0,\"cachedBytes\":0,\"response\":{\"ok\":false,\"error\":\"a module couldn't be read (it may be damaged or incomplete)\"}}".to_string()
            }
        }
    })
}

/// # Safety
/// `folder` and `request` must be valid, NUL-terminated UTF-8 text. The result must be passed to `biblelastic_free`.
#[no_mangle]
pub unsafe extern "C" fn biblelastic_request(folder: *const c_char, request: *const c_char, cache_bytes: usize) -> *mut c_char {
    let text = |pointer: *const c_char| if pointer.is_null() { String::new() } else { CStr::from_ptr(pointer).to_string_lossy().into_owned() };
    let response = answer(&text(folder), &text(request), cache_bytes);
    CString::new(response).unwrap_or_default().into_raw()
}

/// # Safety
/// `text` must have come from `biblelastic_request`, and not have been freed already.
#[no_mangle]
pub unsafe extern "C" fn biblelastic_free(text: *mut c_char) {
    if !text.is_null() { drop(CString::from_raw(text)); }
}

#[cfg(test)]
mod tests {
    #[test]
    fn a_missing_folder_is_an_error_not_a_crash() {
        let response = super::answer("/nowhere/at/all", "command=info", 0);
        assert!(response.contains("\"ok\":false"), "{response}");
        assert!(super::answer("/nowhere/at/all", "command=forget", 0).contains("\"ok\":true"));
    }
}
