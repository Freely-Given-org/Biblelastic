//! Runs the bge-small-en-v1.5 model with tract (a pure-Rust ONNX runtime) on queries that were tokenised in Python,
//! and compares the vectors and the time with ONNX Runtime's.
//!
//!     cargo run --release -- ../../build/embeddings/rust [MODEL-FILE [TOKENS]]

use std::time::Instant;

const PADDED: usize = 32; // Tokens: the queries in the file are padded to this

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let folder = std::path::PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| "../../build/embeddings/rust".into()));
    let file = std::env::args().nth(2).unwrap_or_else(|| "bge-small-en-v1.5.int8.onnx".into());
    let length: usize = std::env::args().nth(3).map_or(Ok(PADDED), |number| number.parse())?; // Use only this many tokens
    let bytes = std::fs::read(folder.join(&file))?;
    let started = Instant::now();
    let model = embed_query::load(&bytes, length)?;
    println!("{file} with {length} tokens: loaded and optimised in {:.0} ms", started.elapsed().as_secs_f64() * 1000.0);

    let (mut total_ms, mut worst_agreement, mut count) = (0.0, 1.0f32, 0);
    for line in std::fs::read_to_string(folder.join("queries.tsv"))?.lines() {
        let fields: Vec<&str> = line.split('\t').collect();
        let numbers = |field: &str| field.split(' ').map(|number| number.parse::<i64>().unwrap()).collect::<Vec<_>>();
        let (ids, mask) = (numbers(fields[0]), numbers(fields[1]));
        if mask.iter().sum::<i64>() as usize > length { continue; } // Too long for this run
        let expected: Vec<f32> = fields[2].split(' ').map(|number| number.parse().unwrap()).collect();
        let started = Instant::now();
        let vector = embed_query::embed(&model, &ids[..length], &mask[..length])?;
        total_ms += started.elapsed().as_secs_f64() * 1000.0;
        worst_agreement = worst_agreement.min(vector.iter().zip(&expected).map(|(a, b)| a * b).sum());
        count += 1;
    }
    println!("{count} queries: {:.1} ms each; the vectors agree with ONNX Runtime's to at least {worst_agreement:.4} (cosine)", total_ms / count as f64);
    Ok(())
}
