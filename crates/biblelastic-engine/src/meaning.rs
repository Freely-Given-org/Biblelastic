//! Meaning-based search: a small sentence-embedding model (a BERT encoder, e.g., `bge-small-en-v1.5`) turns a query into a vector,
//! which is compared with the vectors of passages that were made with the same model when the modules were built.
//!
//! The model runs here, in plain Rust, so that it's the same natively and in WebAssembly, and needs nothing else.
//! Its weights are stored as one byte each (with a scale for each row), and the arithmetic is done in 32-bit floats.
//! The same code embeds the passages when the modules are built (`biblelastic embed`), so the two sides always agree.
//!
//! A model module (kind `model`) has these sections (all raw):
//! - `model.config`: `name=value` lines (`layers`, `hidden`, `heads`, `intermediate`, `query_prefix`, `passage_prefix`, `max_tokens`,
//!   `pooling`: `cls` (the first token's state, as bge uses) or `mean` (all the tokens' states averaged, as e5 does),
//!   and `tokenizer`: `wordpiece` (BERT's) or `unigram` (SentencePiece's, as XLM-RoBERTa and multilingual e5 use))
//! - `model.vocab`: the word pieces, one per line, in the order of their ids
//! - `model.scores`: for a unigram tokenizer, each piece's score (its log probability) as a little-endian f32
//! - for a matrix `NAME` (rows × columns): `NAME.q` (one signed byte per weight, row by row) and `NAME.s` (one little-endian f32 scale per row)
//! - for a vector `NAME`: `NAME.f` (little-endian f32s)

use std::collections::HashMap;

use crate::format::{Module, ModuleWriter, Result};

/// The pieces of a BERT model: (name, rows, columns). A matrix with one row is a vector (stored as floats); the others are stored as bytes.
pub fn tensor_names(layers: usize) -> Vec<String> {
    let mut names: Vec<String> = ["embeddings.word_embeddings.weight", "embeddings.position_embeddings.weight", "embeddings.token_type_embeddings.weight",
        "embeddings.LayerNorm.weight", "embeddings.LayerNorm.bias"].iter().map(|name| name.to_string()).collect();
    for layer in 0..layers {
        for part in ["attention.self.query", "attention.self.key", "attention.self.value", "attention.output.dense", "intermediate.dense", "output.dense"] {
            names.push(format!("encoder.layer.{layer}.{part}.weight"));
            names.push(format!("encoder.layer.{layer}.{part}.bias"));
        }
        for part in ["attention.output.LayerNorm", "output.LayerNorm"] {
            names.push(format!("encoder.layer.{layer}.{part}.weight"));
            names.push(format!("encoder.layer.{layer}.{part}.bias"));
        }
    }
    names
}

/// Write a model module's sections, from its configuration, its word pieces, and its weights (name → (shape, values))
/// (`scores` are a unigram tokenizer's, and empty for a WordPiece one.)
pub fn write_model(writer: &mut ModuleWriter, config: &[(&str, String)], vocab: &[String], scores: &[f32], tensors: &HashMap<String, (Vec<usize>, Vec<f32>)>) -> Result<()> {
    let text: String = config.iter().map(|(name, value)| format!("{name}={value}\n")).collect();
    writer.raw("model.config", text.as_bytes());
    writer.raw("model.vocab", vocab.join("\n").as_bytes());
    if !scores.is_empty() { writer.raw("model.scores", &scores.iter().flat_map(|score| score.to_le_bytes()).collect::<Vec<u8>>()); }
    let layers: usize = config.iter().find(|(name, _)| *name == "layers").ok_or("no layers")?.1.parse()?;
    for name in tensor_names(layers) {
        let (shape, values) = tensors.get(&name).ok_or_else(|| format!("the model has no {name}"))?;
        if shape.len() == 1 {
            writer.raw(&format!("{name}.f"), &values.iter().flat_map(|value| value.to_le_bytes()).collect::<Vec<u8>>());
        } else {
            let columns = shape[1];
            let (mut quantised, mut scales) = (Vec::with_capacity(values.len()), Vec::with_capacity(shape[0] * 4));
            for row in values.chunks(columns) {
                let largest = row.iter().fold(0f32, |largest, value| largest.max(value.abs()));
                let scale = if largest > 0.0 { largest / 127.0 } else { 1.0 };
                quantised.extend(row.iter().map(|value| (value / scale).round().clamp(-127.0, 127.0) as i8 as u8));
                scales.extend(scale.to_le_bytes());
            }
            writer.raw(&format!("{name}.q"), &quantised);
            writer.raw(&format!("{name}.s"), &scales);
        }
    }
    Ok(())
}

/// A matrix of weights, one byte each, with a scale for each row
struct Matrix {
    rows: usize,
    columns: usize,
    weights: Vec<i8>,
    scales: Vec<f32>,
}

impl Matrix {
    fn open(module: &Module, name: &str, columns: usize) -> Result<Matrix> {
        let weights: Vec<i8> = module.bytes(&format!("{name}.q"))?.into_iter().map(|byte| byte as i8).collect();
        let scales = floats(&module.bytes(&format!("{name}.s"))?);
        if weights.len() != scales.len() * columns { return Err(format!("{name} isn't {} by {columns}", scales.len()).into()); }
        Ok(Matrix { rows: scales.len(), columns, weights, scales })
    }

    /// One row, as floats
    fn row(&self, row: usize, into: &mut [f32]) {
        let scale = self.scales[row];
        for (value, &weight) in into.iter_mut().zip(&self.weights[row * self.columns..(row + 1) * self.columns]) { *value = weight as f32 * scale; }
    }
}

/// A linear layer: `output = weights × input + bias`, for each of several tokens at once
struct Linear {
    matrix: Matrix,
    bias: Vec<f32>,
}

impl Linear {
    fn open(module: &Module, name: &str, columns: usize) -> Result<Linear> {
        Ok(Linear { matrix: Matrix::open(module, &format!("{name}.weight"), columns)?, bias: floats(&module.bytes(&format!("{name}.bias.f"))?) })
    }

    /// `input` is `tokens` rows of `columns`; the result is `tokens` rows of `rows`
    fn apply(&self, input: &[f32], tokens: usize) -> Vec<f32> {
        #[cfg(target_arch = "aarch64")]
        if std::arch::is_aarch64_feature_detected!("dotprod") { return unsafe { self.apply_bytes(input, tokens) }; } // (Checked once, then remembered)
        #[cfg(all(target_arch = "wasm32", target_feature = "simd128"))]
        return self.apply_shorts(input, tokens);
        #[allow(unreachable_code)]
        let (rows, columns) = (self.matrix.rows, self.matrix.columns);
        let mut output = vec![0f32; tokens * rows];
        let mut weights = vec![0f32; columns];
        for row in 0..rows {
            // Each row of weights is turned into floats once, and used for every token
            self.matrix.row(row, &mut weights);
            for token in 0..tokens { output[token * rows + row] = dot(&weights, &input[token * columns..(token + 1) * columns]) + self.bias[row]; }
        }
        output
    }

    /// The same with ARM's byte dot-product instruction (`sdot`, in most phones' processors since about 2018), which does sixteen products at once:
    /// each token's input is turned into bytes too, with a scale for the token, and each row of weights is used for four tokens at a time.
    /// About three times as fast as the floats on a phone, and nearly as accurate (0.999 against 0.9997).
    #[cfg(target_arch = "aarch64")]
    #[target_feature(enable = "dotprod")]
    unsafe fn apply_bytes(&self, input: &[f32], tokens: usize) -> Vec<f32> {
        use std::arch::aarch64::*;
        let (rows, columns) = (self.matrix.rows, self.matrix.columns);
        let (quantised, scales) = quantise_tokens(input, tokens, columns);
        let blocks = columns / 16 * 16;
        let mut output = vec![0f32; tokens * rows];
        for row in 0..rows {
            let weights = &self.matrix.weights[row * columns..(row + 1) * columns];
            let (scale, bias) = (self.matrix.scales[row], self.bias[row]);
            let finish = |token: usize, sum: i32| -> f32 {
                let tail: i32 = weights[blocks..].iter().zip(&quantised[token * columns + blocks..(token + 1) * columns]).map(|(&w, &x)| w as i32 * x as i32).sum();
                (sum + tail) as f32 * scale * scales[token] + bias
            };
            let mut token = 0;
            while token + 4 <= tokens {
                let base = [0, 1, 2, 3].map(|offset| quantised[(token + offset) * columns..].as_ptr());
                let mut sums = [vdupq_n_s32(0); 4];
                for start in (0..blocks).step_by(16) {
                    let w = vld1q_s8(weights.as_ptr().add(start));
                    for which in 0..4 { sums[which] = vdotq_s32(sums[which], w, vld1q_s8(base[which].add(start))); }
                }
                for which in 0..4 { output[(token + which) * rows + row] = finish(token + which, vaddvq_s32(sums[which])); }
                token += 4;
            }
            for token in token..tokens {
                let x = quantised[token * columns..].as_ptr();
                let mut sum = vdupq_n_s32(0);
                for start in (0..blocks).step_by(16) { sum = vdotq_s32(sum, vld1q_s8(weights.as_ptr().add(start)), vld1q_s8(x.add(start))); }
                output[token * rows + row] = finish(token, vaddvq_s32(sum));
            }
        }
        output
    }
}

impl Linear {
    /// The same in WebAssembly, whose vector instructions have a dot product of 16-bit numbers (eight at once) but not of bytes:
    /// the inputs and weights are bytes, made 16-bit as they're loaded. About twice as fast as the floats.
    #[cfg(all(target_arch = "wasm32", target_feature = "simd128"))]
    fn apply_shorts(&self, input: &[f32], tokens: usize) -> Vec<f32> {
        use std::arch::wasm32::*;
        let (rows, columns) = (self.matrix.rows, self.matrix.columns);
        let (quantised, scales) = quantise_tokens(input, tokens, columns);
        let shorts: Vec<i16> = quantised.iter().map(|&byte| byte as i16).collect();
        let blocks = columns / 8 * 8;
        let mut output = vec![0f32; tokens * rows];
        let sum = |vector: v128| i32x4_extract_lane::<0>(vector) + i32x4_extract_lane::<1>(vector) + i32x4_extract_lane::<2>(vector) + i32x4_extract_lane::<3>(vector);
        for row in 0..rows {
            let weights = &self.matrix.weights[row * columns..(row + 1) * columns];
            let (scale, bias) = (self.matrix.scales[row], self.bias[row]);
            let finish = |token: usize, total: i32| -> f32 {
                let tail: i32 = weights[blocks..].iter().zip(&shorts[token * columns + blocks..(token + 1) * columns]).map(|(&w, &x)| w as i32 * x as i32).sum();
                (total + tail) as f32 * scale * scales[token] + bias
            };
            let mut token = 0;
            while token + 4 <= tokens {
                let mut sums = [i32x4_splat(0); 4];
                for start in (0..blocks).step_by(8) {
                    // Safety: start + 8 <= blocks <= columns, the length of the row and of each token's values
                    let w = unsafe { i16x8_load_extend_i8x8(weights.as_ptr().add(start)) };
                    for which in 0..4 {
                        let x = unsafe { v128_load(shorts.as_ptr().add((token + which) * columns + start) as *const v128) };
                        sums[which] = i32x4_add(sums[which], i32x4_dot_i16x8(w, x));
                    }
                }
                for which in 0..4 { output[(token + which) * rows + row] = finish(token + which, sum(sums[which])); }
                token += 4;
            }
            for token in token..tokens {
                let mut total = i32x4_splat(0);
                for start in (0..blocks).step_by(8) {
                    let (w, x) = unsafe { (i16x8_load_extend_i8x8(weights.as_ptr().add(start)), v128_load(shorts.as_ptr().add(token * columns + start) as *const v128)) };
                    total = i32x4_add(total, i32x4_dot_i16x8(w, x));
                }
                output[token * rows + row] = finish(token, sum(total));
            }
        }
        output
    }
}

/// Each token's values as bytes, with a scale for each token
#[cfg(any(target_arch = "aarch64", all(target_arch = "wasm32", target_feature = "simd128")))]
fn quantise_tokens(input: &[f32], tokens: usize, columns: usize) -> (Vec<i8>, Vec<f32>) {
    let mut quantised = vec![0i8; tokens * columns];
    let mut scales = vec![1f32; tokens];
    for token in 0..tokens {
        let values = &input[token * columns..(token + 1) * columns];
        let largest = values.iter().fold(0f32, |largest, value| largest.max(value.abs()));
        if largest > 0.0 { scales[token] = largest / 127.0; }
        for (byte, value) in quantised[token * columns..(token + 1) * columns].iter_mut().zip(values) { *byte = (value / scales[token]).round() as i8; }
    }
    (quantised, scales)
}

/// A dot product, in eight lanes so that the compiler can use the processor's vector instructions
fn dot(a: &[f32], b: &[f32]) -> f32 {
    let mut lanes = [0f32; 8];
    let (a8, b8) = (a.chunks_exact(8), b.chunks_exact(8));
    let tail: f32 = a8.remainder().iter().zip(b8.remainder()).map(|(x, y)| x * y).sum();
    for (x, y) in a8.zip(b8) {
        for lane in 0..8 { lanes[lane] += x[lane] * y[lane]; }
    }
    lanes.iter().sum::<f32>() + tail
}

struct LayerNorm {
    weight: Vec<f32>,
    bias: Vec<f32>,
}

impl LayerNorm {
    fn open(module: &Module, name: &str) -> Result<LayerNorm> {
        Ok(LayerNorm { weight: floats(&module.bytes(&format!("{name}.weight.f"))?), bias: floats(&module.bytes(&format!("{name}.bias.f"))?) })
    }

    fn apply(&self, values: &mut [f32]) {
        let width = self.weight.len();
        for token in values.chunks_mut(width) {
            let mean = token.iter().sum::<f32>() / width as f32;
            let variance = token.iter().map(|value| (value - mean) * (value - mean)).sum::<f32>() / width as f32;
            let divisor = (variance + 1e-12).sqrt();
            for ((value, weight), bias) in token.iter_mut().zip(&self.weight).zip(&self.bias) { *value = (*value - mean) / divisor * weight + bias; }
        }
    }
}

struct Layer {
    query: Linear,
    key: Linear,
    value: Linear,
    attention_output: Linear,
    attention_norm: LayerNorm,
    intermediate: Linear,
    output: Linear,
    output_norm: LayerNorm,
}

pub struct Model {
    pub name: String,
    pub query_prefix: String,
    pub passage_prefix: String,
    pub max_tokens: usize,
    hidden: usize,
    heads: usize,
    tokenizer: Tokenizer,
    /// Whether the vector is the average of all the tokens' states (otherwise it's the first token's)
    mean: bool,
    words: Matrix,
    positions: Matrix,
    token_type: Vec<f32>,
    embedding_norm: LayerNorm,
    layers: Vec<Layer>,
}

impl Model {
    pub fn open(module: &Module, name: &str) -> Result<Model> {
        let config: HashMap<String, String> = module.text("model.config")?.lines()
            .filter_map(|line| line.split_once('=')).map(|(name, value)| (name.to_string(), value.to_string())).collect();
        let number = |name: &str| -> Result<usize> { Ok(config.get(name).ok_or_else(|| format!("the model's config has no {name}"))?.parse()?) };
        let (hidden, intermediate) = (number("hidden")?, number("intermediate")?);
        let mean = match config.get("pooling").map(String::as_str) { Some("cls") => false, Some("mean") => true, other => return Err(format!("unknown pooling {other:?}").into()) };
        let mut layers = Vec::new();
        for layer in 0..number("layers")? {
            let part = |part: &str| format!("encoder.layer.{layer}.{part}");
            layers.push(Layer {
                query: Linear::open(module, &part("attention.self.query"), hidden)?,
                key: Linear::open(module, &part("attention.self.key"), hidden)?,
                value: Linear::open(module, &part("attention.self.value"), hidden)?,
                attention_output: Linear::open(module, &part("attention.output.dense"), hidden)?,
                attention_norm: LayerNorm::open(module, &part("attention.output.LayerNorm"))?,
                intermediate: Linear::open(module, &part("intermediate.dense"), hidden)?,
                output: Linear::open(module, &part("output.dense"), intermediate)?,
                output_norm: LayerNorm::open(module, &part("output.LayerNorm"))?,
            });
        }
        let token_types = Matrix::open(module, "embeddings.token_type_embeddings.weight", hidden)?;
        let mut token_type = vec![0f32; hidden];
        token_types.row(0, &mut token_type);
        Ok(Model {
            name: name.to_string(),
            query_prefix: config.get("query_prefix").cloned().unwrap_or_default(),
            passage_prefix: config.get("passage_prefix").cloned().unwrap_or_default(),
            max_tokens: number("max_tokens").unwrap_or(512),
            hidden, heads: number("heads")?,
            tokenizer: if config.get("tokenizer").map(String::as_str) == Some("unigram") {
                Tokenizer::Unigram(Unigram::new(module.text("model.vocab")?.split('\n').zip(floats(&module.bytes("model.scores")?)).map(|(piece, score)| (piece.to_string(), score)).collect()))
            } else { Tokenizer::WordPiece(WordPiece::new(&module.text("model.vocab")?)) },
            mean,
            words: Matrix::open(module, "embeddings.word_embeddings.weight", hidden)?,
            positions: Matrix::open(module, "embeddings.position_embeddings.weight", hidden)?,
            token_type,
            embedding_norm: LayerNorm::open(module, "embeddings.LayerNorm")?,
            layers,
        })
    }

    /// The model's vector for a query (with the model's query prefix in front of it)
    pub fn embed_query(&self, text: &str) -> Vec<f32> { self.embed(&format!("{}{text}", self.query_prefix)) }

    /// The model's vector for a passage
    pub fn embed_passage(&self, text: &str) -> Vec<f32> { self.embed(&format!("{}{text}", self.passage_prefix)) }

    /// The vector for some text: its first token's final state, scaled to a length of 1
    pub fn embed(&self, text: &str) -> Vec<f32> {
        let ids = self.tokenizer.encode(text, self.max_tokens.min(self.positions.rows));
        let (tokens, hidden) = (ids.len(), self.hidden);
        let mut states = vec![0f32; tokens * hidden];
        let mut position = vec![0f32; hidden];
        for (token, &id) in ids.iter().enumerate() {
            let state = &mut states[token * hidden..(token + 1) * hidden];
            self.words.row(id as usize, state);
            self.positions.row(token, &mut position);
            for ((value, position), token_type) in state.iter_mut().zip(&position).zip(&self.token_type) { *value += position + token_type; }
        }
        self.embedding_norm.apply(&mut states);
        for layer in &self.layers { states = self.layer(layer, states, tokens); }
        let mut vector = if self.mean {
            let mut sum = vec![0f32; hidden];
            for state in states.chunks(hidden) { for (total, value) in sum.iter_mut().zip(state) { *total += value; } }
            sum
        } else { states[..hidden].to_vec() };
        let length = vector.iter().map(|value| value * value).sum::<f32>().sqrt().max(1e-12);
        for value in &mut vector { *value /= length; }
        vector
    }

    fn layer(&self, layer: &Layer, states: Vec<f32>, tokens: usize) -> Vec<f32> {
        let hidden = self.hidden;
        let head_size = hidden / self.heads;
        let (queries, keys, values) = (layer.query.apply(&states, tokens), layer.key.apply(&states, tokens), layer.value.apply(&states, tokens));
        let mut context = vec![0f32; tokens * hidden];
        let mut weights = vec![0f32; tokens];
        let scale = 1.0 / (head_size as f32).sqrt();
        for head in 0..self.heads {
            let part = head * head_size..(head + 1) * head_size;
            for token in 0..tokens {
                let query = &queries[token * hidden..][part.clone()];
                for (other, weight) in weights.iter_mut().enumerate() { *weight = dot(query, &keys[other * hidden..][part.clone()]) * scale; }
                softmax(&mut weights);
                let output = &mut context[token * hidden..][part.clone()];
                for (other, &weight) in weights.iter().enumerate() {
                    for (value, &other_value) in output.iter_mut().zip(&values[other * hidden..][part.clone()]) { *value += weight * other_value; }
                }
            }
        }
        let mut attended = layer.attention_output.apply(&context, tokens);
        for (value, state) in attended.iter_mut().zip(&states) { *value += state; }
        layer.attention_norm.apply(&mut attended);
        let mut intermediate = layer.intermediate.apply(&attended, tokens);
        for value in &mut intermediate { *value = gelu(*value); }
        let mut output = layer.output.apply(&intermediate, tokens);
        for (value, state) in output.iter_mut().zip(&attended) { *value += state; }
        layer.output_norm.apply(&mut output);
        output
    }
}

fn softmax(values: &mut [f32]) {
    let largest = values.iter().fold(f32::MIN, |largest, &value| largest.max(value));
    let mut total = 0.0;
    for value in values.iter_mut() { *value = (*value - largest).exp(); total += *value; }
    for value in values.iter_mut() { *value /= total; }
}

/// The Gaussian error linear unit, exactly (as BERT uses it), with an approximation of erf that's good to about 1e-7
fn gelu(x: f32) -> f32 { 0.5 * x * (1.0 + erf(x / std::f32::consts::SQRT_2)) }

fn erf(x: f32) -> f32 {
    // Abramowitz and Stegun, 7.1.26
    let (sign, x) = if x < 0.0 { (-1.0, -x as f64) } else { (1.0, x as f64) };
    let t = 1.0 / (1.0 + 0.3275911 * x);
    let y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * (-x * x).exp();
    sign * y as f32
}

fn floats(bytes: &[u8]) -> Vec<f32> { bytes.chunks_exact(4).map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]])).collect() }

mod compatibility;

/// How a model's text is cut into pieces
pub enum Tokenizer {
    WordPiece(WordPiece),
    Unigram(Unigram),
}

impl Tokenizer {
    /// The ids of some text's pieces, between the model's first and last special pieces, and no more than `limit` in all
    pub fn encode(&self, text: &str, limit: usize) -> Vec<u32> {
        match self { Tokenizer::WordPiece(tokenizer) => tokenizer.encode(text, limit), Tokenizer::Unigram(tokenizer) => tokenizer.encode(text, limit) }
    }
}

/// SentencePiece's unigram tokenizer (as XLM-RoBERTa uses it): the text is normalised (Unicode's compatibility forms, and single spaces),
/// each word gets `▁` in front, and is cut into the pieces whose scores (log probabilities) add up to the most
pub struct Unigram {
    pieces: HashMap<String, (u32, f32)>,
    /// The most characters in any piece
    longest: usize,
    /// The score of a character that no piece has (it becomes `<unk>`): ten less than the lowest score, as SentencePiece does
    unknown_score: f32,
    unknown: u32,
    first: u32,
    last: u32,
}

impl Unigram {
    /// From the pieces (with their scores), in the order of their ids
    pub fn new(pieces: Vec<(String, f32)>) -> Unigram {
        let id = |wanted: &str| pieces.iter().position(|(piece, _)| piece == wanted).unwrap_or(0) as u32;
        let (unknown, first, last) = (id("<unk>"), id("<s>"), id("</s>"));
        let lowest = pieces.iter().map(|(_, score)| *score).fold(0f32, f32::min);
        let longest = pieces.iter().map(|(piece, _)| piece.chars().count()).max().unwrap_or(1);
        let pieces = pieces.into_iter().enumerate().filter(|(_, (piece, _))| !piece.starts_with('<') || !piece.ends_with('>'))
            .map(|(id, (piece, score))| (piece, (id as u32, score))).collect();
        Unigram { pieces, longest, unknown_score: lowest - 10.0, unknown, first, last }
    }

    pub fn encode(&self, text: &str, limit: usize) -> Vec<u32> {
        let mut ids = vec![self.first];
        for word in normalise(text).split(' ').filter(|word| !word.is_empty()) { ids.extend(self.word(word)); }
        ids.truncate(limit.max(2) - 1);
        ids.push(self.last);
        ids
    }

    /// One word's pieces (`▁` goes in front of it)
    pub fn word(&self, word: &str) -> Vec<u32> {
        let characters: Vec<char> = std::iter::once('▁').chain(word.chars()).collect();
        let count = characters.len();
        // best[end] = (the best score of the text up to here, where its last piece starts, that piece's id)
        let mut best: Vec<Option<(f32, usize, u32)>> = vec![None; count + 1];
        best[0] = Some((0.0, 0, 0));
        let mut piece = String::new();
        for start in 0..count {
            let Some((score, _, _)) = best[start] else { continue };
            piece.clear();
            let mut found_single = false;
            for end in start + 1..=count.min(start + self.longest) {
                piece.push(characters[end - 1]);
                if let Some(&(id, piece_score)) = self.pieces.get(&piece) {
                    if end == start + 1 { found_single = true; }
                    let total = score + piece_score;
                    if best[end].is_none_or(|(old, _, _)| total > old) { best[end] = Some((total, start, id)); }
                }
            }
            if !found_single { // A character that no piece starts with: it's unknown
                let total = score + self.unknown_score;
                if best[start + 1].is_none_or(|(old, _, _)| total > old) { best[start + 1] = Some((total, start, self.unknown)); }
            }
        }
        let mut ids = Vec::new();
        let mut end = count;
        while end > 0 {
            let (_, start, id) = best[end].expect("every position can be reached");
            ids.push(id);
            end = start;
        }
        ids.reverse();
        ids
    }
}

/// Text as SentencePiece's normaliser makes it: compatibility forms (e.g., `…` → `...`, `ﬁ` → `fi`), control characters left out, and single spaces
pub fn normalise(text: &str) -> String {
    let mut normal = String::with_capacity(text.len());
    for character in text.chars() {
        if character.is_whitespace() { if !normal.ends_with(' ') { normal.push(' '); } continue; }
        if character.is_control() || character == '\u{200B}' || character == '\u{FEFF}' || character == '\u{AD}' { continue; }
        match compatibility::COMPATIBILITY.binary_search_by(|(from, _)| from.cmp(&character)) {
            Ok(index) => {
                for replacement in compatibility::COMPATIBILITY[index].1.chars() {
                    if replacement == ' ' { if !normal.ends_with(' ') { normal.push(' '); } } else { normal.push(replacement); }
                }
            }
            Err(_) => normal.push(character),
        }
    }
    normal.trim().to_string()
}

/// BERT's WordPiece tokenizer (for an uncased model): lower case, accents removed, punctuation split off,
/// then each word cut into the longest pieces that the vocabulary has (later pieces start with `##`)
pub struct WordPiece {
    ids: HashMap<String, u32>,
    unknown: u32,
    first: u32,
    last: u32,
}

impl WordPiece {
    pub fn new(vocab: &str) -> WordPiece {
        let ids: HashMap<String, u32> = vocab.lines().enumerate().map(|(id, piece)| (piece.to_string(), id as u32)).collect();
        let id = |piece: &str| ids.get(piece).copied().unwrap_or(0);
        WordPiece { unknown: id("[UNK]"), first: id("[CLS]"), last: id("[SEP]"), ids }
    }

    /// The ids of some text's pieces, between `[CLS]` and `[SEP]`, and no more than `limit` in all
    pub fn encode(&self, text: &str, limit: usize) -> Vec<u32> {
        let mut ids = vec![self.first];
        'words: for word in basic_words(text) {
            let characters: Vec<char> = word.chars().collect();
            if characters.len() > 100 { ids.push(self.unknown); continue; }
            let (mut start, mut pieces) = (0, Vec::new());
            while start < characters.len() {
                let found = (start + 1..=characters.len()).rev().find_map(|end| {
                    let piece: String = characters[start..end].iter().collect();
                    let piece = if start > 0 { format!("##{piece}") } else { piece };
                    self.ids.get(&piece).map(|&id| (end, id))
                });
                match found {
                    Some((end, id)) => { pieces.push(id); start = end; }
                    None => { ids.push(self.unknown); continue 'words; }
                }
            }
            ids.extend(pieces);
        }
        ids.truncate(limit.max(2) - 1);
        ids.push(self.last);
        ids
    }
}

/// The words of some text, as BERT's basic tokenizer makes them
fn basic_words(text: &str) -> Vec<String> {
    let mut words = Vec::new();
    let mut word = String::new();
    fn finish(words: &mut Vec<String>, word: &mut String) { if !word.is_empty() { words.push(std::mem::take(word)); } }
    for character in text.chars() {
        if character == '\0' || character == '\u{FFFD}' || (character.is_control() && !character.is_whitespace()) { continue; }
        if character.is_whitespace() { finish(&mut words, &mut word); continue; }
        if is_punctuation(character) || is_chinese(character) { finish(&mut words, &mut word); words.push(character.to_string()); continue; }
        for lower in character.to_lowercase() {
            if !('\u{0300}'..='\u{036F}').contains(&lower) { word.push(crate::query::without_accent(lower)); }
        }
    }
    finish(&mut words, &mut word);
    words
}

fn is_punctuation(character: char) -> bool {
    let code = character as u32;
    (33..=47).contains(&code) || (58..=64).contains(&code) || (91..=96).contains(&code) || (123..=126).contains(&code)
        || matches!(character, '\u{2010}'..='\u{2027}' | '\u{2030}'..='\u{205E}' | '\u{3001}'..='\u{3003}' | '\u{3008}'..='\u{3011}'
            | '¡' | '§' | '«' | '¶' | '·' | '»' | '¿')
}

fn is_chinese(character: char) -> bool {
    matches!(character, '\u{4E00}'..='\u{9FFF}' | '\u{3400}'..='\u{4DBF}' | '\u{20000}'..='\u{2A6DF}' | '\u{2A700}'..='\u{2B73F}'
        | '\u{2B740}'..='\u{2B81F}' | '\u{2B820}'..='\u{2CEAF}' | '\u{F900}'..='\u{FAFF}' | '\u{2F800}'..='\u{2FA1F}')
}

/// The vectors of a work's passages, made with one model: each passage as one signed byte for each dimension, all with one scale
pub struct Vectors {
    pub model: String,
    pub dimensions: usize,
    pub scale: f32,
    pub data: Vec<i8>,
}

impl Vectors {
    pub fn open(module: &Module) -> Result<Vectors> {
        let config: HashMap<String, String> = module.text("vectors.config")?.lines()
            .filter_map(|line| line.split_once('=')).map(|(name, value)| (name.to_string(), value.to_string())).collect();
        let dimensions: usize = config.get("dimensions").ok_or("no dimensions")?.parse()?;
        let data: Vec<i8> = module.bytes("vectors.data")?.into_iter().map(|byte| byte as i8).collect();
        Ok(Vectors { model: config.get("model").cloned().unwrap_or_default(), dimensions, scale: config.get("scale").ok_or("no scale")?.parse()?, data })
    }

    pub fn len(&self) -> usize { self.data.len() / self.dimensions }
    pub fn is_empty(&self) -> bool { self.data.is_empty() }

    /// How close each passage is to a query's vector (the cosine similarity, near enough)
    pub fn scores(&self, query: &[f32]) -> Vec<f32> {
        let mut row = vec![0f32; self.dimensions];
        self.data.chunks_exact(self.dimensions).map(|passage| {
            for (value, &byte) in row.iter_mut().zip(passage) { *value = byte as f32; }
            dot(&row, query) * self.scale
        }).collect()
    }
}

/// A set of vectors as one byte for each dimension: the scale (one for all of them) and the bytes
pub fn quantise(vectors: &[Vec<f32>]) -> (f32, Vec<u8>) {
    let largest = vectors.iter().flatten().fold(0f32, |largest, value| largest.max(value.abs())).max(1e-12);
    let scale = largest / 127.0;
    (scale, vectors.iter().flatten().map(|value| (value / scale).round().clamp(-127.0, 127.0) as i8 as u8).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn words_are_split_as_bert_splits_them() {
        assert_eq!(basic_words("Héllo, World! “Don’t” stop—now"), ["hello", ",", "world", "!", "“", "don", "’", "t", "”", "stop", "—", "now"]);
        let tokenizer = WordPiece::new("[PAD]\n[UNK]\n[CLS]\n[SEP]\nun\n##believ\n##able\nfaith\n,");
        assert_eq!(tokenizer.encode("Unbelievable faith, ξ", 512), [2, 4, 5, 6, 7, 8, 1, 3]);
        assert_eq!(tokenizer.encode("faith faith faith", 3), [2, 7, 3]);
    }

    #[test]
    fn unigram_pieces_are_the_most_probable() {
        let pieces = ["<s>", "<pad>", "</s>", "<unk>", "▁un", "zz", "▁unbe", "be", "liev", "able", "lievable", "▁", "...", "fi", "ne"];
        let scores = [0.0, 0.0, 0.0, 0.0, -2.0, -9.0, -6.0, -3.0, -4.0, -3.0, -5.0, -1.0, -2.0, -3.0, -3.0];
        let tokenizer = Unigram::new(pieces.iter().zip(scores).map(|(piece, score)| (piece.to_string(), score)).collect());
        // ‘▁un’ + ‘be’ + ‘lievable’ (-10) beats ‘▁unbe’ + ‘liev’ + ‘able’ (-13); ‘…’ is ‘...’; ‘ﬁ’ is ‘fi’; and ‘ξ’ is unknown
        assert_eq!(tokenizer.encode("unbelievable  …  ﬁne ξ", 512), [0, 4, 7, 10, 11, 12, 11, 13, 14, 11, 3, 2]);
        assert_eq!(normalise(" Yaʸsous\u{A0}x² "), "Yaysous x2");
    }

    #[test]
    fn gelu_is_close() {
        assert!((gelu(1.0) - 0.841_344_7).abs() < 1e-6 && (gelu(-0.5) + 0.154_268_5).abs() < 1e-6);
    }
}
