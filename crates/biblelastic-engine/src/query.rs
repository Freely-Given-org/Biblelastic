//! The first queries. These are written directly against the modules for now;
//! the general query tree described in the README will replace them.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use crate::format::Result;
use crate::library::{find_terms, Anchors, Column, Library, Nodes, Text};
use crate::reference::{pack, unpack, Passage, LAST};

pub struct Example {
    pub reference: String,
    pub text: String,
}

/// One original-language term that the searched-for words translate
pub struct OriginalTerm {
    pub edition: String,
    pub lemma: String,
    pub transliteration: String,
    pub strong: String,
    /// The most common gloss among the counted occurrences
    pub gloss: String,
    /// How many original-language words are translated by one of the searched-for words
    pub count: usize,
    /// How many different verses those are in
    pub verses: usize,
    pub examples: Vec<Example>,
}

pub struct OriginalTerms {
    /// The forms that matched in the translation, with how often each occurs
    pub forms: BTreeMap<String, usize>,
    /// How many of those occurrences are linked to an original-language word
    pub linked: usize,
    pub terms: Vec<OriginalTerm>,
}

/// "Find all the different Hebrew/Greek terms for 'love'": look the words up in a translation,
/// follow the word alignments to every aligned original-language edition, and group by lemma.
pub fn original_terms(library: &Library, edition: &str, words: &[String], example_count: usize) -> Result<OriginalTerms> {
    let text_module = library.text_module(edition)?;
    let (slots, forms) = find_terms(&text_module, "col.norm", &normalise(words))?;
    let text = Text::open(&text_module)?;
    let alignments = library.alignments_from(edition);
    if alignments.is_empty() { return Err(format!("no alignment modules are installed for '{edition}'").into()); }

    let mut linked_slots = BTreeSet::new();
    let mut terms = Vec::new();
    for alignment in alignments {
        let (from, to) = (alignment.module.packed("links.from")?, alignment.module.packed("links.to")?);
        let Some(lemmas) = library.column(&alignment.to, "lemma")? else { continue };
        let transliterations = library.column(&alignment.to, "lemma_translit")?;
        let strongs = library.column(&alignment.to, "strong")?;
        let glosses = library.column(&alignment.to, "gloss")?;
        let context_glosses = library.column(&alignment.to, "context_gloss")?;

        // Original-language slot → the first translation slot that's linked to it
        let mut targets = BTreeMap::new();
        for &slot in &slots {
            let mut link = from.lower_bound(slot);
            while link < from.len() && from.get(link) == slot {
                linked_slots.insert(slot);
                targets.entry(to.get(link)).or_insert(slot);
                link += 1;
            }
        }
        // Group by lemma
        let mut groups: BTreeMap<u32, Vec<(u32, u32)>> = BTreeMap::new();
        for (&target, &slot) in &targets { groups.entry(lemmas.ids.get(target as usize)).or_default().push((target, slot)); }
        for (lemma_id, occurrences) in groups {
            let first_target = occurrences[0].0;
            let mut gloss_counts: HashMap<String, usize> = HashMap::new();
            if let Some(glosses) = &glosses {
                for &(target, _) in &occurrences {
                    let mut gloss = glosses.get(target);
                    if let (true, Some(column)) = (gloss.is_empty(), &context_glosses) { gloss = column.get(target); }
                    if !gloss.is_empty() { *gloss_counts.entry(gloss).or_default() += 1; }
                }
            }
            let mut verse_slots: Vec<u32> = occurrences.iter().map(|&(_, slot)| text.verse(slot).map_or(slot, |verse| verse.start)).collect();
            verse_slots.sort_unstable();
            verse_slots.dedup();
            terms.push(OriginalTerm {
                edition: alignment.to.clone(),
                lemma: lemmas.dictionary.get(lemma_id as usize).to_string(),
                transliteration: transliterations.as_ref().map_or(String::new(), |column| column.get(first_target).to_string()),
                strong: strongs.as_ref().map_or(String::new(), |column| base_strong(&column.get(first_target))),
                gloss: gloss_counts.into_iter().max_by(|a, b| a.1.cmp(&b.1).then_with(|| b.0.cmp(&a.0))).map_or(String::new(), |(gloss, _)| gloss),
                count: occurrences.len(),
                verses: verse_slots.len(),
                examples: verse_slots.iter().take(example_count).map(|&slot| example(&text, slot)).collect(),
            });
        }
    }
    terms.sort_by(|a, b| b.count.cmp(&a.count).then_with(|| a.lemma.cmp(&b.lemma)));
    Ok(OriginalTerms { forms, linked: linked_slots.len(), terms })
}

pub struct Found {
    pub total: usize,
    pub forms: BTreeMap<String, usize>,
    pub examples: Vec<Example>,
}

/// Find every node of one type (e.g., `sentence` or `verse`) that contains all of the words
pub fn find_together(library: &Library, edition: &str, words: &[String], node_type: &str, limit: usize) -> Result<Found> {
    let text_module = library.text_module(edition)?;
    let text = Text::open(&text_module)?;
    let nodes = Nodes::open(&text_module, node_type)?;
    let mut forms = BTreeMap::new();
    let mut common: Option<BTreeSet<usize>> = None;
    for word in normalise(words) {
        let (slots, word_forms) = find_terms(&text_module, "col.norm", &[word])?;
        forms.extend(word_forms);
        let containing: BTreeSet<usize> = slots.into_iter().filter_map(|slot| nodes.containing(slot)).collect();
        common = Some(match common { Some(previous) => previous.intersection(&containing).copied().collect(), None => containing });
    }
    let common = common.unwrap_or_default();
    let examples = common.iter().take(limit).map(|&node| {
        let range = nodes.range(node);
        Example { reference: text.reference(range.start), text: text.render(range) }
    }).collect();
    Ok(Found { total: common.len(), forms, examples })
}

/// Find the marked spans of text (e.g., `add`) that have a particular attribute value, e.g., `reason` = `pronoun_to_name`
/// for the places where the OET-RV replaced a pronoun with a name.
pub fn find_spans(library: &Library, edition: &str, marker: &str, attribute: &str, value: &str, limit: usize) -> Result<Found> {
    let text_module = library.text_module(edition)?;
    let text = Text::open(&text_module)?;
    let spans = Nodes::open(&text_module, "span")?;
    let attributes = text_module.strings("node.span.attributes.dict")?;
    let attribute_ids = text_module.packed("node.span.attributes.ids")?;
    let wanted = format!("\"{attribute}\": \"{value}\""); // As the ingest writes its JSON
    let matching: BTreeSet<u32> = (0..attributes.len()).filter(|&id| attributes.get(id).contains(&wanted)).map(|id| id as u32).collect();
    let (mut total, mut forms, mut examples) = (0, BTreeMap::new(), Vec::new());
    let Some(marker_id) = spans.names.dictionary.find(marker) else { return Ok(Found { total, forms, examples }) };
    for span in 0..spans.starts.len() {
        if !matching.contains(&attribute_ids.get(span)) || spans.names.ids.get(span) as usize != marker_id { continue; }
        total += 1;
        let range = spans.range(span);
        // Just the words, without the punctuation before the first one or after the last one
        let (opening, closing) = (text.before.get(range.start), text.after.get(range.end - 1));
        let (opening, closing) = (opening.as_str(), closing.as_str());
        let whole = text.render_exact(range.clone());
        let words = &whole[opening.len()..whole.len() - closing.len()];
        *forms.entry(words.to_lowercase()).or_default() += 1;
        if examples.len() < limit {
            let verse = text.verse(range.start).unwrap_or(range.clone());
            let (before, after) = (text.render_exact(verse.start..range.start), text.render(range.end..verse.end.max(range.end)));
            examples.push(Example { reference: text.reference(range.start), text: format!("{before}{opening}[{words}]{closing}{after}").trim_end().to_string() });
        }
    }
    Ok(Found { total, forms, examples })
}

/// One document of an edition, for a table of contents
pub struct Document {
    pub name: String,
    /// The highest chapter number (0 if the document isn't divided into chapters)
    pub chapters: u32,
    /// Whether there's anything before the first chapter (titles and an introduction), which is read as chapter 0
    pub introduction: bool,
}

/// The documents of an edition, in order
pub fn contents(library: &Library, edition: &str) -> Result<Vec<Document>> {
    let module = library.text_module(edition)?;
    let text = Text::open(&module)?;
    let chapters = if module.has("node.chapter.starts") { Some(Nodes::open(&module, "chapter")?) } else { None };
    (0..text.document_names.len()).map(|document| {
        let (start, end) = (text.document_starts.get(document), text.document_starts.get(document + 1));
        let (mut highest, mut introduction) = (0, false);
        if let Some(chapters) = &chapters {
            let (first, after) = (chapters.starts.lower_bound(start), chapters.starts.lower_bound(end));
            introduction = first < after && chapters.starts.get(first) > start;
            highest = (first..after).filter_map(|chapter| chapters.names.get(chapter as u32).parse().ok()).max().unwrap_or(0);
        }
        Ok(Document { name: text.document_names.get(document), chapters: highest, introduction })
    }).collect()
}

/// A piece of a paragraph, for displaying it
pub enum Piece {
    /// A verse starts here: its number as the edition gives it (which isn't always just a number)
    Verse(String),
    /// Some text, and the character styles that it has (e.g., `add`, `nd`, or `wj`)
    Text(String, Vec<String>),
}

pub struct Paragraph {
    /// The edition's own paragraph style, e.g., `p`, `q1`, or `s1`
    pub style: String,
    /// `body`, `heading`, `title`, `intro`, or `other`
    pub kind: String,
    pub pieces: Vec<Piece>,
}

pub struct Reading {
    /// The passage that's actually given
    pub passage: String,
    pub paragraphs: Vec<Paragraph>,
}

/// The text of a passage of Scripture, laid out for reading: whole chapters come with their headings,
/// and chapter 0 is whatever comes before the first chapter (titles and an introduction).
pub fn read(library: &Library, edition: &str, passage: &Passage) -> Result<Reading> {
    let module = library.text_module(edition)?;
    let text = Text::open(&module)?;
    let (Some(verses), true) = (&text.verses, module.has("node.chapter.starts")) else { return Err(format!("'{edition}' isn't divided into chapters and verses").into()) };
    let chapters = Nodes::open(&module, "chapter")?;
    let document = (0..text.document_names.len()).find(|&document| text.document_names.get(document) == passage.book)
        .ok_or_else(|| format!("'{edition}' doesn't have {}", passage.book))?;
    let (document_start, document_end) = (text.document_starts.get(document), text.document_starts.get(document + 1));
    let whole_chapters = passage.from.1 == 0 && passage.to.1 == LAST;

    let (mut start, mut end) = (u32::MAX, 0);
    if whole_chapters { // From the start of the first chapter (with its headings) to the end of the last one
        for chapter in chapters.starts.lower_bound(document_start)..chapters.starts.lower_bound(document_end) {
            let Ok(number) = chapters.names.get(chapter as u32).parse::<u32>() else { continue };
            if number >= passage.from.0 && number <= passage.to.0 { start = start.min(chapters.starts.get(chapter)); end = end.max(chapters.ends.get(chapter)); }
        }
        if passage.from.0 == 0 { // What's before the first chapter
            let first = chapters.starts.lower_bound(document_start);
            start = document_start;
            end = end.max(if first < chapters.starts.len() && chapters.starts.get(first) < document_end { chapters.starts.get(first) } else { document_end });
        }
    } else { // Just the verses
        for verse in verses.starts.lower_bound(document_start)..verses.starts.lower_bound(document_end) {
            let Some(number) = verse_number(&verses.names.get(verse as u32)) else { continue };
            if number >= passage.from && number <= passage.to && verses.ends.get(verse) > verses.starts.get(verse) {
                start = start.min(verses.starts.get(verse)); end = end.max(verses.ends.get(verse));
            }
        }
    }
    if start >= end { return Err(format!("'{edition}' doesn't have {passage}").into()); }

    // The character styles that overlap the passage (they're in order of where they start, and none is very long)
    let spans = Nodes::open(&module, "span")?;
    let overlapping: Vec<(std::ops::Range<u32>, String)> = (spans.starts.lower_bound(start.saturating_sub(2000))..spans.starts.lower_bound(end))
        .map(|span| (spans.range(span), span)).filter(|(range, _)| range.end > start).map(|(range, span)| (range, spans.names.get(span as u32))).collect();
    let attributes = Column::open(&module, "node.para.attributes")?;
    let mut paragraphs = Vec::new();
    let mut verse = verses.starts.lower_bound(start);
    // From the first paragraph that starts in the passage, or the one before it if that runs on into the passage
    let mut first = text.paragraphs.starts.lower_bound(start);
    if first > 0 && text.paragraphs.ends.get(first - 1) > start { first -= 1; }
    for paragraph in first..text.paragraphs.starts.lower_bound(end) {
        let range = text.paragraphs.starts.get(paragraph).max(start)..text.paragraphs.ends.get(paragraph).min(end);
        if range.start >= range.end { continue; }
        let attribute_text = attributes.get(paragraph as u32); // JSON, as the ingest writes it
        let kind = attribute_text.split_once("\"kind\": \"").and_then(|(_, rest)| rest.split_once('"')).map_or("other", |(kind, _)| kind).to_string();
        let mut pieces: Vec<Piece> = Vec::new();
        let mut current: Option<(String, Vec<String>)> = None;
        for slot in range {
            while verse < verses.starts.len() && verses.starts.get(verse) <= slot {
                if verses.starts.get(verse) == slot && verses.ends.get(verse) > slot {
                    pieces.extend(current.take().map(|(words, styles)| Piece::Text(words, styles)));
                    let name = verses.names.get(verse as u32);
                    pieces.push(Piece::Verse(name.split_once(':').map_or(name.clone(), |(_, number)| number.to_string())));
                }
                verse += 1;
            }
            let mut styles: Vec<String> = overlapping.iter().filter(|(span, _)| span.contains(&slot)).map(|(_, name)| name.clone()).collect();
            styles.sort_unstable();
            styles.dedup();
            let words = format!("{}{}{}", text.before.get(slot), text.text.get(slot), text.after.get(slot));
            match &mut current {
                Some((all, current_styles)) if *current_styles == styles => all.push_str(&words),
                _ => { pieces.extend(current.replace((words, styles)).map(|(words, styles)| Piece::Text(words, styles))); }
            }
        }
        pieces.extend(current.take().map(|(words, styles)| Piece::Text(words, styles)));
        paragraphs.push(Paragraph { style: text.paragraphs.names.get(paragraph as u32), kind, pieces });
    }
    Ok(Reading { passage: passage.to_string(), paragraphs })
}

/// `3:16` → (3, 16), and `3:16a` too
fn verse_number(name: &str) -> Option<(u32, u32)> {
    let (chapter, verse) = name.split_once(':')?;
    let digits = |text: &str| text.chars().take_while(char::is_ascii_digit).collect::<String>().parse::<u32>().ok();
    Some((digits(chapter)?, digits(verse)?))
}

/// What's said about (or what cites) a passage of Scripture, in one entry of a commentary, dictionary, etc.
pub struct Comment {
    pub edition: String,
    /// `commentary` or `dictionary`
    pub work: String,
    /// Where the entry is: its document, then its name
    pub locator: String,
    pub title: String,
    /// `about` if the entry is about the passage, or `cites` if it only refers to it
    pub kind: &'static str,
    /// The passage that the entry is about or cites
    pub passage: String,
    pub text: String,
}

pub struct About {
    pub total: usize,
    pub comments: Vec<Comment>,
}

/// "What do the commentators say about this passage?" Finds every entry that's anchored to any part of the passage:
/// first the ones that are about it (starting with those whose own passage is closest to this one), then the ones that cite it.
pub fn about(library: &Library, passage: &Passage, edition: Option<&str>, limit: usize, length: usize) -> Result<About> {
    struct Candidate { kind: u32, distance: u32, module: usize, anchor: usize, shown: std::ops::Range<u32> }
    let mut opened = Vec::new();
    let mut candidates = Vec::new();
    for installed in library.item_modules(edition) {
        if !installed.module.has("anchor.from") { continue; }
        let anchors = Anchors::open(&installed.module)?;
        let text = Text::open(&installed.module)?;
        let sentences = Nodes::open(&installed.module, "sentence")?;
        if let Some(book) = anchors.books.find(&passage.book) {
            let (wanted_from, wanted_to) = (pack(book as u32, passage.from), pack(book as u32, passage.to));
            let mut seen = BTreeSet::new();
            // Every anchor of this book that starts at or before the end of the passage, and doesn't end before it starts
            for anchor in anchors.from.lower_bound(pack(book as u32, (0, 0)))..anchors.from.upper_bound(wanted_to) {
                let (from, to) = (anchors.from.get(anchor), anchors.to.get(anchor));
                if to < wanted_from { continue; }
                let (kind, start) = (anchors.kind.get(anchor), anchors.start.get(anchor));
                let shown = if kind == 0 { start..anchors.end.get(anchor) } // The whole entry
                    else { sentences.containing(start).or_else(|| sentences.containing(start.saturating_sub(1))).map_or(start..anchors.end.get(anchor), |sentence| sentences.range(sentence)) };
                if seen.insert((kind, shown.start)) { candidates.push(Candidate { kind, distance: from.abs_diff(wanted_from) + to.abs_diff(wanted_to), module: opened.len(), anchor, shown }); }
            }
        }
        opened.push((installed, anchors, text));
    }
    candidates.sort_by_key(|candidate| (candidate.kind, candidate.distance, candidate.module, candidate.anchor));
    let comments = candidates.iter().take(limit).map(|candidate| {
        let (installed, anchors, text) = &opened[candidate.module];
        let ((_, from), (_, to)) = (unpack(anchors.from.get(candidate.anchor)), unpack(anchors.to.get(candidate.anchor)));
        let entry = anchors.entry.get(candidate.anchor);
        Ok(Comment { edition: installed.edition.clone(), work: installed.work.clone(), locator: text.reference(anchors.start.get(candidate.anchor)),
                     title: Column::open(&installed.module, "node.entry.title")?.get(entry), kind: if candidate.kind == 0 { "about" } else { "cites" },
                     passage: Passage { book: passage.book.clone(), from, to }.to_string(), text: text.excerpt(candidate.shown.clone(), length) })
    }).collect::<Result<Vec<_>>>()?;
    Ok(About { total: candidates.len(), comments })
}

/// One entry of a dictionary (or of a commentary, etc.)
pub struct EntryFound {
    pub edition: String,
    pub work: String,
    pub locator: String,
    pub title: String,
    /// What kind of entry the source says that it is, e.g., `Article` or `Map`
    pub kind: String,
    pub text: String,
    /// The titles of the entries that this one links to (or where they are, for entries without titles)
    pub see: Vec<String>,
}

pub struct Entries {
    pub total: usize,
    pub entries: Vec<EntryFound>,
}

/// Look entries up by the words of their titles, e.g., `aaron` or `abel*`. Exact titles come first, then the shortest ones.
pub fn entries(library: &Library, words: &[String], edition: Option<&str>, limit: usize, length: usize) -> Result<Entries> {
    let wanted: Vec<String> = words.iter().flat_map(|word| title_words(word)).collect();
    if wanted.is_empty() { return Err("no words to look up".into()); }
    let (mut opened, mut matches) = (Vec::new(), Vec::new());
    for installed in library.item_modules(edition) {
        let titles = Column::open(&installed.module, "node.entry.title")?;
        let mut common: Option<BTreeSet<u32>> = None;
        for word in &wanted {
            let found: BTreeSet<u32> = find_terms(&installed.module, "idx.entry", std::slice::from_ref(word))?.0.into_iter().collect();
            common = Some(match common { Some(previous) => previous.intersection(&found).copied().collect(), None => found });
        }
        for entry in common.unwrap_or_default() {
            let title_words = title_words(&titles.get(entry));
            let exact = title_words.iter().map(|word| word.trim_end_matches('*')).eq(wanted.iter().map(|word| word.trim_end_matches('*')));
            matches.push((!exact, title_words.len(), opened.len(), entry));
        }
        opened.push((installed, titles));
    }
    matches.sort_unstable();
    let entries = matches.iter().take(limit).map(|&(_, _, module, entry)| {
        let (installed, titles) = &opened[module];
        let text = Text::open(&installed.module)?;
        let nodes = Nodes::open(&installed.module, "entry")?;
        let range = nodes.range(entry as usize);
        let mut see = Vec::new();
        if installed.module.has("link.start") {
            let (starts, targets) = (installed.module.packed("link.start")?, installed.module.packed("link.target")?);
            for link in starts.lower_bound(range.start)..starts.lower_bound(range.end.max(range.start + 1)) {
                let target = targets.get(link);
                let title = match titles.get(target) { title if title.is_empty() => text.reference(nodes.starts.get(target as usize)), title => title };
                if !see.contains(&title) && see.len() < 12 { see.push(title); }
            }
        }
        Ok(EntryFound { edition: installed.edition.clone(), work: installed.work.clone(), locator: text.reference(range.start), title: titles.get(entry),
                        kind: Column::open(&installed.module, "node.entry.type")?.get(entry), text: text.excerpt(range, length), see })
    }).collect::<Result<Vec<_>>>()?;
    Ok(Entries { total: matches.len(), entries })
}

/// How a title is looked up: in lower case, as separate words, without punctuation (but keeping a final `*`).
/// The compiler indexes titles in the same way.
pub fn title_words(title: &str) -> Vec<String> {
    let lowered: String = title.to_lowercase().chars().filter(|character| !matches!(character, '\'' | '’')).collect();
    lowered.split(|character: char| !character.is_alphanumeric() && character != '*').filter(|word| !word.trim_end_matches('*').is_empty()).map(str::to_string).collect()
}

fn example(text: &Text, slot: u32) -> Example {
    let paragraph = || text.paragraphs.containing(slot).map_or(slot..slot + 1, |paragraph| text.paragraphs.range(paragraph)); // e.g., a psalm title
    let range = text.verse(slot).unwrap_or_else(paragraph);
    Example { reference: text.reference(slot), text: text.render(range) }
}

/// `c:d:H0776` → `H0776` (drops the prefixes that mark attached Hebrew particles)
fn base_strong(strong: &str) -> String { strong.rsplit(':').next().unwrap_or(strong).to_string() }

/// Provisional: matches the ingest's `norm` column only for unaccented words
fn normalise(words: &[String]) -> Vec<String> { words.iter().map(|word| word.to_lowercase()).collect() }
