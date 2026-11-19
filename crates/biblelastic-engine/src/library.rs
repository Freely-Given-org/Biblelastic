//! A set of installed modules, and typed views of what's inside them.

use std::collections::BTreeMap;
use std::ops::Range;
use std::rc::Rc;

use crate::format::{Module, PageCache, Packed, Result, Strings, DEFAULT_CACHE_BYTES};

/// Where modules come from (a folder natively; browser storage later)
pub trait ModuleSource {
    fn names(&self) -> Result<Vec<String>>;
    /// Open one module, which must use this page cache
    fn open(&self, name: &str, cache: &Rc<PageCache>) -> Result<Module>;
}

#[cfg(not(target_arch = "wasm32"))]
pub struct Folder(pub std::path::PathBuf);

#[cfg(not(target_arch = "wasm32"))]
impl ModuleSource for Folder {
    fn names(&self) -> Result<Vec<String>> {
        let mut names = Vec::new();
        for entry in std::fs::read_dir(&self.0).map_err(|error| format!("{}: {error}", self.0.display()))? {
            let name = entry?.file_name().to_string_lossy().into_owned();
            if let Some(stem) = name.strip_suffix(".blm") { names.push(stem.to_string()); }
        }
        names.sort();
        Ok(names)
    }
    fn open(&self, name: &str, cache: &Rc<PageCache>) -> Result<Module> { Module::open_file_with(&self.0.join(format!("{name}.blm")), cache) }
}

pub struct Installed {
    pub name: String,
    /// `text`, `features`, or `alignment`
    pub kind: String,
    /// What the edition is: `scripture`, `commentary`, or `dictionary` (empty for an alignment)
    pub work: String,
    pub edition: String,
    pub layer: String,
    /// What the work is called, e.g., `Tyndale Open Study Notes, adapted for the OET`
    pub title: String,
    /// Anything that must be shown with what the work says (HTML: only <em> and <a>)
    pub disclaimer: String,
    /// For alignments: the two editions that are linked
    pub from: String,
    pub to: String,
    pub module: Rc<Module>,
}

/// Every installed module, with only its header and table of contents read so far
pub struct Library {
    pub modules: Vec<Installed>,
    /// The pages that have been read from all the modules: this is nearly all of the memory that the engine uses
    pub cache: Rc<PageCache>,
}

impl Library {
    pub fn open(source: &dyn ModuleSource) -> Result<Library> { Library::open_with(source, DEFAULT_CACHE_BYTES) }

    /// `cache_bytes` limits how much of the modules is kept in memory
    pub fn open_with(source: &dyn ModuleSource, cache_bytes: usize) -> Result<Library> {
        let cache = PageCache::new(cache_bytes);
        let mut modules = Vec::new();
        for name in source.names()? {
            let module = source.open(&name, &cache)?;
            let field = |section: &str| if module.has(section) { module.text(section) } else { Ok(String::new()) };
            modules.push(Installed { kind: field("module.kind")?, work: field("module.work")?, title: field("module.title")?, disclaimer: field("module.disclaimer")?, edition: field("module.edition")?, layer: field("module.layer")?,
                                     from: field("module.from")?, to: field("module.to")?, name, module: Rc::new(module) });
        }
        Ok(Library { modules, cache })
    }

    pub fn bytes_read(&self) -> u64 { self.modules.iter().map(|installed| installed.module.bytes_read()).sum() }

    /// The text modules of the commentaries, dictionaries, and so on (of just one edition, if one is named)
    pub fn item_modules<'a>(&'a self, edition: Option<&'a str>) -> impl Iterator<Item = &'a Installed> {
        self.modules.iter().filter(move |installed| installed.kind == "text" && installed.module.has("node.entry.starts") && edition.is_none_or(|edition| installed.edition == edition))
    }

    pub fn text_module(&self, edition: &str) -> Result<Rc<Module>> {
        self.modules.iter().find(|installed| installed.kind == "text" && installed.edition == edition).map(|installed| installed.module.clone())
            .ok_or_else(|| format!("no text module is installed for '{edition}'").into())
    }

    /// Whichever of an edition's modules has this feature column
    pub fn column_module(&self, edition: &str, column: &str) -> Option<Rc<Module>> {
        let section = format!("col.{column}.ids");
        self.modules.iter().find(|installed| installed.edition == edition && installed.module.has(&section)).map(|installed| installed.module.clone())
    }

    pub fn column(&self, edition: &str, column: &str) -> Result<Option<Column>> {
        self.column_module(edition, column).map(|module| Column::open(&module, &format!("col.{column}"))).transpose()
    }

    pub fn alignments_from(&self, edition: &str) -> Vec<&Installed> {
        self.modules.iter().filter(|installed| installed.kind == "alignment" && installed.from == edition).collect()
    }
}

/// A dictionary-encoded feature: one value for every slot
pub struct Column {
    pub dictionary: Strings,
    pub ids: Packed,
}

impl Column {
    /// `prefix` is e.g. `col.lemma` or `node.verse.name`
    pub fn open(module: &Module, prefix: &str) -> Result<Column> {
        Ok(Column { dictionary: module.strings(&format!("{prefix}.dict"))?, ids: module.packed(&format!("{prefix}.ids"))? })
    }
    pub fn get(&self, slot: u32) -> String { self.dictionary.get(self.ids.get(slot as usize) as usize) }
}

/// One type of node: ranges of slots, in order of where they start
pub struct Nodes {
    pub starts: Packed,
    pub ends: Packed,
    pub names: Column,
}

impl Nodes {
    pub fn open(module: &Module, node_type: &str) -> Result<Nodes> {
        Ok(Nodes { starts: module.packed(&format!("node.{node_type}.starts"))?, ends: module.packed(&format!("node.{node_type}.ends"))?,
                   names: Column::open(module, &format!("node.{node_type}.name"))? })
    }
    pub fn range(&self, index: usize) -> Range<u32> { self.starts.get(index)..self.ends.get(index) }

    /// The node that contains this slot (for node types that don't overlap themselves, like verses and sentences)
    pub fn containing(&self, slot: u32) -> Option<usize> {
        let after = self.starts.upper_bound(slot);
        (after.saturating_sub(4)..after).rev().find(|&index| self.ends.get(index) > slot) // Steps back over any empty nodes
    }
}

/// What's needed to display an edition's text and say where it's from
pub struct Text {
    pub before: Column,
    pub text: Column,
    pub after: Column,
    pub document_names: Strings,
    pub document_starts: Packed,
    /// Only Scripture has verses
    pub verses: Option<Nodes>,
    /// Only commentaries, dictionaries, and so on have entries
    pub entries: Option<Nodes>,
    pub paragraphs: Nodes,
}

impl Text {
    pub fn open(module: &Module) -> Result<Text> {
        Ok(Text { before: Column::open(module, "col.before")?, text: Column::open(module, "col.text")?, after: Column::open(module, "col.after")?,
                  document_names: module.strings("documents.names")?, document_starts: module.packed("documents.starts")?,
                  verses: optional_nodes(module, "verse")?, entries: optional_nodes(module, "entry")?, paragraphs: Nodes::open(module, "para")? })
    }

    /// Resynthesise the text of a range of slots (as one line, with a space where a new paragraph or line of poetry starts)
    pub fn render(&self, range: Range<u32>) -> String { self.render_exact(range).trim_end().to_string() }

    /// The same, but keeping any space after the last word
    pub fn render_exact(&self, range: Range<u32>) -> String {
        let mut rendered = String::new();
        let mut paragraph = self.paragraphs.starts.upper_bound(range.start);
        for slot in range {
            while paragraph < self.paragraphs.starts.len() && self.paragraphs.starts.get(paragraph) <= slot {
                if !rendered.is_empty() && !rendered.ends_with(' ') { rendered.push(' '); }
                paragraph += 1;
            }
            rendered.push_str(&self.before.get(slot));
            rendered.push_str(&self.text.get(slot));
            rendered.push_str(&self.after.get(slot));
        }
        rendered
    }

    pub fn document(&self, slot: u32) -> String { self.document_names.get(self.document_starts.upper_bound(slot) - 1) }

    /// The slots of the verse that this slot is in
    pub fn verse(&self, slot: u32) -> Option<Range<u32>> {
        let verses = self.verses.as_ref()?;
        verses.containing(slot).map(|verse| verses.range(verse))
    }

    /// Where a slot is: e.g., `JHN 3:16` in Scripture, `Articles Aaron` in a dictionary (the document, then the entry's name),
    /// or just the document for text that's in neither a verse nor an entry
    pub fn reference(&self, slot: u32) -> String {
        for nodes in [&self.verses, &self.entries].into_iter().flatten() {
            if let Some(node) = nodes.containing(slot) { return format!("{} {}", self.document(slot), nodes.names.get(node as u32)); }
        }
        self.document(slot)
    }

    /// The text of a range of slots, cut short (with an ellipsis) once it's longer than `length` characters
    pub fn excerpt(&self, range: Range<u32>, length: usize) -> String {
        let (mut rendered, mut next) = (String::new(), range.start);
        while next < range.end && rendered.chars().count() <= length { // A few words at a time, so that a long article isn't all read
            let end = range.end.min(next + 16);
            if !rendered.is_empty() && !rendered.ends_with(' ') && self.paragraphs.starts.lower_bound(next) < self.paragraphs.starts.upper_bound(next) { rendered.push(' '); }
            rendered.push_str(&self.render_exact(next..end));
            next = end;
        }
        let rendered = rendered.trim_end();
        if rendered.chars().count() <= length { return rendered.to_string(); }
        let cut: String = rendered.chars().take(length).collect();
        format!("{}…", cut.rsplit_once(' ').map_or(cut.as_str(), |(kept, _)| kept).trim_end_matches([',', ';', ':', ' ', '(']))
    }
}

fn optional_nodes(module: &Module, node_type: &str) -> Result<Option<Nodes>> {
    if module.has(&format!("node.{node_type}.starts")) { Nodes::open(module, node_type).map(Some) } else { Ok(None) }
}

/// The Scripture passages that the entries of a commentary or dictionary are about (kind 0) or cite (kind 1), in passage order
pub struct Anchors {
    /// The codes of the books that there are anchors for: a book's number here is its number in `from` and `to`
    pub books: Strings,
    /// Packed positions (see `reference::pack`), with `to` included
    pub from: Packed,
    pub to: Packed,
    pub kind: Packed,
    /// The slots of the whole entry (for kind 0) or of the words that cite the passage (for kind 1)
    pub start: Packed,
    pub end: Packed,
    pub entry: Packed,
}

impl Anchors {
    pub fn open(module: &Module) -> Result<Anchors> {
        Ok(Anchors { books: module.strings("anchor.books")?, from: module.packed("anchor.from")?, to: module.packed("anchor.to")?, kind: module.packed("anchor.kind")?,
                     start: module.packed("anchor.start")?, end: module.packed("anchor.end")?, entry: module.packed("anchor.entry")? })
    }
}

/// Look up words in an index (`prefix` is e.g. `col.norm` or `idx.tags`). A trailing `*` matches any ending.
/// Returns the slots (ascending) and how many times each matching form occurs.
pub fn find_terms(module: &Module, prefix: &str, words: &[String]) -> Result<(Vec<u32>, BTreeMap<String, usize>)> {
    let dictionary = module.strings(&format!("{prefix}.dict"))?;
    let mut ids = Vec::new();
    for word in words {
        match word.strip_suffix('*') {
            Some(prefix) => ids.extend(dictionary.find_prefix(prefix)),
            None => ids.extend(dictionary.find(word)),
        }
    }
    ids.sort_unstable();
    ids.dedup();
    let (mut slots, mut forms) = (Vec::new(), BTreeMap::new());
    for id in ids {
        let list = module.postings(&format!("{prefix}.post"), id)?;
        forms.insert(dictionary.get(id).to_string(), list.len());
        slots.extend(list);
    }
    slots.sort_unstable();
    Ok((slots, forms))
}
