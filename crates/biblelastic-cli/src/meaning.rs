//! Meaning-based search, at build time: converting a sentence-embedding model into a module (`biblelastic model`),
//! and making the vectors of the passages of installed works with it (`biblelastic embed`). See the engine's `meaning.rs`.

use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use biblelastic_engine::format::{Module, Result};
use biblelastic_engine::library::{Folder, Library};
use biblelastic_engine::meaning::{quantise, write_model, Model, Unigram};
use biblelastic_engine::library::Text;
use biblelastic_engine::query::{self, Piece, Wanted};

use crate::compile::Options;

/// Passages are runs of paragraphs (within one section of Scripture, or one entry of a commentary, dictionary, or book) of about this many words
const MIN_WORDS: usize = 80;
const MAX_WORDS: usize = 200;

/// The models that `biblelastic model` knows: (a part of the folder's name, the model's name, query prefix, passage prefix, language of the works that it's for, licence)
const KNOWN_MODELS: [(&str, &str, &str, &str, &str, &str); 2] = [
    ("bge-small-en-v1.5", "bge-small-en-v1.5", "Represent this sentence for searching relevant passages: ", "", "eng", "MIT"),
    ("multilingual-e5-small", "multilingual-e5-small", "query: ", "passage: ", "spa", "MIT"),
];

/// Convert a Hugging Face BERT sentence-embedding model (a folder with `config.json`, `model.safetensors`, `1_Pooling/config.json`, and either
/// `vocab.txt` for a WordPiece tokenizer or `tokenizer.json` for a unigram one) into a module. It must be one of KNOWN_MODELS.
/// A unigram tokenizer for many languages (e.g., multilingual e5's 250,000 pieces) is trimmed to the pieces that the installed works in English and Spanish use
/// (and the single characters of most scripts), which is most of the model's size.
pub fn convert_model(folder: &Path, modules: &Path, options: Options) -> Result<()> {
    let folder_name = folder.to_string_lossy();
    let &(_, name, query_prefix, passage_prefix, language, licence) = KNOWN_MODELS.iter().find(|known| folder_name.contains(known.0))
        .ok_or_else(|| format!("not a model that's known (one of {})", KNOWN_MODELS.map(|known| known.0).join(", ")))?;
    let read = |file: &str| fs::read(folder.join(file)).map_err(|error| format!("{}: {error}", folder.join(file).display()));
    let config = Json::parse(&String::from_utf8(read("config.json")?)?)?;
    let number = |key: &str| config.get(key).and_then(Json::number).map(|value| value as usize).ok_or_else(|| format!("config.json has no {key}"));
    if config.get("model_type").and_then(Json::text) != Some("bert") { return Err("only BERT models are supported".into()); }
    let pooling = Json::parse(&String::from_utf8(read("1_Pooling/config.json")?)?)?;
    let pooling = if matches!(pooling.get("pooling_mode_cls_token"), Some(Json::Bool(true))) { "cls" }
        else if matches!(pooling.get("pooling_mode_mean_tokens"), Some(Json::Bool(true))) { "mean" } else { return Err("only cls or mean pooling is supported".into()) };
    let mut tensors = read_safetensors(&read("model.safetensors")?)?;
    let (tokenizer, vocab, scores) = if folder.join("vocab.txt").exists() {
        ("wordpiece", String::from_utf8(read("vocab.txt")?)?.lines().map(str::to_string).collect::<Vec<_>>(), Vec::new())
    } else {
        let tokenizer = Json::parse(&String::from_utf8(read("tokenizer.json")?)?)?;
        let model = tokenizer.get("model").ok_or("tokenizer.json has no model")?;
        if model.get("type").and_then(Json::text) != Some("Unigram") { return Err("only WordPiece (vocab.txt) and Unigram tokenizers are supported".into()); }
        let Some(Json::Array(entries)) = model.get("vocab") else { return Err("tokenizer.json has no vocab".into()) };
        let pieces: Vec<(String, f32)> = entries.iter().filter_map(|entry| match entry {
            Json::Array(pair) if pair.len() == 2 => Some((pair[0].text()?.to_string(), pair[1].number()? as f32)), _ => None }).collect();
        let kept = used_pieces(&pieces, modules)?;
        println!("Keeping {} of the tokenizer's {} pieces", kept.len(), pieces.len());
        // The word embeddings of the pieces that are kept, in the same order
        let words = tensors.get_mut("embeddings.word_embeddings.weight").ok_or("the model has no word embeddings")?;
        let width = words.0[1];
        words.1 = kept.iter().flat_map(|&id| words.1[id * width..(id + 1) * width].to_vec()).collect();
        words.0[0] = kept.len();
        ("unigram", kept.iter().map(|&id| pieces[id].0.clone()).collect(), kept.iter().map(|&id| pieces[id].1).collect())
    };
    let settings = [("layers", number("num_hidden_layers")?.to_string()), ("hidden", number("hidden_size")?.to_string()), ("heads", number("num_attention_heads")?.to_string()),
        ("intermediate", number("intermediate_size")?.to_string()), ("max_tokens", number("max_position_embeddings")?.to_string()), ("pooling", pooling.to_string()),
        ("tokenizer", tokenizer.to_string()), ("query_prefix", query_prefix.to_string()), ("passage_prefix", passage_prefix.to_string())];
    let mut writer = options.writer();
    writer.raw("module.kind", b"model");
    writer.raw("module.edition", name.as_bytes());
    writer.raw("module.title", name.as_bytes());
    writer.raw("module.language", language.as_bytes());
    writer.raw("manifest", format!("{{\"id\": \"{name}\", \"kind\": \"model\", \"licence\": \"{licence}\", \"source\": \"{}\"}}", folder.display()).as_bytes());
    write_model(&mut writer, &settings, &vocab, &scores, &tensors)?;
    let path = modules.join(format!("{name}.model.blm"));
    fs::write(&path, writer.finish()).map_err(|error| format!("{}: {error}", path.display()))?;
    println!("{} ({:.1} MB)", path.display(), fs::metadata(&path)?.len() as f64 / 1048576.0);
    write_index(modules)
}

/// The ids of a unigram tokenizer's pieces that the installed works in English and Spanish use (with the special pieces, and the single characters of most scripts),
/// in order. Words are cut into pieces in the same way whichever other pieces there are, so the works' texts come out the same with only these.
fn used_pieces(pieces: &[(String, f32)], modules: &Path) -> Result<Vec<usize>> {
    let tokenizer = Unigram::new(pieces.to_vec());
    let library = Library::open(&Folder(modules.to_path_buf()))?;
    let mut words = std::collections::HashSet::new();
    for installed in library.modules.iter().filter(|installed| installed.kind == "text" && matches!(installed.language.as_str(), "eng" | "spa")) {
        let text = Text::open(&installed.module)?;
        let mut line = String::new();
        for slot in 0..text.text.ids.len() as u32 {
            line.push_str(&text.before.get(slot)); line.push_str(&text.text.get(slot)); line.push_str(&text.after.get(slot));
            if line.len() > 10_000 { words.extend(normalised_words(&line)); line.clear(); }
        }
        words.extend(normalised_words(&line));
    }
    let mut used: std::collections::BTreeSet<usize> = pieces.iter().enumerate()
        // Every single character (and `▁` with one) of the scripts before the Chinese, Japanese, and Korean ones, so that no letter or symbol that a query might have is unknown
        .filter(|(_, (piece, _))| (piece.starts_with('<') && piece.ends_with('>'))
            || piece.trim_start_matches('▁').chars().count() == 1 && piece.trim_start_matches('▁').chars().all(|character| character < '\u{2E80}'))
        .map(|(id, _)| id).collect();
    for word in &words { used.extend(tokenizer.word(word).into_iter().map(|id| id as usize)); }
    Ok(used.into_iter().collect())
}

/// The words of some text, as the tokenizer will see them (normalised, and split at spaces), which may lose a word that crossed the end of a chunk: that doesn't matter here
fn normalised_words(text: &str) -> Vec<String> {
    // (The tokenizer normalises a whole text; here it's done to a chunk, through a query of one piece: the words are what's wanted)
    biblelastic_engine::meaning::normalise(text).split(' ').filter(|word| !word.is_empty()).map(str::to_string).collect()
}

/// The tensors of a `.safetensors` file (only 32-bit floats are kept): name → (shape, values)
fn read_safetensors(data: &[u8]) -> Result<HashMap<String, (Vec<usize>, Vec<f32>)>> {
    let length = u64::from_le_bytes(data.get(..8).ok_or("not a safetensors file")?.try_into()?) as usize;
    let header = Json::parse(std::str::from_utf8(&data[8..8 + length])?)?;
    let body = &data[8 + length..];
    let mut tensors = HashMap::new();
    let Json::Object(fields) = header else { return Err("the safetensors header isn't an object".into()); };
    for (name, field) in fields {
        if field.get("dtype").and_then(Json::text) != Some("F32") { continue; }
        let list = |key: &str| -> Vec<usize> { match field.get(key) { Some(Json::Array(items)) => items.iter().filter_map(Json::number).map(|value| value as usize).collect(), _ => Vec::new() } };
        let (shape, offsets) = (list("shape"), list("data_offsets"));
        if offsets.len() != 2 { return Err(format!("{name} has no data_offsets").into()); }
        let values = body[offsets[0]..offsets[1]].chunks_exact(4).map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]])).collect();
        tensors.insert(name, (shape, values));
    }
    Ok(tensors)
}

/// One passage to embed: where it is (a passage of Scripture, e.g., `JHN 3:16-3:21`, or an entry's locator), its heading or title, and its text
struct Passage {
    locator: String,
    label: String,
    text: String,
}

/// Make the vectors of the passages of these editions (all the installed works in the model's language, if none are named), into `EDITION.vectors.blm` modules.
/// Passages whose text hasn't changed keep the vectors that they already have.
pub fn embed(modules: &Path, editions: &[String], model_name: Option<&str>, options: Options) -> Result<()> {
    let library = Library::open(&Folder(modules.to_path_buf()))?;
    let models: Vec<_> = library.modules.iter().filter(|installed| installed.kind == "model" && model_name.is_none_or(|name| installed.edition == name)).collect();
    if models.is_empty() { return Err("no model is installed (make one with `biblelastic model`)".into()); }
    // Each work is embedded by the model for its language
    let wanted: Vec<_> = library.modules.iter().filter(|installed| installed.kind == "text" && installed.edition != "OET-LV"
        && models.iter().any(|model| model.language == installed.language) && (editions.is_empty() || editions.contains(&installed.edition))).collect();
    let mut opened: HashMap<String, Model> = HashMap::new();
    for installed in wanted {
        let model_module = models.iter().find(|model| model.language == installed.language).expect("chosen above");
        if !opened.contains_key(&model_module.edition) { opened.insert(model_module.edition.clone(), Model::open(&model_module.module, &model_module.edition)?); }
        let model = &opened[&model_module.edition];
        let started = Instant::now();
        let passages = if installed.work == "scripture" { scripture_passages(&library, &installed.edition)? } else { entry_passages(&library, &installed.edition)? };
        if passages.is_empty() { continue; }
        let path = modules.join(format!("{}.vectors.blm", installed.edition));
        // The vectors that an earlier run made, by the hash of what was embedded
        let mut earlier: HashMap<u64, Vec<f32>> = HashMap::new();
        if let Ok(old) = Module::open_file(&path) {
            if let (Ok(vectors), Ok(hashes)) = (biblelastic_engine::meaning::Vectors::open(&old), old.bytes("vectors.hashes")) {
                if vectors.model == model.name {
                    for (index, hash) in hashes.chunks_exact(8).enumerate() {
                        let row = &vectors.data[index * vectors.dimensions..(index + 1) * vectors.dimensions];
                        earlier.insert(u64::from_le_bytes(hash.try_into()?), row.iter().map(|&byte| byte as f32 * vectors.scale).collect());
                    }
                }
            }
        }
        let inputs: Vec<String> = passages.iter().map(|passage| if passage.label.is_empty() { passage.text.clone() } else { format!("{}. {}", passage.label, passage.text) }).collect();
        let hashes: Vec<u64> = inputs.iter().map(|input| hash(input)).collect();
        let next = AtomicUsize::new(0);
        let threads = std::thread::available_parallelism().map_or(4, |count| count.get());
        let mut vectors: Vec<Vec<f32>> = vec![Vec::new(); inputs.len()];
        let reused = hashes.iter().filter(|hash| earlier.contains_key(hash)).count();
        std::thread::scope(|scope| {
            let workers: Vec<_> = (0..threads).map(|_| scope.spawn(|| {
                let mut made = Vec::new();
                loop {
                    let index = next.fetch_add(1, Ordering::Relaxed);
                    if index >= inputs.len() { break; }
                    made.push((index, earlier.get(&hashes[index]).cloned().unwrap_or_else(|| model.embed_passage(&inputs[index]))));
                }
                made
            })).collect();
            for worker in workers { for (index, vector) in worker.join().expect("an embedding thread failed") { vectors[index] = vector; } }
        });
        let (scale, data) = quantise(&vectors);
        let mut writer = options.writer();
        writer.raw("module.kind", b"vectors");
        writer.raw("module.work", installed.work.as_bytes());
        writer.raw("module.edition", installed.edition.as_bytes());
        writer.raw("module.layer", b"vectors");
        writer.raw("module.title", installed.title.as_bytes());
        writer.raw("module.language", installed.language.as_bytes());
        writer.raw("vectors.config", format!("model={}\ndimensions={}\nscale={scale}\n", model.name, vectors[0].len()).as_bytes());
        writer.raw("vectors.data", &data);
        writer.raw("vectors.hashes", &hashes.iter().flat_map(|hash| hash.to_le_bytes()).collect::<Vec<u8>>());
        writer.strings("vectors.locators", &passages.iter().map(|passage| passage.locator.as_str()).collect::<Vec<_>>());
        writer.strings("vectors.labels", &passages.iter().map(|passage| passage.label.as_str()).collect::<Vec<_>>());
        writer.strings("vectors.texts", &passages.iter().map(|passage| passage.text.as_str()).collect::<Vec<_>>());
        fs::write(&path, writer.finish()).map_err(|error| format!("{}: {error}", path.display()))?;
        println!("{:<38} {:>6} passages ({} embedded, {reused} unchanged) in {:>6.1} s, {:>5.1} MB", format!("{}.vectors", installed.edition), passages.len(),
                 passages.len() - reused, started.elapsed().as_secs_f64(), fs::metadata(&path)?.len() as f64 / 1048576.0);
    }
    write_index(modules)
}

/// FNV-1a, which is enough to tell whether a passage's text has changed
fn hash(text: &str) -> u64 { text.bytes().fold(0xcbf2_9ce4_8422_2325, |hash, byte| (hash ^ byte as u64).wrapping_mul(0x0100_0000_01b3)) }

/// Cut paragraphs (each with its words) into passages of about MIN_WORDS to MAX_WORDS words
fn runs<T: Clone>(paragraphs: &[(T, usize)]) -> Vec<Vec<T>> {
    let (mut runs, mut run, mut words) = (Vec::new(), Vec::new(), 0);
    for (paragraph, count) in paragraphs {
        if !run.is_empty() && words + count > MAX_WORDS { runs.push(std::mem::take(&mut run)); words = 0; }
        run.push(paragraph.clone());
        words += count;
        if words >= MIN_WORDS { runs.push(std::mem::take(&mut run)); words = 0; }
    }
    if !run.is_empty() { runs.push(run); }
    runs
}

/// A Bible's passages: runs of the body paragraphs within each section, with the section's heading
fn scripture_passages(library: &Library, edition: &str) -> Result<Vec<Passage>> {
    let text = biblelastic_engine::library::Text::open(&*library.text_module(edition)?)?;
    let mut passages = Vec::new();
    for document in 0..text.document_names.len() {
        let name = text.document_names.get(document);
        for number in 1.. {
            let Ok(section) = query::read_section(library, edition, Wanted::Number(&name, number), false) else { break };
            if section.document != name { break; }
            // Each body paragraph: (its text, its first verse, its last verse), with its number of words
            let mut paragraphs = Vec::new();
            let mut verse: Option<String> = None;
            for paragraph in section.paragraphs.iter().filter(|paragraph| paragraph.kind == "body") {
                // The paragraph's text, verse by verse
                let mut verses: Vec<(String, String)> = Vec::new();
                for piece in &paragraph.pieces {
                    match piece {
                        Piece::Verse(name) => { verse = Some(name.clone()); }
                        Piece::Text(piece, _, _) => {
                            let Some(current) = &verse else { continue };
                            match verses.last_mut() { Some((name, text)) if name == current => text.push_str(piece), _ => verses.push((current.clone(), piece.clone())) }
                        }
                        Piece::Chapter(_) => {}
                    }
                }
                let count = |text: &str| text.split_whitespace().count();
                let total: usize = verses.iter().map(|(_, text)| count(text)).sum();
                if total == 0 { continue; }
                if total > MAX_WORDS { // A very long paragraph (e.g., a whole chapter, as the RV1909 has them) is cut between verses
                    for (name, text) in verses { if count(&text) > 0 { paragraphs.push(((text.trim().to_string(), name.clone(), name), count(&text))); } }
                } else {
                    let text = verses.iter().map(|(_, text)| text.as_str()).collect::<String>();
                    paragraphs.push(((text.trim().to_string(), verses[0].0.clone(), verses[verses.len() - 1].0.clone()), total));
                }
            }
            for run in runs(&paragraphs) {
                // A combined verse's name is a range (e.g., `1:6-7`): the passage starts at its first verse and ends at its last
                let first = run[0].1.split('-').next().unwrap_or_default().to_string();
                let last = run[run.len() - 1].2.clone();
                let last = match last.split_once('-') { Some((start, end)) => format!("{}:{end}", start.split(':').next().unwrap_or_default()), None => last };
                let (first, last) = (&first, &last);
                passages.push(Passage { locator: format!("{name} {}", if first == last { first.clone() } else { format!("{first}-{last}") }),
                                        label: section.title.clone(), text: run.iter().map(|(text, _, _)| text.as_str()).collect::<Vec<_>>().join(" ") });
            }
            if section.next.is_none() { break; }
        }
    }
    Ok(passages)
}

/// The passages of a commentary, dictionary, or book: runs of the paragraphs of each entry, with its title (and the heading that they're under)
fn entry_passages(library: &Library, edition: &str) -> Result<Vec<Passage>> {
    let mut passages = Vec::new();
    for (locator, title, _kind) in query::contents_of(library, edition)? {
        let Ok(article) = query::article(library, Some(edition), &locator) else { continue };
        // Body paragraphs, each with the heading that it's under
        let (mut paragraphs, mut heading) = (Vec::new(), String::new());
        for (_style, kind, text) in &article.paragraphs {
            // (A heading that's only the entry's title again, perhaps without its number, isn't added to it)
            if kind == "heading" { heading = if title.to_lowercase().contains(&text.trim().to_lowercase()) { String::new() } else { text.trim().to_string() }; continue; }
            let count = text.split_whitespace().count();
            if count > 0 { paragraphs.push(((text.trim().to_string(), heading.clone()), count)); }
        }
        for run in runs(&paragraphs) {
            let heading = &run[0].1;
            let label = [title.trim(), heading.as_str()].iter().filter(|part| !part.is_empty()).copied().collect::<Vec<_>>().join(": ");
            passages.push(Passage { locator: locator.clone(), label, text: run.iter().map(|(text, _)| text.as_str()).collect::<Vec<_>>().join(" ") });
        }
    }
    Ok(passages)
}

/// The catalogue that an installer downloads first, to see what there is: every module in the folder
pub fn write_index(output: &Path) -> Result<()> {
    let mut modules: Vec<(String, u64)> = fs::read_dir(output)?.flatten()
        .filter_map(|entry| Some((entry.file_name().to_string_lossy().strip_suffix(".blm")?.to_string(), entry.metadata().ok()?.len()))).collect();
    modules.sort();
    let entries: Vec<String> = modules.iter().map(|(name, bytes)| format!("    {{\"name\": \"{name}\", \"bytes\": {bytes}}}")).collect();
    let catalogue = format!("{{\n  \"format\": {},\n  \"modules\": [\n{}\n  ]\n}}\n", biblelastic_engine::format::FORMAT_VERSION, entries.join(",\n"));
    fs::write(output.join("index.json"), catalogue).map_err(|error| format!("{}: {error}", output.display()).into())
}

/// Just enough JSON for a model's configuration and a safetensors header
enum Json {
    Null,
    Bool(bool),
    Number(f64),
    Text(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    fn parse(text: &str) -> Result<Json> {
        let characters: Vec<char> = text.chars().collect();
        let mut position = 0;
        let value = Json::value(&characters, &mut position)?;
        Ok(value)
    }

    fn get(&self, key: &str) -> Option<&Json> { match self { Json::Object(fields) => fields.iter().find(|(name, _)| name == key).map(|(_, value)| value), _ => None } }
    fn number(&self) -> Option<f64> { match self { Json::Number(value) => Some(*value), _ => None } }
    fn text(&self) -> Option<&str> { match self { Json::Text(value) => Some(value), _ => None } }

    fn value(characters: &[char], position: &mut usize) -> Result<Json> {
        let skip = |position: &mut usize| while *position < characters.len() && characters[*position].is_whitespace() { *position += 1; };
        skip(position);
        let character = *characters.get(*position).ok_or("unexpected end of JSON")?;
        match character {
            '{' | '[' => {
                *position += 1;
                let (mut fields, mut items) = (Vec::new(), Vec::new());
                loop {
                    skip(position);
                    if characters.get(*position) == Some(&if character == '{' { '}' } else { ']' }) { *position += 1; break; }
                    if character == '{' {
                        let Json::Text(key) = Json::value(characters, position)? else { return Err("a JSON key must be a string".into()) };
                        skip(position);
                        if characters.get(*position) != Some(&':') { return Err("expected : in JSON".into()); }
                        *position += 1;
                        fields.push((key, Json::value(characters, position)?));
                    } else { items.push(Json::value(characters, position)?); }
                    skip(position);
                    if characters.get(*position) == Some(&',') { *position += 1; }
                }
                Ok(if character == '{' { Json::Object(fields) } else { Json::Array(items) })
            }
            '"' => {
                *position += 1;
                let mut text = String::new();
                while let Some(&next) = characters.get(*position) {
                    *position += 1;
                    match next {
                        '"' => return Ok(Json::Text(text)),
                        '\\' => {
                            let escaped = *characters.get(*position).ok_or("unexpected end of JSON")?;
                            *position += 1;
                            match escaped {
                                'n' => text.push('\n'), 't' => text.push('\t'), 'r' => text.push('\r'), 'b' => text.push('\u{8}'), 'f' => text.push('\u{c}'),
                                'u' => {
                                    let hex: String = characters.get(*position..*position + 4).ok_or("bad \\u in JSON")?.iter().collect();
                                    *position += 4;
                                    text.push(char::from_u32(u32::from_str_radix(&hex, 16)?).unwrap_or('\u{FFFD}'));
                                }
                                other => text.push(other),
                            }
                        }
                        other => text.push(other),
                    }
                }
                Err("unterminated string in JSON".into())
            }
            't' | 'f' | 'n' => {
                let word: String = characters[*position..].iter().take_while(|character| character.is_ascii_alphabetic()).collect();
                *position += word.len();
                match word.as_str() { "true" => Ok(Json::Bool(true)), "false" => Ok(Json::Bool(false)), "null" => Ok(Json::Null), _ => Err(format!("unexpected '{word}' in JSON").into()) }
            }
            _ => {
                let number: String = characters[*position..].iter().take_while(|character| character.is_ascii_digit() || "+-.eE".contains(**character)).collect();
                *position += number.len();
                Ok(Json::Number(number.parse().map_err(|_| format!("unexpected '{character}' in JSON"))?))
            }
        }
    }
}
