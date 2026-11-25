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
    /// How many sections it has to read (see `read_section`), not counting anything before the first one
    pub sections: usize,
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
        let sections = match units(&module, &chapters)? { Some(units) => units.starts.lower_bound(end) - units.starts.lower_bound(start), None => 0 };
        Ok(Document { name: text.document_names.get(document), chapters: highest, introduction, sections })
    }).collect()
}

/// A piece of a paragraph, for displaying it
pub enum Piece {
    /// A chapter's first verse comes next: the chapter's number
    Chapter(String),
    /// A verse starts here: its name as the edition gives it, e.g., `3:16`
    Verse(String),
    /// Some text, and the character styles that it has (e.g., `add`, `nd`, or `wj`).
    /// When the words were asked for separately, each piece is one word with its punctuation, and has that word's slot.
    Text(String, Vec<String>, Option<u32>),
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
pub fn read(library: &Library, edition: &str, passage: &Passage, separate_words: bool) -> Result<Reading> {
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
    } else if let Some(range) = verse_slots(verses, document_start..document_end, passage) { // Just the verses
        (start, end) = (range.start, range.end);
    }
    if start >= end { return Err(format!("'{edition}' doesn't have {passage}").into()); }
    Ok(Reading { passage: passage.to_string(), paragraphs: lay_out(&module, &text, verses, start..end, separate_words)? })
}

/// What an edition is read in: its sections (from one heading to the next) if it has any, or else its chapters
fn units(module: &crate::format::Module, chapters: &Option<Nodes>) -> Result<Option<Nodes>> {
    if module.has("node.section.starts") { return Nodes::open(module, "section").map(Some); }
    match chapters { Some(_) => Nodes::open(module, "chapter").map(Some), None => Ok(None) }
}

/// Which section to read
pub enum Wanted<'a> {
    /// The one that this passage starts in
    At(&'a Passage),
    /// By its number within a document: 1 is the first, and 0 is whatever comes before that (titles and an introduction)
    Number(&'a str, usize),
}

pub struct SectionReading {
    pub document: String,
    /// This section's number within its document (0 for what comes before the first section)
    pub number: usize,
    /// Its heading (or its chapter number, in an edition without headings)
    pub title: String,
    /// The verses that it covers, e.g., `JHN 3:1-21` (or just the document, if it has no verses)
    pub passage: String,
    /// The sections before and after it, which can be in other documents
    pub previous: Option<(String, usize)>,
    pub next: Option<(String, usize)>,
    pub paragraphs: Vec<Paragraph>,
    /// The verses that an installed commentary has a note of their own on (one that starts at that verse), e.g., `3:16`
    pub noted: Vec<String>,
}

/// One section of Scripture laid out for reading: from one section heading to the next (which can cross from one chapter into another).
pub fn read_section(library: &Library, edition: &str, wanted: Wanted, separate_words: bool) -> Result<SectionReading> {
    let module = library.text_module(edition)?;
    let text = Text::open(&module)?;
    let Some(verses) = &text.verses else { return Err(format!("'{edition}' isn't divided into verses").into()) };
    let chapters = if module.has("node.chapter.starts") { Some(Nodes::open(&module, "chapter")?) } else { None };
    let units = units(&module, &chapters)?.ok_or_else(|| format!("'{edition}' has neither sections nor chapters"))?;
    let document_count = text.document_names.len();
    let bounds = |document: usize| (text.document_starts.get(document), text.document_starts.get(document + 1));
    // The units of a document: (the number of the first one among all the units, how many there are, whether there's anything before the first)
    let units_of = |document: usize| {
        let (start, end) = bounds(document);
        let (first, after) = (units.starts.lower_bound(start), units.starts.lower_bound(end));
        (first, after - first, end > start && (first == after || units.starts.get(first) > start))
    };
    let find_document = |name: &str| (0..document_count).find(|&document| text.document_names.get(document) == name).ok_or_else(|| format!("'{edition}' doesn't have {name}"));

    let (document, number) = match wanted {
        Wanted::Number(name, number) => (find_document(name)?, number),
        Wanted::At(passage) => {
            let document = find_document(&passage.book)?;
            let (start, end) = bounds(document);
            // The first verse at or after where the passage starts (or the start of the document, for a passage that's the whole of it)
            let slot = (verses.starts.lower_bound(start)..verses.starts.lower_bound(end))
                .find(|&verse| verses.ends.get(verse) > verses.starts.get(verse) && verse_number(&verses.names.get(verse as u32)).is_some_and(|number| number >= passage.from))
                .map_or(start, |verse| verses.starts.get(verse));
            let (first, _, _) = units_of(document);
            (document, (units.starts.upper_bound(slot)).saturating_sub(first))
        }
    };
    let (document_start, document_end) = bounds(document);
    let (first, count, before) = units_of(document);
    if number > count || (number == 0 && !before) { return Err(format!("{} has no section {number}", text.document_names.get(document)).into()); }
    let range = if number == 0 { document_start..if count == 0 { document_end } else { units.starts.get(first) } }
        else { units.starts.get(first + number - 1)..if number < count { units.starts.get(first + number) } else { document_end } };

    // The neighbouring sections, going on into the next document (or back into the one before) at either end
    let name = |document: usize| text.document_names.get(document);
    let previous = if number > 1 || (number == 1 && before) { Some((name(document), number - 1)) } else {
        (0..document).rev().map(|other| (other, units_of(other))).find(|(_, (_, count, before))| *count > 0 || *before).map(|(other, (_, count, _))| (name(other), count))
    };
    let next = if number < count { Some((name(document), number + 1)) } else {
        (document + 1..document_count).map(|other| (other, units_of(other))).find(|(_, (_, count, before))| *count > 0 || *before)
            .map(|(other, (_, _, before))| (name(other), if before { 0 } else { 1 }))
    };
    let inside: Vec<(u32, u32)> = (verses.starts.lower_bound(range.start)..verses.starts.lower_bound(range.end))
        .filter(|&verse| verses.ends.get(verse) > verses.starts.get(verse)).filter_map(|verse| verse_number(&verses.names.get(verse as u32))).collect();
    let passage = match (inside.iter().min(), inside.iter().max()) {
        (Some(&from), Some(&to)) => Passage { book: name(document), from, to }.to_string(),
        _ => name(document),
    };
    let title = if number == 0 { String::new() } else { units.names.get((first + number - 1) as u32) };
    let noted = match (inside.iter().min(), inside.iter().max()) {
        (Some(&from), Some(&to)) => noted_verses(library, &name(document), from, to)?.into_iter().map(|(chapter, verse)| format!("{chapter}:{verse}")).collect(),
        _ => Vec::new(),
    };
    Ok(SectionReading { document: name(document), number, title, passage, previous, next, paragraphs: lay_out(&module, &text, verses, range, separate_words)?, noted })
}

/// The verses from `from` to `to` (in one book) that an installed commentary has a note on that starts at that verse
fn noted_verses(library: &Library, book: &str, from: (u32, u32), to: (u32, u32)) -> Result<BTreeSet<(u32, u32)>> {
    let mut noted = BTreeSet::new();
    for installed in library.item_modules(None) {
        if !installed.module.has("anchor.from") { continue; }
        let anchors = Anchors::open(&installed.module)?;
        let Some(number) = anchors.books.find(book) else { continue };
        for anchor in anchors.from.lower_bound(pack(number as u32, from))..anchors.from.upper_bound(pack(number as u32, to)) {
            if anchors.kind.get(anchor) == 0 { noted.insert(unpack(anchors.from.get(anchor)).1); }
        }
    }
    Ok(noted)
}

/// Lay a range of slots out as paragraphs
fn lay_out(module: &crate::format::Module, text: &Text, verses: &Nodes, range: std::ops::Range<u32>, separate_words: bool) -> Result<Vec<Paragraph>> {
    let (start, end) = (range.start, range.end);
    // The character styles that overlap the passage (they're in order of where they start, and none is very long)
    let mut overlapping: Vec<(std::ops::Range<u32>, String)> = Vec::new();
    if module.has("node.span.starts") { // (An edition needn't have any)
        let spans = Nodes::open(module, "span")?;
        overlapping = (spans.starts.lower_bound(start.saturating_sub(2000))..spans.starts.lower_bound(end))
            .map(|span| (spans.range(span), span)).filter(|(range, _)| range.end > start).map(|(range, span)| (range, spans.names.get(span as u32))).collect();
    }
    let attributes = Column::open(module, "node.para.attributes")?;
    let mut paragraphs = Vec::new();
    let mut verse = verses.starts.lower_bound(start);
    let mut chapter: Option<u32> = None; // Of the last verse that was laid out
    // From the first paragraph that starts in the passage, or the one before it if that runs on into the passage
    let mut first = text.paragraphs.starts.lower_bound(start);
    if first > 0 && text.paragraphs.ends.get(first - 1) > start { first -= 1; }
    for paragraph in first..text.paragraphs.starts.lower_bound(end) {
        let range = text.paragraphs.starts.get(paragraph).max(start)..text.paragraphs.ends.get(paragraph).min(end);
        if range.start >= range.end { continue; }
        let attribute_text = attributes.get(paragraph as u32); // JSON, as the ingest writes it
        let kind = attribute_text.split_once("\"kind\": \"").and_then(|(_, rest)| rest.split_once('"')).map_or("other", |(kind, _)| kind).to_string();
        let mut pieces: Vec<Piece> = Vec::new();
        let mut current: Option<(String, Vec<String>, Option<u32>)> = None;
        for slot in range {
            while verse < verses.starts.len() && verses.starts.get(verse) <= slot {
                if verses.starts.get(verse) == slot && verses.ends.get(verse) > slot {
                    pieces.extend(current.take().map(|(words, styles, slot)| Piece::Text(words, styles, slot)));
                    let name = verses.names.get(verse as u32);
                    // A new chapter is marked before its first verse (but not at the start of a passage that starts part-way through a chapter)
                    if let Some((number, verse_number)) = verse_number(&name) {
                        if chapter.map_or(verse_number <= 1, |previous| previous != number) { pieces.push(Piece::Chapter(number.to_string())); }
                        chapter = Some(number);
                    }
                    pieces.push(Piece::Verse(name));
                }
                verse += 1;
            }
            let mut styles: Vec<String> = overlapping.iter().filter(|(span, _)| span.contains(&slot)).map(|(_, name)| name.clone()).collect();
            styles.sort_unstable();
            styles.dedup();
            let words = format!("{}{}{}", text.before.get(slot), text.text.get(slot), text.after.get(slot));
            match &mut current {
                Some((all, current_styles, None)) if *current_styles == styles && !separate_words => all.push_str(&words),
                _ => { pieces.extend(current.replace((words, styles, separate_words.then_some(slot))).map(|(words, styles, slot)| Piece::Text(words, styles, slot))); }
            }
        }
        pieces.extend(current.take().map(|(words, styles, slot)| Piece::Text(words, styles, slot)));
        paragraphs.push(Paragraph { style: text.paragraphs.names.get(paragraph as u32), kind, pieces });
    }
    Ok(paragraphs)
}

/// The slots of the verses of a passage, within one document's slots
fn verse_slots(verses: &Nodes, document: std::ops::Range<u32>, passage: &Passage) -> Option<std::ops::Range<u32>> {
    let (mut start, mut end) = (u32::MAX, 0);
    for verse in verses.starts.lower_bound(document.start)..verses.starts.lower_bound(document.end) {
        let Some(number) = verse_number(&verses.names.get(verse as u32)) else { continue };
        if number >= passage.from && number <= passage.to && verses.ends.get(verse) > verses.starts.get(verse) {
            start = start.min(verses.starts.get(verse)); end = end.max(verses.ends.get(verse));
        }
    }
    (start < end).then_some(start..end)
}

/// `3:16` → (3, 16), and `3:16a` too
fn verse_number(name: &str) -> Option<(u32, u32)> {
    let (chapter, verse) = name.split_once(':')?;
    let digits = |text: &str| text.chars().take_while(char::is_ascii_digit).collect::<String>().parse::<u32>().ok();
    Some((digits(chapter)?, digits(verse)?))
}

/// An original-language word that a word of a translation translates
pub struct Original {
    pub edition: String,
    pub reference: String,
    pub text: String,
    pub transliteration: String,
    pub lemma: String,
    pub lemma_transliteration: String,
    pub strong: String,
    pub morphology: String,
    pub gloss: String,
    /// How many times the lemma occurs in its edition
    pub occurrences: usize,
    /// How many of those were looked at for the renderings (a very common word isn't followed up everywhere)
    pub counted: usize,
    /// How the translation renders the lemma, with how often, the commonest first
    pub renderings: Vec<(String, usize)>,
    /// The word's meaning in this place, from a dictionary that gives meanings place by place (the UBS dictionaries so far)
    pub meaning: Option<Meaning>,
    /// Articles about the thing that the word refers to (e.g., in a handbook of animals): (edition, locator, title)
    pub articles: Vec<(String, String, String)>,
}

pub struct Meaning {
    pub gloss: String,
    pub definition: String,
    pub note: String,
    /// e.g., a Louw-Nida number such as 67.65
    pub code: String,
    /// The semantic domains that this meaning belongs to, e.g., `Time > A Point of Time with Reference to Duration of Time: Beginning, End`
    pub domains: Vec<String>,
}

pub struct WordInfo {
    pub text: String,
    pub reference: String,
    pub originals: Vec<Original>,
    /// In every installed translation that's aligned to the same originals (this one included):
    /// the words that translate them, e.g., to mark them in the OET-RV and the OET-LV side by side
    pub linked: Vec<(String, Vec<u32>)>,
}

/// How many occurrences of a lemma are followed up to see how it's rendered
const RENDERINGS_SAMPLE: usize = 4000;

/// The slots in the translation that each of these original-language slots is rendered by (in the same order)
fn rendered_by(alignment: &crate::format::Module, targets: &[u32]) -> Result<Vec<Vec<u32>>> {
    let (to, from) = (alignment.packed("rlinks.to")?, alignment.packed("rlinks.from")?);
    Ok(targets.iter().map(|&target| {
        let mut slots = Vec::new();
        let mut link = to.lower_bound(target);
        while link < to.len() && to.get(link) == target { slots.push(from.get(link)); link += 1; }
        slots.sort_unstable();
        slots
    }).collect())
}

/// "What does this word translate?" Follows a word of a translation to the original-language word(s) behind it,
/// with their details, and how else the translation renders the same lemma.
pub fn word(library: &Library, edition: &str, slot: u32) -> Result<WordInfo> {
    let text = Text::open(&*library.text_module(edition)?)?;
    if slot >= text.document_starts.get(text.document_starts.len() - 1) { return Err(format!("'{edition}' has no word {slot}").into()); }
    let mut originals = Vec::new();
    let mut targets: Vec<(String, u32)> = Vec::new();
    for alignment in library.alignments_from(edition) {
        let (from, to) = (alignment.module.packed("links.from")?, alignment.module.packed("links.to")?);
        let mut link = from.lower_bound(slot);
        if link >= from.len() || from.get(link) != slot { continue; }
        let original_text = Text::open(&*library.text_module(&alignment.to)?)?;
        let value = |column: &str, target: u32| -> Result<String> { Ok(library.column(&alignment.to, column)?.map_or(String::new(), |column| column.get(target))) };
        while link < from.len() && from.get(link) == slot {
            let target = to.get(link);
            link += 1;
            targets.push((alignment.to.clone(), target));
            let lemma = value("lemma", target)?;
            // Every occurrence of the lemma, and how each is rendered (as the translation's words in order, in lower case)
            let lemma_module = library.column_module(&alignment.to, "lemma");
            let occurrences = match (&lemma_module, lemma.is_empty()) { (Some(module), false) => find_terms(module, "col.lemma", std::slice::from_ref(&lemma))?.0, _ => Vec::new() };
            let sample = &occurrences[..occurrences.len().min(RENDERINGS_SAMPLE)];
            let mut counts: HashMap<String, usize> = HashMap::new();
            for slots in rendered_by(&alignment.module, sample)? {
                if slots.is_empty() { continue; }
                let words: Vec<String> = slots.iter().map(|&slot| text.text.get(slot).to_lowercase()).collect();
                *counts.entry(words.join(" ")).or_default() += 1;
            }
            let mut renderings: Vec<(String, usize)> = counts.into_iter().collect();
            renderings.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
            renderings.truncate(12);
            let gloss = match value("gloss", target)? { gloss if gloss.is_empty() => value("context_gloss", target)?, gloss => gloss };
            let meaning = match value("meaning_gloss", target)? {
                gloss if gloss.is_empty() && value("meaning_definition", target)?.is_empty() => None,
                gloss => Some(Meaning { gloss, definition: value("meaning_definition", target)?, note: value("meaning_note", target)?, code: value("meaning_code", target)?,
                                        domains: value("domains", target)?.split(';').filter(|domain| !domain.is_empty()).map(str::to_string).collect() }),
            };
            let mut articles = Vec::new();
            for locator in value("handbook", target)?.split(';').filter(|locator| !locator.is_empty()) {
                if let Some((installed, entry)) = find_entry(library, None, locator)? {
                    articles.push((installed.edition.clone(), locator.to_string(), Column::open(&installed.module, "node.entry.title")?.get(entry)));
                }
            }
            originals.push(Original { edition: alignment.to.clone(), reference: original_text.reference(target), text: original_text.text.get(target),
                                      transliteration: value("translit", target)?, lemma_transliteration: value("lemma_translit", target)?, strong: base_strong(&value("strong", target)?),
                                      morphology: value("morph", target)?, gloss, occurrences: occurrences.len(), counted: sample.len(), renderings, lemma, meaning, articles });
        }
    }
    let mut linked: BTreeMap<String, Vec<u32>> = BTreeMap::new();
    for alignment in library.modules.iter().filter(|installed| installed.kind == "alignment") {
        let wanted: Vec<u32> = targets.iter().filter(|(original, _)| *original == alignment.to).map(|&(_, target)| target).collect();
        if wanted.is_empty() { continue; }
        let slots = linked.entry(alignment.from.clone()).or_default();
        for rendering in rendered_by(&alignment.module, &wanted)? { slots.extend(rendering); }
        slots.sort_unstable();
        slots.dedup();
    }
    Ok(WordInfo { text: text.text.get(slot), reference: text.reference(slot), originals, linked: linked.into_iter().collect() })
}

/// Every verse of a translation that has a word translating this original-language lemma
pub fn lemma_verses(library: &Library, edition: &str, original_edition: &str, lemma: &str, limit: usize) -> Result<Found> {
    let text = Text::open(&*library.text_module(edition)?)?;
    let alignment = library.alignments_from(edition).into_iter().find(|alignment| alignment.to == original_edition)
        .ok_or_else(|| format!("no alignment from '{edition}' to '{original_edition}' is installed"))?;
    let lemma_module = library.column_module(original_edition, "lemma").ok_or_else(|| format!("'{original_edition}' has no lemmas installed"))?;
    let occurrences = find_terms(&lemma_module, "col.lemma", &[lemma.to_string()])?.0;
    let mut verse_starts: Vec<u32> = rendered_by(&alignment.module, &occurrences)?.into_iter().filter_map(|slots| slots.first().copied())
        .map(|slot| text.verse(slot).map_or(slot, |verse| verse.start)).collect();
    verse_starts.sort_unstable();
    verse_starts.dedup();
    let mut forms = BTreeMap::new();
    forms.insert(lemma.to_string(), occurrences.len());
    Ok(Found { total: verse_starts.len(), forms, examples: verse_starts.iter().take(limit).map(|&slot| example(&text, slot)).collect() })
}

/// The entry of a commentary, dictionary, etc. at a locator such as `Fauna 2.10` or `Articles Aaron` (the document, then the entry's name),
/// in one edition or in whichever installed one has it
pub fn find_entry<'a>(library: &'a Library, edition: Option<&'a str>, locator: &str) -> Result<Option<(&'a crate::library::Installed, u32)>> {
    let Some((document, name)) = locator.split_once(' ') else { return Ok(None) };
    for installed in library.item_modules(edition) {
        let documents = installed.module.strings("documents.names")?;
        let Some(number) = (0..documents.len()).find(|&number| documents.get(number) == document) else { continue };
        let starts = installed.module.packed("documents.starts")?;
        let entries = Nodes::open(&installed.module, "entry")?;
        for entry in entries.starts.lower_bound(starts.get(number))..entries.starts.lower_bound(starts.get(number + 1)) {
            if entries.names.get(entry as u32) == name { return Ok(Some((installed, entry as u32))); }
        }
    }
    Ok(None)
}

/// One whole entry of a commentary, dictionary, etc., laid out for reading
pub struct Article {
    pub edition: String,
    pub work: String,
    pub locator: String,
    pub title: String,
    /// (style, kind, text) for each paragraph, e.g., (`h2`, `heading`, `Discussion:`)
    pub paragraphs: Vec<(String, String, String)>,
    /// The entries that it links to: (locator, title)
    pub see: Vec<(String, String)>,
    /// The entries before and after it in its work (e.g., the chapters of a book)
    pub previous: Option<String>,
    pub next: Option<String>,
}

pub fn article(library: &Library, edition: Option<&str>, locator: &str) -> Result<Article> {
    let (installed, entry) = find_entry(library, edition, locator)?.ok_or_else(|| format!("there's no entry '{locator}'"))?;
    let module = &installed.module;
    let text = Text::open(module)?;
    let entries = Nodes::open(module, "entry")?;
    let titles = Column::open(module, "node.entry.title")?;
    let range = entries.range(entry as usize);
    let attributes = Column::open(module, "node.para.attributes")?;
    let mut paragraphs = Vec::new();
    for paragraph in text.paragraphs.starts.lower_bound(range.start)..text.paragraphs.starts.lower_bound(range.end) {
        let span = text.paragraphs.range(paragraph);
        let attribute_text = attributes.get(paragraph as u32);
        let kind = attribute_text.split_once("\"kind\": \"").and_then(|(_, rest)| rest.split_once('"')).map_or("body", |(kind, _)| kind).to_string();
        let words = if span.is_empty() { attribute_text.split_once("\"text\": \"").and_then(|(_, rest)| rest.split_once('"')).map_or(String::new(), |(text, _)| text.to_string()) }
                    else { text.render(span) };
        paragraphs.push((text.paragraphs.names.get(paragraph as u32), kind, words));
    }
    let mut see = Vec::new();
    if module.has("link.start") {
        let (starts, targets) = (module.packed("link.start")?, module.packed("link.target")?);
        for link in starts.lower_bound(range.start)..starts.lower_bound(range.end.max(range.start + 1)) {
            let target = targets.get(link);
            let item = (text.reference(entries.starts.get(target as usize)), titles.get(target));
            if !see.contains(&item) { see.push(item); }
        }
    }
    let locator_of = |entry: usize| text.reference(entries.starts.get(entry));
    let previous = (entry > 0).then(|| locator_of(entry as usize - 1));
    let next = ((entry as usize) + 1 < entries.starts.len()).then(|| locator_of(entry as usize + 1));
    Ok(Article { edition: installed.edition.clone(), work: installed.work.clone(), locator: text.reference(range.start), title: titles.get(entry), paragraphs, see, previous, next })
}

/// The entries of a commentary, dictionary, book, etc., in order: (locator, title, type)
pub fn contents_of(library: &Library, edition: &str) -> Result<Vec<(String, String, String)>> {
    let installed = library.item_modules(Some(edition)).next().ok_or_else(|| format!("'{edition}' isn't installed, or has no entries"))?;
    let text = Text::open(&installed.module)?;
    let entries = Nodes::open(&installed.module, "entry")?;
    let (titles, types) = (Column::open(&installed.module, "node.entry.title")?, Column::open(&installed.module, "node.entry.type")?);
    Ok((0..entries.starts.len()).map(|entry| (text.reference(entries.starts.get(entry)), titles.get(entry as u32), types.get(entry as u32))).collect())
}

/// A word (in its dictionary form) that has a meaning in a semantic domain
pub struct DomainWord {
    pub lemma: String,
    pub transliteration: String,
    /// Its commonest gloss in this domain
    pub gloss: String,
    pub count: usize,
}

/// "What other words mean something like this?" Every dictionary form of an original-language edition that has a meaning
/// in a semantic domain, the commonest first
pub fn domain(library: &Library, original: &str, domain: &str, limit: usize) -> Result<(usize, Vec<DomainWord>)> {
    let module = library.column_module(original, "domains").ok_or_else(|| format!("no semantic domains are installed for '{original}'"))?;
    let (slots, _) = find_terms(&module, "idx.domains", &[domain.to_string()])?;
    let lemmas = library.column(original, "lemma")?.ok_or_else(|| format!("'{original}' has no lemmas installed"))?;
    let transliterations = library.column(original, "lemma_translit")?;
    let glosses = library.column(original, "meaning_gloss")?;
    let mut groups: BTreeMap<u32, (usize, u32, HashMap<u32, usize>)> = BTreeMap::new(); // lemma → (count, a slot, gloss counts)
    for &slot in &slots {
        let group = groups.entry(lemmas.ids.get(slot as usize)).or_insert((0, slot, HashMap::new()));
        group.0 += 1;
        if let Some(glosses) = &glosses { *group.2.entry(glosses.ids.get(slot as usize)).or_default() += 1; }
    }
    let mut words: Vec<(usize, u32, u32, HashMap<u32, usize>)> = groups.into_iter().map(|(lemma, (count, slot, glosses))| (count, lemma, slot, glosses)).collect();
    words.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)));
    let total = words.len();
    let words = words.into_iter().take(limit).map(|(count, lemma, slot, gloss_counts)| DomainWord {
        lemma: lemmas.dictionary.get(lemma as usize),
        transliteration: transliterations.as_ref().map_or(String::new(), |column| column.get(slot)),
        gloss: match (&glosses, gloss_counts.into_iter().max_by(|a, b| a.1.cmp(&b.1).then(b.0.cmp(&a.0)))) { (Some(glosses), Some((gloss, _))) => glosses.dictionary.get(gloss as usize), _ => String::new() },
        count,
    }).collect();
    Ok((total, words))
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
        for (exact, words, entry) in titled(&installed.module, &titles, &wanted)? { matches.push((!exact, words, opened.len(), entry)); }
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

/// The entries of one module whose titles have all of these words: (whether that's the whole title, how many words the title has, the entry)
fn titled(module: &crate::format::Module, titles: &Column, wanted: &[String]) -> Result<Vec<(bool, usize, u32)>> {
    let mut common: Option<BTreeSet<u32>> = None;
    for word in wanted {
        let found: BTreeSet<u32> = find_terms(module, "idx.entry", std::slice::from_ref(word))?.0.into_iter().collect();
        common = Some(match common { Some(previous) => previous.intersection(&found).copied().collect(), None => found });
    }
    Ok(common.unwrap_or_default().into_iter().map(|entry| {
        let title_words = title_words(&titles.get(entry));
        let exact = title_words.iter().map(|word| word.trim_end_matches('*')).eq(wanted.iter().map(|word| word.trim_end_matches('*')));
        (exact, title_words.len(), entry)
    }).collect())
}

/// A passage that the entries on a subject refer to
pub struct KeyPassage {
    pub passage: String,
    /// The titles of the entries that refer to it
    pub sources: Vec<String>,
    /// Its text in the edition being read (empty if that edition doesn't have it)
    pub text: String,
}

/// What's known about a subject (see `topic`)
pub struct Topic {
    /// The entry titles that the thesaurus gives for the subject, and for the other side of the question
    pub see: Vec<String>,
    pub contrast: Vec<String>,
    /// Entries on the subject, and the passages that they refer to most
    pub entries: Vec<EntryFound>,
    pub passages: Vec<KeyPassage>,
    /// The same for the other side of the question
    pub other_entries: Vec<EntryFound>,
    pub other_passages: Vec<KeyPassage>,
    /// Where the words themselves are found: together in a sentence of the edition being read, and in a paragraph of a commentary or dictionary
    pub scripture: Vec<Example>,
    pub mentions: Vec<Example>,
}

/// "What do the Scriptures and the commentators say about …?" Nothing is generated: the answer is entries from the installed
/// dictionaries and commentaries (found by their titles, and through the thesaurus), the passages that those entries refer to most,
/// the same again for the other side of the question where the thesaurus names one, and the places where the words themselves are found.
pub fn topic(library: &Library, edition: &str, words: &[String], limit: usize, length: usize) -> Result<Topic> {
    let wanted: Vec<String> = words.iter().flat_map(|word| title_words(word)).map(|word| word.trim_end_matches('*').to_string()).collect();
    if wanted.is_empty() { return Err("no words to look up".into()); }
    let (mut see, mut contrast) = (Vec::new(), Vec::new());
    for installed in library.modules.iter().filter(|installed| installed.kind == "thesaurus") {
        if let Some(term) = installed.module.strings("term.dict")?.find(&wanted.join(" ")) {
            let list = |section: &str| -> Result<Vec<String>> {
                Ok(installed.module.strings(section)?.get(term).split(';').map(|title| title.trim().to_string()).filter(|title| !title.is_empty()).collect())
            };
            see.extend(list("term.see")?);
            contrast.extend(list("term.contrast")?);
        }
    }
    let reading = library.text_module(edition).ok().map(|module| Text::open(&module)).transpose()?;

    // One side of the question: the entries with these titles, and the passages that they refer to most
    let side = |titles_wanted: &[String], with_query: bool| -> Result<(Vec<EntryFound>, Vec<KeyPassage>)> {
        let (mut entries, mut passages): (Vec<EntryFound>, BTreeMap<(String, (u32, u32), (u32, u32)), (u32, Vec<String>)>) = (Vec::new(), BTreeMap::new());
        for installed in library.item_modules(None) {
            let titles = Column::open(&installed.module, "node.entry.title")?;
            // The query's own words: an entry with just that title, or failing that a few that have all the words. The thesaurus's titles: exact ones only.
            let mut found: Vec<u32> = Vec::new();
            if with_query {
                let matches = titled(&installed.module, &titles, &wanted)?;
                let exact: Vec<u32> = matches.iter().filter(|(exact, _, _)| *exact).map(|&(_, _, entry)| entry).collect();
                found = if exact.is_empty() { let mut near = matches; near.sort_by_key(|&(_, words, entry)| (words, entry)); near.iter().take(3).map(|&(_, _, entry)| entry).collect() } else { exact };
            }
            for title in titles_wanted {
                found.extend(titled(&installed.module, &titles, &title_words(title))?.into_iter().filter(|(exact, _, _)| *exact).map(|(_, _, entry)| entry));
            }
            found.sort_unstable();
            found.dedup();
            if found.is_empty() { continue; }
            let text = Text::open(&installed.module)?;
            let nodes = Nodes::open(&installed.module, "entry")?;
            for &entry in &found {
                let range = nodes.range(entry as usize);
                entries.push(EntryFound { edition: installed.edition.clone(), work: installed.work.clone(), locator: text.reference(range.start), title: titles.get(entry),
                                          kind: Column::open(&installed.module, "node.entry.type")?.get(entry), text: text.excerpt(range, length), see: Vec::new() });
            }
            if !installed.module.has("anchor.from") { continue; }
            let anchors = Anchors::open(&installed.module)?;
            for anchor in 0..anchors.entry.len() { // (Every anchor is looked at: they're in passage order, not entry order)
                let entry = anchors.entry.get(anchor);
                if found.binary_search(&entry).is_err() { continue; }
                let ((book, from), (_, to)) = (unpack(anchors.from.get(anchor)), unpack(anchors.to.get(anchor)));
                if to.0 > from.0 + 1 || to.0 >= 999 { continue; } // Not whole books and other long stretches
                let key = (anchors.books.get(book as usize), from, to);
                let scored = passages.entry(key).or_default();
                scored.0 += if anchors.kind.get(anchor) == 0 { 2 } else { 1 };
                let title = titles.get(entry);
                if !scored.1.contains(&title) { scored.1.push(title); }
            }
        }
        // Passages that overlap are taken together (as long as that doesn't make more than about a dozen verses)
        let mut merged: Vec<((String, (u32, u32), (u32, u32)), (u32, Vec<String>))> = Vec::new();
        for ((book, from, to), (score, sources)) in passages { // (In order of book, then of where they start)
            match merged.last_mut() {
                Some(((last_book, last_from, last_to), (last_score, last_sources)))
                    if *last_book == book && from <= *last_to && pack(0, to.max(*last_to)) - pack(0, *last_from) <= 12 => {
                    *last_to = to.max(*last_to);
                    *last_score += score;
                    for source in sources { if !last_sources.contains(&source) { last_sources.push(source); } }
                }
                _ => merged.push(((book, from, to), (score, sources))),
            }
        }
        // The passages that the most entries refer to come first, then the ones referred to most often.
        // After that, the entries take turns, so that one long article doesn't crowd the others out.
        merged.sort_by_key(|(_, (score, sources))| (std::cmp::Reverse(sources.len()), std::cmp::Reverse(*score)));
        let mut turns: BTreeMap<(usize, String), usize> = BTreeMap::new();
        let mut ranked: Vec<_> = merged.into_iter().map(|passage| {
            let turn = turns.entry((passage.1 .1.len(), passage.1 .1[0].clone())).or_default();
            *turn += 1;
            (std::cmp::Reverse(passage.1 .1.len()), *turn, passage)
        }).collect();
        ranked.sort_by(|a, b| (&a.0, a.1).cmp(&(&b.0, b.1)));
        let ranked = ranked.into_iter().map(|(_, _, passage)| passage);
        let passages = ranked.take(limit).map(|((book, from, to), (_, sources))| {
            let passage = Passage { book, from, to };
            let text = reading.as_ref().and_then(|text| {
                let document = (0..text.document_names.len()).find(|&document| text.document_names.get(document) == passage.book)?;
                let slots = verse_slots(text.verses.as_ref()?, text.document_starts.get(document)..text.document_starts.get(document + 1), &passage)?;
                Some(text.excerpt(slots, length))
            }).unwrap_or_default();
            KeyPassage { passage: passage.to_string(), sources, text }
        }).collect();
        Ok((entries, passages))
    };
    let (entries, passages) = side(&see, true)?;
    let (other_entries, mut other_passages) = if contrast.is_empty() { (Vec::new(), Vec::new()) } else { side(&contrast, false)? };
    other_passages.retain(|other| !passages.iter().any(|passage| passage.passage == other.passage));

    // Where the words themselves are found (these can fail harmlessly, e.g., if a word isn't used at all)
    let scripture = find_together(library, edition, &wanted, "sentence", limit).map_or(Vec::new(), |found| found.examples);
    let mut mentions = Vec::new();
    for installed in library.item_modules(None) {
        let found = find_together(library, &installed.edition, &wanted, "para", limit.min(5)).map_or(Vec::new(), |found| found.examples);
        mentions.extend(found.into_iter().map(|example| Example { reference: format!("{} {}", installed.edition, example.reference), text: example.text.chars().take(length).collect() }));
    }
    Ok(Topic { see, contrast, entries, passages, other_entries, other_passages, scripture, mentions })
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

/// A passage found by meaning-based search
pub struct MeaningFound {
    pub edition: String,
    /// `scripture`, `commentary`, `dictionary`, or `book`
    pub work: String,
    /// A passage of Scripture (e.g., `JHN 3:16-3:21`), or an entry's locator (e.g., `Chapter 4`)
    pub locator: String,
    /// The section's heading, or the entry's title (and the heading that the passage is under)
    pub label: String,
    pub text: String,
    /// How close it is to the query, from -1 to 1 (the cosine similarity)
    pub score: f32,
}

/// "Passages that are about this": the query's vector is compared with the vectors of every installed work's passages (see `meaning.rs`).
/// Gives the best `limit` passages of Scripture and, separately, the best `limit` passages of everything else (only the best one from each entry).
/// `editions`, if given, are the only works to search.
pub fn meaning(library: &Library, query: &str, editions: &[String], limit: usize, length: usize) -> Result<(Vec<MeaningFound>, Vec<MeaningFound>)> {
    let model = library.model()?;
    let vector = model.embed_query(query);
    let mut scripture: Vec<(f32, usize, usize)> = Vec::new();
    let mut others: Vec<(f32, usize, usize)> = Vec::new();
    for (index, installed) in library.modules.iter().enumerate() {
        if installed.kind != "vectors" || (!editions.is_empty() && !editions.contains(&installed.edition)) { continue; }
        let vectors = library.vectors_of(installed)?;
        if vectors.model != model.name || vectors.dimensions != vector.len() { continue; } // Made with another model: not comparable
        let found = if installed.work == "scripture" { &mut scripture } else { &mut others };
        let mut scores: Vec<(f32, usize, usize)> = vectors.scores(&vector).into_iter().enumerate().map(|(passage, score)| (score, index, passage)).collect();
        scores.sort_by(|a, b| b.0.total_cmp(&a.0));
        scores.truncate(limit * 4); // Enough to fill the list after passages of the same entry are left out
        found.extend(scores);
    }
    let finish = |mut found: Vec<(f32, usize, usize)>, one_per_entry: bool| -> Result<Vec<MeaningFound>> {
        found.sort_by(|a, b| b.0.total_cmp(&a.0));
        let mut results: Vec<MeaningFound> = Vec::new();
        for (score, index, passage) in found {
            if results.len() >= limit { break; }
            let installed = &library.modules[index];
            let locator = installed.module.strings("vectors.locators")?.get(passage);
            if one_per_entry && results.iter().any(|result| result.edition == installed.edition && result.locator == locator) { continue; }
            // The same passage in another edition of the same work (e.g., a book's modernised edition) is left out too
            let label = installed.module.strings("vectors.labels")?.get(passage);
            if one_per_entry && !label.is_empty() && results.iter().any(|result| result.locator == locator && result.label == label) { continue; }
            let text = installed.module.strings("vectors.texts")?.get(passage);
            let short: String = text.chars().take(length).collect();
            results.push(MeaningFound { edition: installed.edition.clone(), work: installed.work.clone(), locator, label,
                                        text: if short.len() < text.len() { format!("{short}…") } else { short }, score });
        }
        Ok(results)
    };
    Ok((finish(scripture, false)?, finish(others, true)?))
}

/// As the ingest's `norm` column has them for Latin script: lower case, without accents or modifier letters (so `Corazón` → `corazon`, and `ñ` → `n`).
/// (Provisional for Greek and Hebrew, whose words are only lower-cased.)
fn normalise(words: &[String]) -> Vec<String> { words.iter().map(|word| fold_latin(&word.to_lowercase())).collect() }

const ACCENTED: &str = "ÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝàáâãäåçèéêëìíîïñòóôõöùúûüýÿĀāĂăĄąĆćĈĉĊċČčĎďĒēĔĕĖėĘęĚěĜĝĞğĠġĢģĤĥĨĩĪīĬĭĮįİĴĵĶķĹĺĻļĽľŃńŅņŇňŌōŎŏŐőŔŕŖŗŘřŚśŜŝŞşŠšŢţŤťŨũŪūŬŭŮůŰűŲųŴŵŶŷŸŹźŻżŽž";
const UNACCENTED: &str = "AAAAAACEEEEIIIINOOOOOUUUUYaaaaaaceeeeiiiinooooouuuuyyAaAaAaCcCcCcCcDdEeEeEeEeEeGgGgGgGgHhIiIiIiIiIJjKkLlLlLlNnNnNnOoOoOoRrRrRrSsSsSsSsTtTtUuUuUuUuUuUuWwYyYZzZzZz";

fn fold_latin(word: &str) -> String {
    word.chars().filter(|&character| !matches!(character, '\u{0300}'..='\u{036F}' | '\u{02B0}'..='\u{02FF}')).map(without_accent).collect()
}

/// A Latin letter without its accent, as Unicode's decomposition gives it (e.g., `é` → `e`, `Ñ` → `N`)
pub(crate) fn without_accent(character: char) -> char {
    if (character as u32) < 0xC0 || (character as u32) >= 0x180 { return character; }
    ACCENTED.chars().position(|accented| accented == character).and_then(|ix| UNACCENTED.chars().nth(ix)).unwrap_or(character)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_words_are_folded_as_the_ingest_folds_them() {
        assert_eq!(normalise(&["Corazón".to_string(), "Señor".to_string(), "Yaʸsous".to_string(), "λόγος".to_string()]), ["corazon", "senor", "yasous", "λόγος"]);
    }
}
