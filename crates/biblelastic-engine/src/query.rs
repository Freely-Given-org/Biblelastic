//! The first queries. These are written directly against the modules for now;
//! the general query tree described in the README will replace them.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use crate::format::Result;
use crate::library::{find_terms, Library, Nodes, Text};

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
            let mut verse_slots: Vec<u32> = occurrences.iter().map(|&(_, slot)| text.verses.containing(slot).map_or(slot, |verse| text.verses.starts.get(verse))).collect();
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
                examples: verse_slots.iter().take(example_count).map(|&slot| example(&text, &text.verses, slot)).collect(),
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
            let verse = text.verses.containing(range.start).map_or(range.clone(), |verse| text.verses.range(verse));
            let (before, after) = (text.render_exact(verse.start..range.start), text.render(range.end..verse.end.max(range.end)));
            examples.push(Example { reference: text.reference(range.start), text: format!("{before}{opening}[{words}]{closing}{after}").trim_end().to_string() });
        }
    }
    Ok(Found { total, forms, examples })
}

fn example(text: &Text, verses: &Nodes, slot: u32) -> Example {
    let paragraph = || text.paragraphs.containing(slot).map_or(slot..slot + 1, |paragraph| text.paragraphs.range(paragraph)); // e.g., a psalm title
    let range = verses.containing(slot).map_or_else(paragraph, |verse| verses.range(verse));
    Example { reference: text.reference(slot), text: text.render(range) }
}

/// `c:d:H0776` → `H0776` (drops the prefixes that mark attached Hebrew particles)
fn base_strong(strong: &str) -> String { strong.rsplit(':').next().unwrap_or(strong).to_string() }

/// Provisional: matches the ingest's `norm` column only for unaccented words
fn normalise(words: &[String]) -> Vec<String> { words.iter().map(|word| word.to_lowercase()).collect() }
