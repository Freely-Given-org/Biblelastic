//! The query-side embedding model, run by tract. Shared by the command-line trial (main.rs) and the browser trial (web/index.html).

use tract_onnx::prelude::*;

pub type Runnable = SimplePlan<TypedFact, Box<dyn TypedOp>, Graph<TypedFact, Box<dyn TypedOp>>>;

/// Load an ONNX model of the BERT kind, fixed to one text of `length` tokens so that tract can optimise it fully
pub fn load(mut model: &[u8], length: usize) -> TractResult<Runnable> {
    let model = tract_onnx::onnx().model_for_read(&mut model)?;
    let sizes = SymbolValues::default().with(&model.symbols.sym("batch_size"), 1).with(&model.symbols.sym("sequence_length"), length as i64);
    model.into_typed()?.concretize_dims(&sizes)?.into_optimized()?.into_runnable()
}

/// The embedding of one text: the first token's output vector, scaled to length 1
pub fn embed(model: &Runnable, ids: &[i64], mask: &[i64]) -> TractResult<Vec<f32>> {
    let tensor = |values: &[i64]| -> TValue { tract_ndarray::Array2::from_shape_vec((1, values.len()), values.to_vec()).unwrap().into_tensor().into() };
    // The inputs are in the model's own order: ids, attention mask, token types
    let outputs = model.run(tvec!(tensor(ids), tensor(mask), tensor(&vec![0; ids.len()])))?;
    let states = outputs[0].to_array_view::<f32>()?;
    let size = states.shape()[2];
    let first: Vec<f32> = states.iter().take(size).copied().collect();
    let norm = first.iter().map(|value| value * value).sum::<f32>().sqrt();
    Ok(first.iter().map(|value| value / norm).collect())
}

// For the browser: three plain functions, as in crates/biblelastic-wasm
#[cfg(target_arch = "wasm32")]
mod browser {
    use std::cell::RefCell;

    fn no_randomness(_: &mut [u8]) -> Result<(), getrandom::Error> { Err(getrandom::Error::UNSUPPORTED) }
    getrandom::register_custom_getrandom!(no_randomness);

    thread_local! { static MODEL: RefCell<Option<(super::Runnable, usize)>> = const { RefCell::new(None) }; }

    #[no_mangle]
    pub extern "C" fn allocate(length: usize) -> *mut u8 { Box::leak(vec![0u8; length].into_boxed_slice()).as_mut_ptr() }

    /// Returns 0 if the model loaded
    #[no_mangle]
    pub unsafe extern "C" fn load(model: *const u8, bytes: usize, length: usize) -> i32 {
        match super::load(std::slice::from_raw_parts(model, bytes), length) {
            Ok(runnable) => { MODEL.with(|slot| *slot.borrow_mut() = Some((runnable, length))); 0 }
            Err(_) => 1,
        }
    }

    /// `ids` and `mask` are 64-bit integers, one for each token; the vector is written to `output`. Returns its size, or 0 if it failed.
    #[no_mangle]
    pub unsafe extern "C" fn embed(ids: *const i64, mask: *const i64, output: *mut f32) -> usize {
        MODEL.with(|slot| {
            let slot = slot.borrow();
            let Some((model, length)) = slot.as_ref() else { return 0 };
            let Ok(vector) = super::embed(model, std::slice::from_raw_parts(ids, *length), std::slice::from_raw_parts(mask, *length)) else { return 0 };
            std::ptr::copy_nonoverlapping(vector.as_ptr(), output, vector.len());
            vector.len()
        })
    }
}
