//! Step 4: are Biblelastic's own index structures good enough, or should it use Tantivy's building blocks?
//!
//!     cargo run --release --manifest-path bench/Cargo.toml          (after `biblelastic compile`)
//!
//! It reads the real compiled modules from build/modules, and compares:
//!   A. term dictionaries: the sorted string array against a finite-state transducer (the `fst` crate)
//!   B. postings lists: delta + LEB128 bytes against blocks of 128 bit-packed with SIMD (the `bitpacking` crate, as Tantivy uses)
//!   C. a whole Tantivy index of the OET-RV against the OET-RV text module.

use std::hint::black_box;
use std::path::{Path, PathBuf};
use std::time::Instant;

use biblelastic_engine::format::Module;
use biblelastic_engine::library::{find_terms, Column, Nodes};
use bitpacking::{BitPacker, BitPacker4x};
use fst::automaton::{Automaton, Str};
use fst::{IntoStreamer, Streamer};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

/// Nanoseconds for one call (the best of several rounds)
fn time<T>(rounds: usize, mut call: impl FnMut() -> T) -> f64 {
    (0..rounds).map(|_| { let started = Instant::now(); black_box(call()); started.elapsed().as_nanos() as f64 }).fold(f64::MAX, f64::min)
}

fn kilobytes(bytes: usize) -> String { format!("{:.1} kB", bytes as f64 / 1024.0) }
fn duration(nanoseconds: f64) -> String {
    if nanoseconds >= 1e6 { format!("{:.2} ms", nanoseconds / 1e6) } else if nanoseconds >= 1e3 { format!("{:.1} µs", nanoseconds / 1e3) } else { format!("{nanoseconds:.0} ns") }
}

/// The same "random" choices every run
struct Chooser(u64);
impl Chooser {
    fn next(&mut self, below: usize) -> usize {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((self.0 >> 33) as usize) % below
    }
}

/// Is the edit distance between these two words no more than `limit`?
fn within_distance(a: &[char], b: &str, limit: usize, rows: &mut (Vec<usize>, Vec<usize>)) -> bool {
    let (previous, current) = (&mut rows.0, &mut rows.1);
    previous.clear();
    previous.extend(0..=a.len());
    let mut length = 0;
    for (n, character) in b.chars().enumerate() {
        length = n + 1;
        current.clear();
        current.push(n + 1);
        let mut smallest = n + 1;
        for (m, &other) in a.iter().enumerate() {
            let cost = (previous[m] + usize::from(other != character)).min(previous[m + 1] + 1).min(current[m] + 1);
            smallest = smallest.min(cost);
            current.push(cost);
        }
        if smallest > limit { return false; }
        std::mem::swap(previous, current);
    }
    length.abs_diff(a.len()) <= limit && previous[a.len()] <= limit
}

/// The automaton that Tantivy uses for near matches. (The `fst` crate's own `Levenshtein` isn't used here
/// because it found nothing at all, not even the word itself, for Hebrew words with vowel points.)
struct Near(levenshtein_automata::DFA);

impl Automaton for Near {
    type State = u32;
    fn start(&self) -> u32 { self.0.initial_state() }
    fn is_match(&self, state: &u32) -> bool { matches!(self.0.distance(*state), levenshtein_automata::Distance::Exact(_)) }
    fn can_match(&self, state: &u32) -> bool { *state != levenshtein_automata::SINK_STATE }
    fn accept(&self, state: &u32, byte: u8) -> u32 { self.0.transition(*state, byte) }
}

fn varints(list: &[u32], out: &mut Vec<u8>) {
    let mut previous = 0;
    for &value in list {
        let mut difference = value - previous;
        previous = value;
        while difference >= 0x80 { out.push(difference as u8 | 0x80); difference >>= 7; }
        out.push(difference as u8);
    }
}

fn read_varints(data: &[u8], count: usize, mut value: u32, out: &mut Vec<u32>) -> usize {
    let mut at = 0;
    for _ in 0..count {
        let (mut difference, mut shift) = (0u32, 0);
        loop { let byte = data[at]; at += 1; difference |= ((byte & 0x7F) as u32) << shift; if byte & 0x80 == 0 { break; } shift += 7; }
        value += difference;
        out.push(value);
    }
    at
}

const BLOCK: usize = BitPacker4x::BLOCK_LEN; // 128

/// As Tantivy does: whole blocks of 128 are bit-packed (one byte says how many bits), and what's left over is varints
fn blocks(packer: &BitPacker4x, list: &[u32], out: &mut Vec<u8>) {
    let mut previous = 0;
    let mut chunks = list.chunks_exact(BLOCK);
    for chunk in &mut chunks {
        let bits = packer.num_bits_sorted(previous, chunk);
        out.push(bits);
        let start = out.len();
        out.resize(start + BLOCK * 4, 0);
        let written = packer.compress_sorted(previous, chunk, &mut out[start..], bits);
        out.truncate(start + written);
        previous = chunk[BLOCK - 1];
    }
    let rest: Vec<u32> = chunks.remainder().iter().map(|&value| value - previous).collect();
    varints(&rest, out); // Ascending, and counted from the end of the last block
}

fn read_blocks(packer: &BitPacker4x, data: &[u8], count: usize, out: &mut Vec<u32>) {
    let (mut at, mut previous) = (0, 0);
    let mut block = [0u32; BLOCK];
    for _ in 0..count / BLOCK {
        let bits = data[at];
        at += 1 + packer.decompress_sorted(previous, &data[at + 1..], &mut block, bits);
        previous = block[BLOCK - 1];
        out.extend_from_slice(&block);
    }
    read_varints(&data[at..], count % BLOCK, previous, out);
}

fn compare_column(modules: &Path, module_name: &str, column: &str) -> Result<()> {
    let module = Module::open_file(&modules.join(format!("{module_name}.blm")))?;
    let dictionary = module.strings(&format!("col.{column}.dict"))?;
    let owned: Vec<String> = (0..dictionary.len()).map(|id| dictionary.get(id)).collect();
    let terms: Vec<&str> = owned.iter().map(String::as_str).collect();
    let lists: Vec<Vec<u32>> = (0..terms.len()).map(|id| module.postings(&format!("col.{column}.post"), id)).collect::<std::result::Result<_, _>>()?;
    let total: usize = lists.iter().map(Vec::len).sum();
    println!("\n== {module_name} {column}: {} terms, {total} postings", terms.len());

    // A. Dictionaries
    let mut array: Vec<u8> = Vec::new();
    let mut offset = 0u32;
    for term in &terms { array.extend(offset.to_le_bytes()); offset += term.len() as u32; }
    array.extend(offset.to_le_bytes());
    for term in &terms { array.extend(term.bytes()); }
    let transducer = fst::Map::from_iter(terms.iter().enumerate().map(|(id, term)| (term, id as u64)))?;
    let transducer_bytes = transducer.as_fst().as_bytes();
    println!("  dictionary size      array {:>10}   (zstd {:>9})    fst {:>10}   (zstd {:>9})", kilobytes(array.len()), kilobytes(zstd::encode_all(&array[..], 19)?.len()),
             kilobytes(transducer_bytes.len()), kilobytes(zstd::encode_all(transducer_bytes, 19)?.len()));

    let mut chooser = Chooser(1);
    let wanted: Vec<&str> = (0..10_000).map(|_| terms[chooser.next(terms.len())]).collect();
    let array_exact = time(5, || wanted.iter().filter_map(|term| dictionary.find(term)).sum::<usize>()) / wanted.len() as f64;
    let fst_exact = time(5, || wanted.iter().filter_map(|term| transducer.get(term)).sum::<u64>()) / wanted.len() as f64;
    println!("  exact lookup         array {:>10}                       fst {:>10}", duration(array_exact), duration(fst_exact));

    let prefixes: Vec<String> = wanted.iter().take(1000).map(|term| term.chars().take(3).collect()).collect();
    let array_prefix = time(5, || prefixes.iter().map(|prefix| dictionary.find_prefix(prefix).len()).sum::<usize>()) / prefixes.len() as f64;
    let fst_prefix = time(5, || prefixes.iter().map(|prefix| { let mut stream = transducer.search(Str::new(prefix).starts_with()).into_stream(); let mut count = 0; while stream.next().is_some() { count += 1; } count }).sum::<usize>()) / prefixes.len() as f64;
    println!("  3-letter prefix      array {:>10}                       fst {:>10}", duration(array_prefix), duration(fst_prefix));

    // Misspellings: every term within one or two edits. The array has no index for this, so it checks every term.
    let queries: Vec<&str> = wanted.iter().copied().filter(|term| term.chars().count() >= 4).take(100).collect();
    for limit in [1, 2] {
        let mut rows = (Vec::new(), Vec::new());
        let mut scan_found = 0;
        let scan = time(3, || { scan_found = 0; for query in &queries { let query: Vec<char> = query.chars().collect(); scan_found += terms.iter().filter(|term| within_distance(&query, term, limit, &mut rows)).count(); } }) / queries.len() as f64;
        let mut fst_found = 0;
        let builder = levenshtein_automata::LevenshteinAutomatonBuilder::new(limit as u8, false);
        let automaton = time(3, || { fst_found = 0; for query in &queries { let mut stream = transducer.search(Near(builder.build_dfa(query))).into_stream(); while stream.next().is_some() { fst_found += 1; } } }) / queries.len() as f64;
        assert_eq!(scan_found, fst_found, "the two ways of finding near matches disagree");
        println!("  within {limit} edit{}       scan  {:>10}                       fst {:>10}    ({:.1} matches each)", if limit == 1 { " " } else { "s" }, duration(scan), duration(automaton), fst_found as f64 / queries.len() as f64);
    }

    // B. Postings
    let packer = BitPacker4x::new();
    let (mut as_varints, mut as_blocks) = (Vec::new(), Vec::new());
    let (mut varint_starts, mut block_starts) = (vec![0], vec![0]);
    for list in &lists {
        varints(list, &mut as_varints); varint_starts.push(as_varints.len());
        blocks(&packer, list, &mut as_blocks); block_starts.push(as_blocks.len());
    }
    let long: usize = lists.iter().filter(|list| list.len() >= BLOCK).map(Vec::len).sum();
    println!("  postings size        varints {:>8}   (zstd {:>9})    blocks {:>7}   (zstd {:>9})   ({:.0}% of postings are in the {} lists of 128 or more)",
             kilobytes(as_varints.len()), kilobytes(zstd::encode_all(&as_varints[..], 19)?.len()), kilobytes(as_blocks.len()), kilobytes(zstd::encode_all(&as_blocks[..], 19)?.len()),
             100.0 * long as f64 / total as f64, lists.iter().filter(|list| list.len() >= BLOCK).count());
    let mut out: Vec<u32> = Vec::with_capacity(total);
    let decode_varints = time(5, || { out.clear(); for (id, list) in lists.iter().enumerate() { read_varints(&as_varints[varint_starts[id]..], list.len(), 0, &mut out); } out.len() });
    assert!(out.iter().eq(lists.iter().flatten()));
    let decode_blocks = time(5, || { out.clear(); for (id, list) in lists.iter().enumerate() { read_blocks(&packer, &as_blocks[block_starts[id]..], list.len(), &mut out); } out.len() });
    assert!(out.iter().eq(lists.iter().flatten()));
    println!("  decode every list    varints {:>8}                       blocks {:>7}", duration(decode_varints), duration(decode_blocks));
    let longest = (0..lists.len()).max_by_key(|&id| lists[id].len()).unwrap();
    let one_varints = time(20, || { out.clear(); read_varints(&as_varints[varint_starts[longest]..], lists[longest].len(), 0, &mut out); out.len() });
    let one_blocks = time(20, || { out.clear(); read_blocks(&packer, &as_blocks[block_starts[longest]..], lists[longest].len(), &mut out); out.len() });
    println!("  decode the longest   varints {:>8}                       blocks {:>7}   (‘{}’, {} postings)", duration(one_varints), duration(one_blocks), terms[longest], lists[longest].len());
    Ok(())
}

fn folder_sizes(folder: &Path) -> Vec<(String, u64)> {
    let mut sizes: std::collections::BTreeMap<String, u64> = Default::default();
    for entry in std::fs::read_dir(folder).into_iter().flatten().flatten() {
        let extension = entry.path().extension().map_or("(other)".to_string(), |extension| extension.to_string_lossy().into_owned());
        *sizes.entry(extension).or_default() += entry.metadata().map_or(0, |metadata| metadata.len());
    }
    sizes.into_iter().collect()
}

/// C. Index the same words with Tantivy (one document for each verse, positions kept, nothing stored) and ask the same things
fn compare_tantivy(modules: &Path, edition: &str) -> Result<()> {
    use tantivy::collector::{Count, DocSetCollector};
    use tantivy::query::{BooleanQuery, Occur, PhraseQuery, Query, TermQuery};
    use tantivy::schema::{IndexRecordOption, Schema, TextFieldIndexing, TextOptions};
    use tantivy::{doc, Index, Term};

    let module = Module::open_file(&modules.join(format!("{edition}.text.blm")))?;
    let norm = Column::open(&module, "col.norm")?;
    let verses = Nodes::open(&module, "verse")?;
    println!("\n== Tantivy: {edition}, {} verses", verses.starts.len());

    let mut schema = Schema::builder();
    let field = schema.add_text_field("text", TextOptions::default().set_indexing_options(TextFieldIndexing::default().set_tokenizer("whitespace").set_index_option(IndexRecordOption::WithFreqsAndPositions)));
    let folder = std::env::temp_dir().join(format!("biblelastic-bench-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&folder);
    std::fs::create_dir_all(&folder)?;
    let index = Index::create_in_dir(&folder, schema.build())?;
    let started = Instant::now();
    let mut writer = index.writer_with_num_threads(1, 200_000_000)?;
    for verse in 0..verses.starts.len() {
        let words: Vec<String> = verses.range(verse).map(|slot| norm.get(slot)).filter(|word| !word.is_empty()).collect();
        writer.add_document(doc!(field => words.join(" ")))?;
    }
    writer.commit()?;
    let segments = index.searchable_segment_ids()?;
    if segments.len() > 1 { writer.merge(&segments).wait()?; }
    writer.garbage_collect_files().wait()?;
    drop(writer);
    println!("  built in {:.2} s", started.elapsed().as_secs_f64());

    let sizes = folder_sizes(&folder);
    println!("  Tantivy index: {}   ({})", kilobytes(sizes.iter().map(|(_, size)| *size as usize).sum()), sizes.iter().map(|(extension, size)| format!(".{extension} {}", kilobytes(*size as usize))).collect::<Vec<_>>().join(", "));
    let ours: Vec<(&str, u64)> = module.entries().iter().filter(|entry| entry.name.starts_with("col.norm.dict") || entry.name.starts_with("col.norm.post") || entry.name.starts_with("node.verse.starts") || entry.name.starts_with("node.verse.ends"))
        .map(|entry| (entry.name.as_str(), entry.length)).collect();
    println!("  Our equivalent: {}   ({})", kilobytes(ours.iter().map(|(_, size)| *size as usize).sum()), ours.iter().map(|(name, size)| format!("{name} {}", kilobytes(*size as usize))).collect::<Vec<_>>().join(", "));

    let reader = index.reader()?;
    let searcher = reader.searcher();
    let term = |word: &str| Term::from_field_text(field, word);
    let term_query = |word: &str| -> Box<dyn Query> { Box::new(TermQuery::new(term(word), IndexRecordOption::Basic)) };
    let our_verses = |words: &[&str]| -> usize {
        let mut common: Option<Vec<usize>> = None;
        for word in words {
            let (slots, _) = find_terms(&module, "col.norm", &[word.to_string()]).unwrap();
            let mut containing: Vec<usize> = slots.into_iter().filter_map(|slot| verses.containing(slot)).collect();
            containing.dedup();
            common = Some(match common { Some(previous) => previous.into_iter().filter(|verse| containing.binary_search(verse).is_ok()).collect(), None => containing });
        }
        common.map_or(0, |verses| verses.len())
    };
    for words in [&["love"][..], &["the"], &["grace", "truth"], &["love", "god"]] {
        let query: Box<dyn Query> = if words.len() == 1 { term_query(words[0]) } else { Box::new(BooleanQuery::new(words.iter().map(|word| (Occur::Must, term_query(word))).collect())) };
        let mut counted = 0;
        let count_time = time(20, || { counted = searcher.search(&query, &Count).unwrap(); counted });
        let list_time = time(20, || searcher.search(&query, &DocSetCollector).unwrap().len());
        let mut ours_counted = 0;
        let ours_time = time(20, || { ours_counted = our_verses(words); ours_counted });
        assert_eq!(counted, ours_counted, "the two engines disagree about {words:?}");
        println!("  verses with {:<16} {:>6} verses    Tantivy count {:>9}, list {:>9}    ours (list) {:>9}", words.join(" + "), counted, duration(count_time), duration(list_time), duration(ours_time));
    }
    // A phrase, which our engine has no query for yet (its postings are positions, so it could)
    let phrase = PhraseQuery::new(vec![term("the"), term("messiah")]);
    let mut counted = 0;
    let phrase_time = time(20, || { counted = searcher.search(&phrase, &Count).unwrap(); counted });
    println!("  ‘the messiah’ (as a phrase)  {:>6} verses    Tantivy count {:>9}                    ours: not written yet", counted, duration(phrase_time));
    std::fs::remove_dir_all(&folder)?;
    Ok(())
}

fn main() -> Result<()> {
    let modules = PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| "build/modules".to_string()));
    for (module, column) in [("OET-RV.text", "norm"), ("UHB.text", "norm"), ("UHB.morph", "lemma"), ("SR-GNT.morph", "lemma")] { compare_column(&modules, module, column)?; }
    compare_tantivy(&modules, "OET-RV")
}
