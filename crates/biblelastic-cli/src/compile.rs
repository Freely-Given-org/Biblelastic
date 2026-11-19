//! Compiles the intermediate format (docs/IntermediateFormat.md) into modules (docs/ModuleFormat.md).

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::{Path, PathBuf};

use biblelastic_engine::format::{ModuleWriter, DEFAULT_PAGE_BITS};
use biblelastic_engine::reference::{pack, Passage};

type Result<T> = std::result::Result<T, String>;

#[derive(Clone, Copy)]
pub struct Options {
    /// Pages are 2^this bytes
    pub page_bits: u8,
    /// Compress the sections that it helps (with zstd)
    pub compress: bool,
}

impl Default for Options { fn default() -> Self { Options { page_bits: DEFAULT_PAGE_BITS, compress: true } } }

impl Options {
    fn writer(self) -> ModuleWriter {
        // Each page is a frame of its own, so that any page can be read without the others
        ModuleWriter::with(self.page_bits, self.compress.then(|| Box::new(|page: &[u8]| zstd::bulk::compress(page, 19).expect("zstd compression")) as _))
    }
}

/// Which module each token column goes into, and whether it gets a search index.
/// (Provisional: this should come from the source registry rather than being fixed here.)
#[derive(Clone, Copy, PartialEq)]
enum Index { None, Whole, Split(char) }

fn token_column_plan(column: &str) -> Option<(&'static str, Index)> {
    match column {
        "before" | "text" | "after" => Some(("text", Index::None)),
        "norm" => Some(("text", Index::Whole)),
        "row" | "oet_row" => None, // Only needed for building the alignments
        "lemma" | "strong" | "morph" | "cons" | "translit" | "lemma_translit" => Some(("morph", Index::Whole)),
        _ => Some(("morph", Index::None)),
    }
}

/// Columns of several values (separated by semicolons) get an index of each value: tags, semantic domains, and handbook articles
fn layer_column_plan(column: &str) -> Index { if matches!(column, "tags" | "domains" | "handbook") { Index::Split(';') } else { Index::None } }

/// A feature column while it's being read: each distinct value is given a number as it's first seen
#[derive(Default)]
struct Interned {
    numbers: HashMap<String, u32>,
    ids: Vec<u32>,
}

impl Interned {
    fn push(&mut self, value: &str) {
        let next = self.numbers.len() as u32;
        let id = match self.numbers.get(value) { Some(&id) => id, None => { self.numbers.insert(value.to_string(), next); next } };
        self.ids.push(id);
    }

    /// Writes `<prefix>.dict` (sorted) and `<prefix>.ids`, and any index that was asked for
    fn write(self, writer: &mut ModuleWriter, prefix: &str, index: Index) {
        let mut dictionary: Vec<(String, u32)> = self.numbers.into_iter().collect();
        dictionary.sort();
        let mut new_ids = vec![0u32; dictionary.len()];
        for (new_id, (_, old_id)) in dictionary.iter().enumerate() { new_ids[*old_id as usize] = new_id as u32; }
        let ids: Vec<u32> = self.ids.iter().map(|&old_id| new_ids[old_id as usize]).collect();
        let strings: Vec<&str> = dictionary.iter().map(|(string, _)| string.as_str()).collect();
        writer.strings(&format!("{prefix}.dict"), &strings);
        writer.packed(&format!("{prefix}.ids"), &ids);
        match index {
            Index::None => {}
            Index::Whole => {
                let mut lists = vec![Vec::new(); strings.len()];
                for (slot, &id) in ids.iter().enumerate() { lists[id as usize].push(slot as u32); }
                writer.postings(&format!("{prefix}.post"), &lists);
            }
            Index::Split(separator) => { // An index of the separate values, e.g., of each tag
                let mut lists: BTreeMap<&str, Vec<u32>> = BTreeMap::new();
                for (slot, &id) in ids.iter().enumerate() {
                    let parts: BTreeSet<&str> = strings[id as usize].split(separator).filter(|part| !part.is_empty()).collect();
                    for part in parts { lists.entry(part).or_default().push(slot as u32); }
                }
                let index_prefix = prefix.replacen("col.", "idx.", 1);
                writer.strings(&format!("{index_prefix}.dict"), &lists.keys().collect::<Vec<_>>());
                writer.postings(&format!("{index_prefix}.post"), &lists.into_values().collect::<Vec<_>>());
            }
        }
    }
}

fn read_tsv(path: &Path) -> Result<(Vec<String>, Vec<Vec<String>>)> {
    let content = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let mut lines = content.strip_suffix('\n').unwrap_or(&content).split('\n'); // A row can be an empty line (one empty field)
    let header: Vec<String> = lines.next().ok_or_else(|| format!("{} is empty", path.display()))?.split('\t').map(str::to_string).collect();
    let rows: Vec<Vec<String>> = lines.map(|line| line.split('\t').map(str::to_string).collect()).collect();
    if let Some(row) = rows.iter().position(|row| row.len() != header.len()) {
        return Err(format!("{} row {} has {} fields, not {}", path.display(), row + 1, rows[row].len(), header.len()));
    }
    Ok((header, rows))
}

fn subfolders(folder: &Path) -> Vec<PathBuf> {
    let mut found: Vec<PathBuf> = fs::read_dir(folder).into_iter().flatten().flatten().map(|entry| entry.path()).filter(|path| path.is_dir()).collect();
    found.sort();
    found
}

fn file_name(path: &Path) -> String { path.file_name().unwrap_or_default().to_string_lossy().into_owned() }

pub struct Written {
    pub name: String,
    pub bytes: u64,
    pub sections: usize,
}

struct Edition {
    id: String,
    document_starts: HashMap<String, u32>,
    written: Vec<Written>,
    slots: usize,
}

/// The entries of a commentary or dictionary (its study notes, articles, etc.), the Scripture passages they're anchored to,
/// and the links between them
#[derive(Default)]
struct Items {
    starts: Vec<u32>,
    ends: Vec<u32>,
    names: Interned,
    types: Interned,
    titles: Interned,
    /// Lower-case `DOCUMENT NAME` → the entry's number
    locations: HashMap<String, u32>,
    /// The words of each title → the entries that have them
    title_words: BTreeMap<String, Vec<u32>>,
    /// (passage, kind, first slot, end slot)
    anchors: Vec<(Passage, u32, u32, u32)>,
    /// (first slot, end slot, kind, target location)
    links: Vec<(u32, u32, u32, String)>,
}

impl Items {
    /// Read one document's entries, anchors, and links (`start` is the document's first slot)
    fn read(&mut self, id: &str, folder: &Path, document: &str, start: u32) -> Result<()> {
        let file = |kind: &str| folder.join("documents").join(format!("{document}.{kind}.tsv"));
        let slot = |field: &String| field.parse::<u32>().map(|value| value + start).map_err(|_| format!("{id} {document}: bad position '{field}'"));
        if !file("entries").exists() { return Ok(()); }
        for row in read_tsv(&file("entries"))?.1 { // start, end, name, type, title
            let entry = self.starts.len() as u32;
            self.starts.push(slot(&row[0])?);
            self.ends.push(slot(&row[1])?);
            self.names.push(&row[2]);
            self.types.push(&row[3]);
            self.titles.push(&row[4]);
            self.locations.insert(format!("{document} {}", row[2]).to_lowercase(), entry);
            for word in biblelastic_engine::query::title_words(&row[4].replace('*', " ")) {
                let list = self.title_words.entry(word).or_default();
                if list.last() != Some(&entry) { list.push(entry); }
            }
        }
        for row in read_tsv(&file("anchors"))?.1 { // start, end, kind, reference
            let kind = match row[2].as_str() { "about" => 0, "cites" => 1, other => return Err(format!("{id} {document}: unknown kind of anchor '{other}'")) };
            let passage = Passage::parse(&row[3]).map_err(|error| format!("{id} {document}: {error}"))?;
            self.anchors.push((passage, kind, slot(&row[0])?, slot(&row[1])?));
        }
        for row in read_tsv(&file("links"))?.1 { // start, end, kind, target
            let kind = match row[2].as_str() { "see" => 0, "include" => 1, other => return Err(format!("{id} {document}: unknown kind of link '{other}'")) };
            self.links.push((slot(&row[0])?, slot(&row[1])?, kind, row[3].to_lowercase()));
        }
        Ok(())
    }

    fn write(mut self, writer: &mut ModuleWriter) {
        if self.starts.is_empty() { return; }
        let entry_at = |slot: u32| self.starts.partition_point(|&start| start <= slot).saturating_sub(1) as u32;
        writer.packed("node.entry.starts", &self.starts);
        writer.packed("node.entry.ends", &self.ends);
        self.names.write(writer, "node.entry.name", Index::None);
        self.types.write(writer, "node.entry.type", Index::None);
        self.titles.write(writer, "node.entry.title", Index::None);
        writer.strings("idx.entry.dict", &self.title_words.keys().collect::<Vec<_>>());
        writer.postings("idx.entry.post", &self.title_words.values().cloned().collect::<Vec<_>>());

        // Scripture anchors, in passage order. The books are numbered within this module, in the order of their codes.
        let books: Vec<String> = self.anchors.iter().map(|anchor| anchor.0.book.clone()).collect::<BTreeSet<_>>().into_iter().collect();
        let book_numbers: HashMap<&str, u32> = books.iter().enumerate().map(|(number, book)| (book.as_str(), number as u32)).collect();
        let mut anchors: Vec<[u32; 6]> = self.anchors.iter().map(|(passage, kind, start, end)| {
            let book = book_numbers[passage.book.as_str()];
            [pack(book, passage.from), pack(book, passage.to), *kind, *start, *end, entry_at(*start)]
        }).collect();
        anchors.sort_unstable();
        anchors.dedup();
        writer.strings("anchor.books", &books);
        for (field, name) in ["from", "to", "kind", "start", "end", "entry"].iter().enumerate() {
            writer.packed(&format!("anchor.{name}"), &anchors.iter().map(|anchor| anchor[field]).collect::<Vec<_>>());
        }

        // Links between entries, in slot order (the few that lead nowhere are dropped)
        self.links.sort();
        let links: Vec<[u32; 4]> = self.links.iter().filter_map(|(start, end, kind, target)| self.locations.get(target).map(|&entry| [*start, *end, *kind, entry])).collect();
        for (field, name) in ["start", "end", "kind", "target"].iter().enumerate() {
            writer.packed(&format!("link.{name}"), &links.iter().map(|link| link[field]).collect::<Vec<_>>());
        }
    }
}

/// A top-level text value from a manifest, as the ingest writes it (one key to a line, indented by one space)
fn manifest_value(manifest: &[u8], key: &str) -> Option<String> {
    let start = format!(" \"{key}\": \"");
    String::from_utf8_lossy(manifest).lines().find_map(|line| line.strip_prefix(&start).map(|rest| rest.trim_end_matches(',').trim_end_matches('"').to_string()))
}

fn save(output: &Path, name: &str, writer: ModuleWriter) -> Result<Written> {
    let bytes = writer.finish();
    let sections = biblelastic_engine::format::Module::open(Box::new(bytes.clone())).map_err(|error| error.to_string())?.entries().len();
    let path = output.join(format!("{name}.blm"));
    fs::write(&path, &bytes).map_err(|error| format!("{}: {error}", path.display()))?;
    Ok(Written { name: name.to_string(), bytes: bytes.len() as u64, sections })
}

/// The order that documents (and so search results) come in: front matter, New Testament, Old Testament,
/// then the deuterocanonical and other books. Anything not listed comes last, in alphabetical order.
const BOOK_ORDER: &[&str] = &[
    "FRT", "INT",
    "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "CO1", "CO2", "GAL", "EPH", "PHP", "COL", "TH1", "TH2", "TI1", "TI2", "TIT", "PHM", "HEB", "JAM", "PE1", "PE2",
    "JN1", "JN2", "JN3", "JDE", "REV",
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "SA1", "SA2", "KI1", "KI2", "CH1", "CH2", "EZR", "NEH", "EST", "JOB", "PSA", "PRO", "ECC", "SNG",
    "ISA", "JER", "LAM", "EZE", "DAN", "HOS", "JOL", "AMO", "OBA", "JNA", "MIC", "NAH", "HAB", "ZEP", "HAG", "ZEC", "MAL",
    "TOB", "JDT", "ESG", "WIS", "SIR", "BAR", "LJE", "DAG", "PAZ", "SUS", "BEL", "MA1", "MA2", "MA3", "MA4", "ES1", "ES2", "MAN", "PS2", "PSS", "ODE", "LAO",
];

fn compile_edition(folder: &Path, output: &Path, options: Options) -> Result<Edition> {
    let id = file_name(folder);
    let manifest = fs::read(folder.join("manifest.json")).map_err(|error| format!("{id}: manifest.json: {error}"))?;
    let mut documents: Vec<String> = fs::read_dir(folder.join("documents")).map_err(|error| format!("{id}: {error}"))?.flatten()
        .filter_map(|entry| file_name(&entry.path()).strip_suffix(".tokens.tsv").map(str::to_string)).collect();
    documents.sort_by_key(|document| (BOOK_ORDER.iter().position(|book| book == document).unwrap_or(usize::MAX), document.clone()));
    let layer_folders = subfolders(&folder.join("layers"));

    let mut token_header: Vec<String> = Vec::new();
    let mut token_columns: Vec<Interned> = Vec::new();
    let mut layer_headers: Vec<Vec<String>> = vec![Vec::new(); layer_folders.len()];
    let mut layer_columns: Vec<Vec<Interned>> = layer_folders.iter().map(|_| Vec::new()).collect();
    let mut nodes: BTreeMap<String, (Vec<u32>, Vec<u32>, Interned, Interned)> = BTreeMap::new();
    let mut starts = vec![0u32];
    let mut items = Items::default();
    for document in &documents {
        let start = *starts.last().unwrap();
        items.read(&id, folder, document, start)?;
        let (header, rows) = read_tsv(&folder.join("documents").join(format!("{document}.tokens.tsv")))?;
        if token_header.is_empty() { token_columns = header.iter().map(|_| Interned::default()).collect(); token_header = header; }
        else if header != token_header { return Err(format!("{id} {document}: token columns differ from the other documents")); }
        for row in &rows { for (column, value) in token_columns.iter_mut().zip(row) { column.push(value); } }

        for (n, layer_folder) in layer_folders.iter().enumerate() {
            let path = layer_folder.join(format!("{document}.features.tsv"));
            if !path.exists() { continue; } // e.g., a layer that only has variants
            let (header, layer_rows) = read_tsv(&path)?;
            if layer_rows.len() != rows.len() { return Err(format!("{}: {} rows for {} tokens", path.display(), layer_rows.len(), rows.len())); }
            if layer_headers[n].is_empty() { layer_columns[n] = header.iter().map(|_| Interned::default()).collect(); layer_headers[n] = header; }
            if layer_columns[n][0].ids.len() != start as usize { return Err(format!("{}: earlier documents are missing from this layer", path.display())); }
            for row in &layer_rows { for (column, value) in layer_columns[n].iter_mut().zip(row) { column.push(value); } }
        }

        let (_, node_rows) = read_tsv(&folder.join("documents").join(format!("{document}.nodes.tsv")))?;
        for row in &node_rows { // type, start, end, name, attributes
            let number = |field: &String| field.parse::<u32>().map(|value| value + start).map_err(|_| format!("{id} {document}: bad node position '{field}'"));
            let entry = nodes.entry(row[0].clone()).or_default();
            entry.0.push(number(&row[1])?);
            entry.1.push(number(&row[2])?);
            entry.2.push(&row[3]);
            entry.3.push(&row[4]);
        }
        starts.push(start + rows.len() as u32);
    }
    let slots = *starts.last().unwrap() as usize;

    let work = manifest_value(&manifest, "kind").unwrap_or_else(|| "scripture".to_string());
    let new_module = |layer: &str, kind: &str| {
        let mut writer = options.writer();
        writer.raw("module.kind", kind.as_bytes());
        writer.raw("module.work", work.as_bytes());
        writer.raw("module.edition", id.as_bytes());
        writer.raw("module.layer", layer.as_bytes());
        writer.raw("manifest", &manifest);
        writer.strings("documents.names", &documents);
        writer.packed("documents.starts", &starts);
        writer
    };
    let mut written = Vec::new();

    let mut text = new_module("text", "text");
    let mut morph = new_module("morph", "features");
    let mut has_morph = false;
    for (name, column) in token_header.iter().zip(token_columns) {
        match token_column_plan(name) {
            Some(("text", index)) => column.write(&mut text, &format!("col.{name}"), index),
            Some((_, index)) => { column.write(&mut morph, &format!("col.{name}"), index); has_morph = true; }
            None => {}
        }
    }
    for (node_type, (node_starts, node_ends, names, attributes)) in nodes {
        text.packed(&format!("node.{node_type}.starts"), &node_starts);
        text.packed(&format!("node.{node_type}.ends"), &node_ends);
        names.write(&mut text, &format!("node.{node_type}.name"), Index::None);
        attributes.write(&mut text, &format!("node.{node_type}.attributes"), Index::None);
    }
    items.write(&mut text);
    written.push(save(output, &format!("{id}.text"), text)?);
    if has_morph { written.push(save(output, &format!("{id}.morph"), morph)?); }

    for ((layer_folder, header), columns) in layer_folders.iter().zip(layer_headers).zip(layer_columns) {
        if header.is_empty() { continue; }
        let layer = file_name(layer_folder);
        let mut writer = new_module(&layer, "features");
        for (name, column) in header.iter().zip(columns) {
            if column.ids.len() != slots { return Err(format!("{id} layer {layer}: {} rows for {slots} tokens", column.ids.len())); }
            column.write(&mut writer, &format!("col.{name}"), layer_column_plan(name));
        }
        written.push(save(output, &format!("{id}.{layer}"), writer)?);
    }
    Ok(Edition { document_starts: documents.into_iter().zip(starts).collect(), id, written, slots })
}

fn compile_alignment(folder: &Path, editions: &[Edition], output: &Path, options: Options) -> Result<Option<Written>> {
    let name = file_name(folder);
    let (from_id, to_id) = name.split_once("--").ok_or_else(|| format!("alignment folder '{name}' isn't named FROM--TO"))?;
    let (Some(from), Some(to)) = (editions.iter().find(|edition| edition.id == from_id), editions.iter().find(|edition| edition.id == to_id)) else { return Ok(None) };
    let mut links: Vec<(u32, u32)> = Vec::new();
    let mut files: Vec<PathBuf> = fs::read_dir(folder).map_err(|error| error.to_string())?.flatten().map(|entry| entry.path()).collect();
    files.sort();
    for path in files {
        let Some(document) = file_name(&path).strip_suffix(".links.tsv").map(str::to_string) else { continue };
        let (Some(&from_start), Some(&to_start)) = (from.document_starts.get(&document), to.document_starts.get(&document)) else {
            return Err(format!("{name}: {document} isn't in both editions"));
        };
        for row in read_tsv(&path)?.1 {
            let number = |field: &String| field.parse::<u32>().map_err(|_| format!("{name} {document}: bad link '{field}'"));
            links.push((number(&row[0])? + from_start, number(&row[1])? + to_start));
        }
    }
    let mut writer = options.writer();
    writer.raw("module.kind", b"alignment");
    writer.raw("module.from", from_id.as_bytes());
    writer.raw("module.to", to_id.as_bytes());
    writer.packed("module.slots", &[from.slots as u32, to.slots as u32]);
    links.sort_unstable();
    links.dedup();
    writer.packed("links.from", &links.iter().map(|link| link.0).collect::<Vec<_>>());
    writer.packed("links.to", &links.iter().map(|link| link.1).collect::<Vec<_>>());
    links.sort_unstable_by_key(|link| (link.1, link.0)); // And the same links for looking up in the other direction
    writer.packed("rlinks.to", &links.iter().map(|link| link.1).collect::<Vec<_>>());
    writer.packed("rlinks.from", &links.iter().map(|link| link.0).collect::<Vec<_>>());
    save(output, &format!("{name}.align"), writer).map(Some)
}

/// A thesaurus: for each term (as it's looked up), the entry titles to see, and the ones for the other side of the question
fn compile_thesaurus(path: &Path, output: &Path, options: Options) -> Result<Written> {
    let language = file_name(path).trim_end_matches(".tsv").to_string();
    let mut rows: Vec<(String, Vec<String>)> = read_tsv(path)?.1.into_iter() // term, see, contrast, note
        .map(|row| (biblelastic_engine::query::title_words(&row[0]).join(" "), row)).filter(|(key, _)| !key.is_empty()).collect();
    rows.sort();
    rows.dedup_by(|a, b| a.0 == b.0);
    let mut writer = options.writer();
    writer.raw("module.kind", b"thesaurus");
    writer.raw("module.layer", language.as_bytes());
    writer.strings("term.dict", &rows.iter().map(|(key, _)| key).collect::<Vec<_>>());
    for (column, name) in ["name", "see", "contrast", "note"].iter().enumerate() {
        writer.strings(&format!("term.{name}"), &rows.iter().map(|(_, row)| row[column].as_str()).collect::<Vec<_>>());
    }
    save(output, &format!("Thesaurus.{language}"), writer)
}

/// Compile everything in the intermediate folder. Editions are compiled in parallel.
pub fn compile(intermediate: &Path, output: &Path, options: Options) -> Result<Vec<Written>> {
    fs::create_dir_all(output).map_err(|error| format!("{}: {error}", output.display()))?;
    let edition_folders: Vec<PathBuf> = subfolders(intermediate).into_iter().filter(|folder| folder.join("documents").is_dir()).collect();
    if edition_folders.is_empty() { return Err(format!("no editions found in {} (run the ingest first)", intermediate.display())); }
    let editions: Vec<Edition> = std::thread::scope(|scope| {
        let handles: Vec<_> = edition_folders.iter().map(|folder| scope.spawn(move || compile_edition(folder, output, options))).collect();
        handles.into_iter().map(|handle| handle.join().map_err(|_| "a compile thread failed".to_string())?).collect::<Result<Vec<_>>>()
    })?;
    let alignments: Vec<Written> = std::thread::scope(|scope| {
        let editions = &editions;
        let handles: Vec<_> = subfolders(&intermediate.join("alignments")).into_iter().map(|folder| scope.spawn(move || compile_alignment(&folder, editions, output, options))).collect();
        handles.into_iter().map(|handle| handle.join().map_err(|_| "a compile thread failed".to_string())?).collect::<Result<Vec<_>>>()
    })?.into_iter().flatten().collect();
    let mut thesauruses = Vec::new();
    let mut thesaurus_files: Vec<PathBuf> = fs::read_dir(intermediate.join("thesaurus")).into_iter().flatten().flatten().map(|entry| entry.path()).collect();
    thesaurus_files.sort();
    for path in thesaurus_files.iter().filter(|path| path.extension().is_some_and(|extension| extension == "tsv")) { thesauruses.push(compile_thesaurus(path, output, options)?); }
    let written: Vec<Written> = editions.into_iter().flat_map(|edition| edition.written).chain(alignments).chain(thesauruses).collect();
    // The catalogue that an installer downloads first, to see what there is
    let entries: Vec<String> = written.iter().map(|module| format!("    {{\"name\": \"{}\", \"bytes\": {}}}", module.name, module.bytes)).collect();
    let catalogue = format!("{{\n  \"format\": {},\n  \"modules\": [\n{}\n  ]\n}}\n", biblelastic_engine::format::FORMAT_VERSION, entries.join(",\n"));
    fs::write(output.join("index.json"), catalogue).map_err(|error| format!("{}: {error}", output.display()))?;
    Ok(written)
}

#[cfg(test)]
mod tests {
    use biblelastic_engine::library::{find_terms, Folder, Library, Text};
    use biblelastic_engine::query;

    fn write(folder: &std::path::Path, name: &str, content: &str) {
        let path = folder.join(name);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, content).unwrap();
    }

    #[test]
    fn compile_then_query() {
        let folder = std::env::temp_dir().join(format!("biblelastic-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&folder);
        let intermediate = folder.join("intermediate");
        // A two-document translation, so that slot numbers aren't the same as the per-document word indexes
        write(&intermediate, "EN/manifest.json", "{}");
        write(&intermediate, "EN/documents/FRT.tokens.tsv", "before\ttext\tafter\tnorm\trow\n\tTitle\t\ttitle\t\n");
        write(&intermediate, "EN/documents/FRT.nodes.tsv", "type\tstart\tend\tname\tattributes\npara\t0\t1\tmt1\t\n");
        write(&intermediate, "EN/documents/JN1.tokens.tsv", "before\ttext\tafter\tnorm\trow\n\
            “\tGod\t \tgod\t2\n\tloves\t \tloves\t3\n\tus\t.” \tus\t\n\tLove\t \tlove\t5\n\tis\t \tis\t5\n\tgood\t,\tgood\t\n\tgrace\t \tgrace\t\n\tand\t \tand\t\n\tlovely\t \tlovely\t9\n\ttruth\t.\ttruth\t\n");
        write(&intermediate, "EN/documents/JN1.nodes.tsv", "type\tstart\tend\tname\tattributes\n\
            chapter\t0\t10\t4\t\npara\t0\t6\tp\t{\"kind\": \"body\"}\nverse\t0\t3\t4:8\t\nsentence\t0\t3\t\t\nverse\t3\t3\t4:9\t\nverse\t3\t10\t4:10\t\nsentence\t3\t10\t\t\npara\t6\t10\tq1\t\n\
            span\t0\t1\tadd\t{\"reason\": \"pronoun_to_name\", \"uncertain\": true}\nspan\t2\t3\tadd\t{\"reason\": \"object\"}\nspan\t0\t1\tnd\t\n");
        write(&intermediate, "GR/manifest.json", "{}");
        write(&intermediate, "GR/documents/JN1.tokens.tsv", "before\ttext\tafter\tnorm\tlemma\tstrong\tlemma_translit\toet_row\n\
            \tθεὸς\t \tθεοσ\tθεός\tG2316\ttheos\t2\n\tἀγαπᾷ\t \tαγαπα\tἀγαπάω\tG0025\tagapaō\t3\n\tἀγάπη\t \tαγαπη\tἀγάπη\tG0026\tagapaʸ\t5\n\tκαλή\t.\tκαλη\tκαλός\tG2570\tkalos\t9\n");
        write(&intermediate, "GR/documents/JN1.nodes.tsv", "type\tstart\tend\tname\tattributes\npara\t0\t4\tp\t\nverse\t0\t4\t4:8\t\n");
        write(&intermediate, "GR/layers/OET/JN1.features.tsv", "gloss\ttags\nGod\tPGod;Y30\nloves\tY30\nlove\t\n\t\n");
        write(&intermediate, "alignments/EN--GR/JN1.links.tsv", "from\tto\n0\t0\n1\t1\n3\t2\n4\t2\n8\t3\n");

        // A commentary: a study note on one verse, and an article that's about a longer passage
        write(&intermediate, "CM/manifest.json", "{\n \"format_version\": \"0.1\",\n \"kind\": \"commentary\",\n \"layers\": [{\"kind\": \"features\"}]\n}\n");
        write(&intermediate, "CM/documents/JN1.tokens.tsv", "before\ttext\tafter\tnorm\n\tLove\t \tlove\n\tdefined\t. \tdefined\n(\tRom\t \trom\n\t5\t:\t5\n\t8\t)\t8\n");
        write(&intermediate, "CM/documents/JN1.nodes.tsv", "type\tstart\tend\tname\tattributes\npara\t0\t5\tsn-text\t\nsentence\t0\t2\t\t\nsentence\t2\t5\t\t\n");
        write(&intermediate, "CM/documents/JN1.entries.tsv", "start\tend\tname\ttype\ttitle\n0\t5\t4:8\tStudyNote\t\n");
        write(&intermediate, "CM/documents/JN1.anchors.tsv", "start\tend\tkind\treference\n2\t5\tcites\tROM 5:8\n0\t5\tabout\tJN1 4:8\n");
        write(&intermediate, "CM/documents/JN1.links.tsv", "start\tend\tkind\ttarget\n0\t1\tsee\tThemes love\n0\t1\tsee\tThemes Missing\n");
        write(&intermediate, "CM/documents/Themes.tokens.tsv", "before\ttext\tafter\tnorm\n\tLove\t \tlove\n\tmatters\t.\tmatters\n");
        write(&intermediate, "CM/documents/Themes.nodes.tsv", "type\tstart\tend\tname\tattributes\npara\t0\t2\ttheme-body\t\nsentence\t0\t2\t\t\n");
        write(&intermediate, "CM/documents/Themes.entries.tsv", "start\tend\tname\ttype\ttitle\n0\t2\tLove\tThemeNote\tGod’s Love*\n");
        write(&intermediate, "CM/documents/Themes.anchors.tsv", "start\tend\tkind\treference\n0\t2\tabout\tJN1 4:7-4:21\n");
        write(&intermediate, "CM/documents/Themes.links.tsv", "start\tend\tkind\ttarget\n1\t2\tsee\tJN1 4:8\n");

        // A thesaurus: what people might type → the titles of entries (and of entries on the other side of the question)
        write(&intermediate, "thesaurus/eng.tsv", "term\tsee\tcontrast\tnote\nDivine affection!\tGod’s Love; Nothing Called This\t\t\n");

        let written = super::compile(&intermediate, &folder.join("modules"), super::Options { page_bits: 5, compress: true }).unwrap(); // Tiny pages, so that plenty of things cross them
        assert_eq!(written.iter().map(|module| module.name.as_str()).collect::<Vec<_>>(), ["CM.text", "EN.text", "GR.text", "GR.morph", "GR.OET", "EN--GR.align", "Thesaurus.eng"]);
        let library = Library::open(&Folder(folder.join("modules"))).unwrap();

        // Text is resynthesised, with a space where the second paragraph starts
        let text = Text::open(&library.text_module("EN").unwrap()).unwrap();
        assert_eq!(text.render(4..11), "Love is good, grace and lovely truth.");
        assert_eq!((text.reference(2), text.reference(4), text.reference(0)), ("JN1 4:8".to_string(), "JN1 4:10".to_string(), "FRT".to_string()));

        // "love*" matches loves, love and lovely; "is" shares its Greek word with "love"
        let result = query::original_terms(&library, "EN", &["LOVE*".to_string()], 1).unwrap();
        assert_eq!(result.forms.into_iter().collect::<Vec<_>>(), [("love".to_string(), 1), ("lovely".to_string(), 1), ("loves".to_string(), 1)]);
        assert_eq!(result.linked, 3);
        let terms: Vec<_> = result.terms.iter().map(|term| (term.lemma.as_str(), term.transliteration.as_str(), term.gloss.as_str(), term.count)).collect();
        assert_eq!(terms, [("καλός", "kalos", "", 1), ("ἀγάπη", "agapaʸ", "love", 1), ("ἀγαπάω", "agapaō", "loves", 1)]);
        assert_eq!(result.terms[2].examples[0].reference, "JN1 4:8");
        assert_eq!(result.terms[2].examples[0].text, "“God loves us.”");

        // Both words in one sentence, but not in one paragraph
        let together = query::find_together(&library, "EN", &["grace".to_string(), "love".to_string()], "sentence", 5).unwrap();
        assert_eq!((together.total, together.examples[0].reference.as_str()), (1, "JN1 4:10"));
        assert_eq!(query::find_together(&library, "EN", &["grace".to_string(), "love".to_string()], "para", 5).unwrap().total, 0);

        // Where the translators marked a change
        let marked = query::find_spans(&library, "EN", "add", "reason", "pronoun_to_name", 5).unwrap();
        assert_eq!((marked.total, marked.examples[0].reference.as_str(), marked.examples[0].text.as_str()), (1, "JN1 4:8", "“[God] loves us.”"));
        assert_eq!(query::find_spans(&library, "EN", "add", "reason", "measure", 5).unwrap().total, 0);

        // The same through the request interface that apps use, and the catalogue
        let response = biblelastic_engine::api::respond(&library, "command=marked\nedition=EN\nwords=pronoun_to_name");
        assert_eq!(response, r#"{"ok":true,"forms":[["god",1]],"total":1,"examples":[{"reference":"JN1 4:8","text":"“[God] loves us.”"}]}"#);
        assert!(biblelastic_engine::api::respond(&library, "command=nothing").starts_with(r#"{"ok":false,"error":"#));
        assert!(std::fs::read_to_string(folder.join("modules/index.json")).unwrap().contains(r#"{"name": "EN--GR.align", "bytes": "#));

        // What the commentary says about a passage: the note on that verse, then the article on a longer passage that includes it
        use biblelastic_engine::reference::Passage;
        assert_eq!(library.modules.iter().map(|installed| installed.work.as_str()).collect::<Vec<_>>(), ["commentary", "", "scripture", "scripture", "scripture", "scripture", ""]);
        let found = query::about(&library, &Passage::parse("JN1 4:8").unwrap(), None, 5, 100).unwrap();
        let comments: Vec<_> = found.comments.iter().map(|comment| (comment.locator.as_str(), comment.title.as_str(), comment.kind, comment.passage.as_str(), comment.text.as_str())).collect();
        assert_eq!(comments, [("JN1 4:8", "", "about", "JN1 4:8", "Love defined. (Rom 5:8)"), ("Themes Love", "God’s Love*", "about", "JN1 4:7-21", "Love matters.")]);
        // … and what cites a passage (shown as the sentence that cites it)
        let found = query::about(&library, &Passage::parse("ROM 5").unwrap(), Some("CM"), 5, 100).unwrap();
        assert_eq!((found.total, found.comments[0].kind, found.comments[0].locator.as_str(), found.comments[0].text.as_str()), (1, "cites", "JN1 4:8", "(Rom 5:8)"));
        assert_eq!(query::about(&library, &Passage::parse("JN1 5").unwrap(), None, 5, 100).unwrap().total, 0);
        assert_eq!(query::about(&library, &Passage::parse("JN1 4:8").unwrap(), None, 5, 6).unwrap().comments[0].text, "Love…");
        // Entries are found by the words of their titles, and list what they link to
        let found = query::entries(&library, &["Gods".to_string(), "lov*".to_string()], None, 5, 100).unwrap();
        assert_eq!((found.total, found.entries[0].locator.as_str(), found.entries[0].kind.as_str(), found.entries[0].text.as_str()), (1, "Themes Love", "ThemeNote", "Love matters."));
        assert_eq!(found.entries[0].see, ["JN1 4:8"]);
        assert_eq!(query::entries(&library, &["defined".to_string()], None, 5, 100).unwrap().total, 0);
        // A commentary's own text is searched like any other, and places in it are given by document and entry
        assert_eq!(query::find_together(&library, "CM", &["love".to_string(), "rom".to_string()], "entry", 5).unwrap().examples[0].reference, "JN1 4:8");
        let response = biblelastic_engine::api::respond(&library, "command=about\npassage=JN1 4:8\nlimit=1\nlength=4");
        assert_eq!(response, r#"{"ok":true,"passage":"JN1 4:8","total":2,"comments":[{"edition":"CM","work":"commentary","locator":"JN1 4:8","title":"","kind":"about","passage":"JN1 4:8","text":"Love…"}]}"#);
        assert!(biblelastic_engine::api::respond(&library, "command=entry\nwords=love").contains(r#""locator":"Themes Love","title":"God’s Love*","type":"ThemeNote","text":"Love matters.","see":["JN1 4:8"]"#));

        // Reading: whole chapters come with their headings, and part of a verse range starts mid-paragraph
        assert_eq!(biblelastic_engine::api::respond(&library, "command=contents\nedition=EN"),
                   r#"{"ok":true,"edition":"EN","documents":[{"name":"FRT","chapters":0,"introduction":false,"sections":0},{"name":"JN1","chapters":4,"introduction":false,"sections":1}]}"#);
        assert_eq!(biblelastic_engine::api::respond(&library, "command=read\nedition=EN\npassage=JN1 4"), concat!(
            r#"{"ok":true,"edition":"EN","passage":"JN1 4","paragraphs":[{"style":"p","kind":"body","pieces":[{"v":"8","r":"4:8"},{"t":"“God ","s":["add","nd"]},{"t":"loves "},{"t":"us.” ","s":["add"]},"#,
            r#"{"v":"10","r":"4:10"},{"t":"Love is good,"}]},{"style":"q1","kind":"other","pieces":[{"t":"grace and lovely truth."}]}]}"#));
        assert_eq!(biblelastic_engine::api::respond(&library, "command=read\nedition=EN\npassage=JN1 4:10"),
                   r#"{"ok":true,"edition":"EN","passage":"JN1 4:10","paragraphs":[{"style":"p","kind":"body","pieces":[{"v":"10","r":"4:10"},{"t":"Love is good,"}]},{"style":"q1","kind":"other","pieces":[{"t":"grace and lovely truth."}]}]}"#);
        // Reading by section: this translation has no section headings, so its chapters are the sections, and what comes before the first one is number 0
        let section = biblelastic_engine::api::respond(&library, "command=read\nedition=EN\nunit=section\npassage=JN1 4:10");
        assert!(section.starts_with(r#"{"ok":true,"edition":"EN","document":"JN1","section":1,"title":"4","passage":"JN1 4:8-10","previous":{"document":"FRT","section":0},"next":null,"paragraphs":[{"style":"p","#), "{section}");
        let front = biblelastic_engine::api::respond(&library, "command=read\nedition=EN\ndocument=FRT\nsection=0");
        assert_eq!(front, r#"{"ok":true,"edition":"EN","document":"FRT","section":0,"title":"","passage":"FRT","previous":null,"next":{"document":"JN1","section":1},"paragraphs":[{"style":"mt1","kind":"other","pieces":[{"t":"Title"}]}],"noted":[]}"#);
        // The commentary has a note of its own on 4:8 (and a theme note that starts at 4:7, which isn't in this translation)
        assert!(section.ends_with(r#""noted":["4:8"]}"#), "{section}");
        assert!(biblelastic_engine::api::respond(&library, "command=read\nedition=EN\ndocument=JN1\nsection=2").contains("JN1 has no section 2"));
        assert!(biblelastic_engine::api::respond(&library, "command=read\nedition=EN\npassage=JN1 5").contains("doesn't have JN1 5"));
        assert!(biblelastic_engine::api::respond(&library, "command=read\nedition=CM\npassage=JN1 4").contains("isn't divided into chapters"));

        // A subject: through the thesaurus to an entry, and from that to the passage it's about, with its text from the translation
        let topic = query::topic(&library, "EN", &["divine".to_string(), "AFFECTION".to_string()], 5, 100).unwrap();
        assert_eq!((topic.see.len(), topic.entries.len(), topic.entries[0].locator.as_str(), topic.other_entries.len()), (2, 1, "Themes Love", 0));
        assert_eq!(topic.passages.iter().map(|passage| (passage.passage.as_str(), passage.sources[0].as_str(), passage.text.as_str())).collect::<Vec<_>>(),
                   [("JN1 4:7-21", "God’s Love*", "“God loves us.” Love is good, grace and lovely truth.")]);
        // … or straight to an entry by its title, and to wherever the words are found
        let topic = query::topic(&library, "EN", &["love".to_string()], 5, 100).unwrap();
        assert_eq!((topic.see.len(), topic.entries[0].title.as_str(), topic.scripture[0].reference.as_str(), topic.mentions[0].reference.as_str()), (0, "God’s Love*", "JN1 4:10", "CM JN1 4:8"));
        assert!(biblelastic_engine::api::respond(&library, "command=topic\nedition=EN\nwords=divine affection").contains(r#""see":["God’s Love","Nothing Called This"],"contrast":[],"entries":[{"edition":"CM","#));
        assert!(biblelastic_engine::api::respond(&library, "command=topic\nedition=EN\nwords=nonsense").starts_with(r#"{"ok":true,"see":[],"contrast":[],"entries":[],"passages":[],"#));

        // A word of the translation → the original word behind it, and how its lemma is rendered (two English words share one Greek word here)
        let words = biblelastic_engine::api::respond(&library, "command=read\nedition=EN\npassage=JN1 4:10\ndetail=words");
        assert!(words.contains(r#"{"v":"10","r":"4:10"},{"t":"Love ","w":4},{"t":"is ","w":5},{"t":"good,","w":6}"#), "{words}");
        let info = query::word(&library, "EN", 4).unwrap();
        assert_eq!((info.text.as_str(), info.reference.as_str(), info.originals.len()), ("Love", "JN1 4:10", 1));
        let original = &info.originals[0];
        assert_eq!((original.edition.as_str(), original.text.as_str(), original.lemma.as_str(), original.lemma_transliteration.as_str(), original.strong.as_str(), original.gloss.as_str()),
                   ("GR", "ἀγάπη", "ἀγάπη", "agapaʸ", "G0026", "love"));
        assert_eq!((original.occurrences, original.renderings.clone()), (1, vec![("love is".to_string(), 1)]));
        assert_eq!(info.linked, [("EN".to_string(), vec![4, 5])]); // ‘Love is’ both translate ἀγάπη
        assert_eq!(query::word(&library, "EN", 3).unwrap().originals.len(), 0); // ‘us’ isn't linked to anything
        assert!(query::word(&library, "EN", 999).is_err());
        let verses = query::lemma_verses(&library, "EN", "GR", "ἀγαπάω", 5).unwrap();
        assert_eq!((verses.total, verses.examples[0].reference.as_str()), (1, "JN1 4:8"));
        assert!(biblelastic_engine::api::respond(&library, "command=word\nedition=EN\nslot=2").contains(r#""lemma":"ἀγαπάω","lemmaTransliteration":"agapaō","strong":"G0025","morphology":"","gloss":"loves","occurrences":1,"counted":1,"renderings":[["loves",1]]"#));

        // Each tag is indexed separately
        let layer = library.column_module("GR", "tags").unwrap();
        assert_eq!(find_terms(&layer, "idx.tags", &["Y30".to_string()]).unwrap().0, [0, 1]);
        assert_eq!(find_terms(&layer, "idx.tags", &["P*".to_string()]).unwrap().0, [0]);
        std::fs::remove_dir_all(&folder).unwrap();
    }
}
