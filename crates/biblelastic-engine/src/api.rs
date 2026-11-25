//! One entry point for every host (browser worker, Flutter, command line): a text request in, JSON out.
//!
//! A request is lines of `key=value`, e.g.
//!
//! ```text
//! command=terms
//! edition=OET-RV
//! words=love loves loved loving
//! ```
//!
//! Commands: `info`, `contents`, `read`, `word`, `lemma`, `article`, `toc`, `domain`, `terms`, `find`, `marked`, `about`, `entry` and `topic`. The response is always a JSON object with `"ok"`.

use std::collections::{BTreeMap, HashMap};

use crate::format::Result;
use crate::library::Library;
use crate::query::{self, EntryFound, Example, KeyPassage, Paragraph, Piece, Wanted};
use crate::reference::Passage;

pub fn respond(library: &Library, request: &str) -> String {
    match answer(library, request) {
        Ok(fields) => format!("{{\"ok\":true,{fields}}}"),
        Err(error) => format!("{{\"ok\":false,\"error\":{}}}", quote(&error.to_string())),
    }
}

fn answer(library: &Library, request: &str) -> Result<String> {
    let fields: HashMap<&str, &str> = request.lines().filter_map(|line| line.split_once('=')).map(|(key, value)| (key.trim(), value.trim())).collect();
    let text = |key: &str, default: &'static str| fields.get(key).copied().filter(|value| !value.is_empty()).unwrap_or(default);
    let number = |key: &str, default: usize| -> Result<usize> {
        match fields.get(key) { Some(value) => value.parse().map_err(|_| format!("{key} needs a number, not '{value}'").into()), None => Ok(default) }
    };
    let words: Vec<String> = text("words", "").split_whitespace().map(str::to_string).collect();
    let (edition, limit) = (text("edition", "OET-RV"), number("limit", 20)?);
    match text("command", "") {
        "info" => {
            let modules: Vec<String> = library.modules.iter().map(|installed| format!(
                "{{\"name\":{},\"kind\":{},\"work\":{},\"edition\":{},\"layer\":{},\"title\":{},\"language\":{},\"disclaimer\":{},\"from\":{},\"to\":{},\"sections\":{}}}", quote(&installed.name), quote(&installed.kind),
                quote(&installed.work), quote(&installed.edition), quote(&installed.layer), quote(&installed.title), quote(&installed.language), quote(&installed.disclaimer), quote(&installed.from), quote(&installed.to),
                installed.module.entries().len())).collect();
            Ok(format!("\"modules\":[{}]", modules.join(",")))
        }
        "contents" => { // The documents of an edition, and how many chapters each has
            let documents: Vec<String> = query::contents(library, edition)?.iter().map(|document| format!(
                "{{\"name\":{},\"chapters\":{},\"introduction\":{},\"sections\":{}}}", quote(&document.name), document.chapters, document.introduction, document.sections)).collect();
            Ok(format!("\"edition\":{},\"documents\":[{}]", quote(edition), documents.join(",")))
        }
        "read" => { // A passage laid out for reading: each paragraph is a list of chapter numbers {"c"}, verse numbers {"v"} (with the verse's full name {"r"}),
            // and pieces of text {"t"} with any character styles {"s"}
            // With detail=words, each piece of text is one word, with its number {"w"} for asking about it (see "word")
            let given = match text("passage", "") { "" => text("words", ""), given => given };
            let separate_words = text("detail", "") == "words";
            if text("unit", "") == "section" || fields.contains_key("section") { // One section: the one a passage starts in, or by its number in a document
                let passage = if fields.contains_key("section") { None } else { Some(Passage::parse(given)?) };
                let wanted = match &passage { Some(passage) => Wanted::At(passage), None => Wanted::Number(text("document", ""), number("section", 0)?) };
                let reading = query::read_section(library, edition, wanted, separate_words)?;
                let neighbour = |neighbour: &Option<(String, usize)>| neighbour.as_ref().map_or("null".to_string(), |(document, number)| format!("{{\"document\":{},\"section\":{number}}}", quote(document)));
                return Ok(format!("\"edition\":{},\"document\":{},\"section\":{},\"title\":{},\"passage\":{},\"previous\":{},\"next\":{},\"paragraphs\":{}", quote(edition), quote(&reading.document),
                                  reading.number, quote(&reading.title), quote(&reading.passage), neighbour(&reading.previous), neighbour(&reading.next), paragraphs(&reading.paragraphs))
                    + &format!(",\"noted\":[{}]", reading.noted.iter().map(|verse| quote(verse)).collect::<Vec<_>>().join(",")));
            }
            let reading = query::read(library, edition, &Passage::parse(given)?, separate_words)?;
            Ok(format!("\"edition\":{},\"passage\":{},\"paragraphs\":{}", quote(edition), quote(&reading.passage), paragraphs(&reading.paragraphs)))
        }
        "word" => { // What a word of a translation translates: `slot` is the word's number, from "read" with detail=words
            let info = query::word(library, edition, fields.get("slot").and_then(|slot| slot.parse().ok()).ok_or("word needs a slot number")?)?;
            let strings = |values: &[String]| format!("[{}]", values.iter().map(|value| quote(value)).collect::<Vec<_>>().join(","));
            let originals: Vec<String> = info.originals.iter().map(|original| format!(
                "{{\"edition\":{},\"reference\":{},\"text\":{},\"transliteration\":{},\"lemma\":{},\"lemmaTransliteration\":{},\"strong\":{},\"morphology\":{},\"gloss\":{},\"occurrences\":{},\"counted\":{},\"renderings\":{},\"meaning\":{},\"articles\":[{}]}}",
                quote(&original.edition), quote(&original.reference), quote(&original.text), quote(&original.transliteration), quote(&original.lemma), quote(&original.lemma_transliteration),
                quote(&original.strong), quote(&original.morphology), quote(&original.gloss), original.occurrences, original.counted,
                format!("[{}]", original.renderings.iter().map(|(words, count)| format!("[{},{count}]", quote(words))).collect::<Vec<_>>().join(",")),
                original.meaning.as_ref().map_or("null".to_string(), |meaning| format!("{{\"gloss\":{},\"definition\":{},\"note\":{},\"code\":{},\"domains\":{}}}",
                    quote(&meaning.gloss), quote(&meaning.definition), quote(&meaning.note), quote(&meaning.code), strings(&meaning.domains))),
                original.articles.iter().map(|(edition, locator, title)| format!("{{\"edition\":{},\"locator\":{},\"title\":{}}}", quote(edition), quote(locator), quote(title))).collect::<Vec<_>>().join(","))).collect();
            let linked: Vec<String> = info.linked.iter().map(|(edition, slots)| format!("{{\"edition\":{},\"slots\":[{}]}}", quote(edition),
                slots.iter().map(u32::to_string).collect::<Vec<_>>().join(","))).collect();
            Ok(format!("\"edition\":{},\"text\":{},\"reference\":{},\"originals\":[{}],\"linked\":[{}]", quote(edition), quote(&info.text), quote(&info.reference),
                       originals.join(","), linked.join(",")))
        }
        "article" => { // One whole entry of a commentary, dictionary, etc., e.g., locator=Fauna 2.10 (in any installed work, unless an edition is given)
            let found = query::article(library, fields.get("edition").copied().filter(|edition| !edition.is_empty()), text("locator", ""))?;
            let paragraphs: Vec<String> = found.paragraphs.iter().map(|(style, kind, words)| format!("{{\"style\":{},\"kind\":{},\"text\":{}}}", quote(style), quote(kind), quote(words))).collect();
            let see: Vec<String> = found.see.iter().map(|(locator, title)| format!("{{\"locator\":{},\"title\":{}}}", quote(locator), quote(title))).collect();
            let neighbour = |neighbour: &Option<String>| neighbour.as_ref().map_or("null".to_string(), |locator| quote(locator));
            Ok(format!("\"edition\":{},\"work\":{},\"locator\":{},\"title\":{},\"paragraphs\":[{}],\"see\":[{}],\"previous\":{},\"next\":{}", quote(&found.edition), quote(&found.work),
                       quote(&found.locator), quote(&found.title), paragraphs.join(","), see.join(","), neighbour(&found.previous), neighbour(&found.next)))
        }
        "toc" => { // The entries of a commentary, dictionary, book, etc., in order (e.g., a book's chapters)
            let entries = query::contents_of(library, text("edition", ""))?;
            let entries: Vec<String> = entries.iter().map(|(locator, title, kind)| format!("{{\"locator\":{},\"title\":{},\"type\":{}}}", quote(locator), quote(title), quote(kind))).collect();
            Ok(format!("\"edition\":{},\"entries\":[{}]", quote(text("edition", "")), entries.join(",")))
        }
        "domain" => { // The words of an original-language edition that have a meaning in a semantic domain
            let (total, words) = query::domain(library, text("original", ""), text("domain", ""), limit)?;
            let words: Vec<String> = words.iter().map(|word| format!("{{\"lemma\":{},\"transliteration\":{},\"gloss\":{},\"count\":{}}}",
                quote(&word.lemma), quote(&word.transliteration), quote(&word.gloss), word.count)).collect();
            Ok(format!("\"domain\":{},\"total\":{},\"words\":[{}]", quote(text("domain", "")), total, words.join(",")))
        }
        "lemma" => { // The verses of a translation where an original-language lemma is translated
            let found = query::lemma_verses(library, edition, text("original", ""), text("lemma", ""), limit)?;
            Ok(format!("\"forms\":{},\"total\":{},\"examples\":{}", counts(&found.forms, usize::MAX), found.total, examples(&found.examples)))
        }
        "terms" => {
            if words.is_empty() { return Err("terms needs at least one word".into()); }
            let result = query::original_terms(library, edition, &words, number("examples", 1)?)?;
            let terms: Vec<String> = result.terms.iter().take(limit).map(|term| format!(
                "{{\"edition\":{},\"lemma\":{},\"transliteration\":{},\"strong\":{},\"gloss\":{},\"count\":{},\"verses\":{},\"examples\":{}}}", quote(&term.edition),
                quote(&term.lemma), quote(&term.transliteration), quote(&term.strong), quote(&term.gloss), term.count, term.verses, examples(&term.examples))).collect();
            Ok(format!("\"forms\":{},\"linked\":{},\"total\":{},\"terms\":[{}]", counts(&result.forms, usize::MAX), result.linked, result.terms.len(), terms.join(",")))
        }
        "find" => {
            if words.is_empty() { return Err("find needs at least one word".into()); }
            let found = query::find_together(library, edition, &words, text("within", "sentence"), limit)?;
            Ok(format!("\"forms\":{},\"total\":{},\"examples\":{}", counts(&found.forms, usize::MAX), found.total, examples(&found.examples)))
        }
        "marked" => {
            let reason = words.first().ok_or("marked needs a reason, e.g., pronoun_to_name")?;
            let found = query::find_spans(library, edition, "add", "reason", reason, limit)?;
            Ok(format!("\"forms\":{},\"total\":{},\"examples\":{}", counts(&found.forms, 10), found.total, examples(&found.examples)))
        }
        "about" => { // What the installed commentaries, dictionaries, etc. say about a passage (in all of them, unless an edition is given)
            let passage = Passage::parse(match text("passage", "") { "" => text("words", ""), given => given })?;
            let found = query::about(library, &passage, fields.get("edition").copied().filter(|edition| !edition.is_empty()), limit, number("length", 300)?)?;
            let comments: Vec<String> = found.comments.iter().map(|comment| format!(
                "{{\"edition\":{},\"work\":{},\"locator\":{},\"title\":{},\"kind\":{},\"passage\":{},\"text\":{}}}", quote(&comment.edition), quote(&comment.work),
                quote(&comment.locator), quote(&comment.title), quote(comment.kind), quote(&comment.passage), quote(&comment.text))).collect();
            Ok(format!("\"passage\":{},\"total\":{},\"comments\":[{}]", quote(&passage.to_string()), found.total, comments.join(",")))
        }
        "entry" => { // Look entries up by their titles
            let found = query::entries(library, &words, fields.get("edition").copied().filter(|edition| !edition.is_empty()), limit, number("length", 300)?)?;
            let entries: Vec<String> = found.entries.iter().map(|entry| format!(
                "{{\"edition\":{},\"work\":{},\"locator\":{},\"title\":{},\"type\":{},\"text\":{},\"see\":[{}]}}", quote(&entry.edition), quote(&entry.work),
                quote(&entry.locator), quote(&entry.title), quote(&entry.kind), quote(&entry.text), entry.see.iter().map(|title| quote(title)).collect::<Vec<_>>().join(","))).collect();
            Ok(format!("\"total\":{},\"entries\":[{}]", found.total, entries.join(",")))
        }
        "topic" => { // What the Scriptures and the commentators say about a subject
            if words.is_empty() { return Err("topic needs at least one word".into()); }
            let topic = query::topic(library, edition, &words, limit, number("length", 300)?)?;
            let titles = |titles: &[String]| titles.iter().map(|title| quote(title)).collect::<Vec<_>>().join(",");
            let entries = |entries: &[EntryFound]| entries.iter().map(|entry| format!(
                "{{\"edition\":{},\"work\":{},\"locator\":{},\"title\":{},\"type\":{},\"text\":{}}}", quote(&entry.edition), quote(&entry.work), quote(&entry.locator),
                quote(&entry.title), quote(&entry.kind), quote(&entry.text))).collect::<Vec<_>>().join(",");
            let passages = |passages: &[KeyPassage]| passages.iter().map(|passage| format!(
                "{{\"passage\":{},\"sources\":[{}],\"text\":{}}}", quote(&passage.passage), titles(&passage.sources), quote(&passage.text))).collect::<Vec<_>>().join(",");
            Ok(format!("\"see\":[{}],\"contrast\":[{}],\"entries\":[{}],\"passages\":[{}],\"otherEntries\":[{}],\"otherPassages\":[{}],\"scripture\":{},\"mentions\":{}",
                       titles(&topic.see), titles(&topic.contrast), entries(&topic.entries), passages(&topic.passages), entries(&topic.other_entries), passages(&topic.other_passages),
                       examples(&topic.scripture), examples(&topic.mentions)))
        }
        "meaning" => { // Passages that are about what the query is about, found by meaning-based search (`words` is the query, as it was typed; optional `editions` and `language`)
            let query = text("words", "");
            if query.is_empty() { return Err("meaning needs a query (words=…)".into()); }
            let editions: Vec<String> = text("editions", "").split(',').map(str::trim).filter(|edition| !edition.is_empty()).map(str::to_string).collect();
            let language = Some(text("language", "")).filter(|language| !language.is_empty()); // e.g., `spa`: only the works in that language
            let (scripture, others) = query::meaning(library, query, &editions, language, limit, number("length", 300)?)?;
            let found = |found: &[query::MeaningFound]| found.iter().map(|found| format!(
                "{{\"edition\":{},\"work\":{},\"locator\":{},\"label\":{},\"text\":{},\"score\":{:.4}}}", quote(&found.edition), quote(&found.work), quote(&found.locator),
                quote(&found.label), quote(&found.text), found.score)).collect::<Vec<_>>().join(",");
            Ok(format!("\"scripture\":[{}],\"others\":[{}]", found(&scripture), found(&others)))
        }
        other => Err(format!("unknown command '{other}'").into()),
    }
}

fn paragraphs(paragraphs: &[Paragraph]) -> String {
    let paragraphs: Vec<String> = paragraphs.iter().map(|paragraph| {
        let pieces: Vec<String> = paragraph.pieces.iter().map(|piece| match piece {
            Piece::Chapter(number) => format!("{{\"c\":{}}}", quote(number)),
            Piece::Verse(name) => format!("{{\"v\":{},\"r\":{}}}", quote(name.split_once(':').map_or(name.as_str(), |(_, number)| number)), quote(name)),
            Piece::Text(words, styles, slot) => format!("{{\"t\":{}{}{}}}", quote(words),
                if styles.is_empty() { String::new() } else { format!(",\"s\":[{}]", styles.iter().map(|style| quote(style)).collect::<Vec<_>>().join(",")) },
                slot.map_or(String::new(), |slot| format!(",\"w\":{slot}"))),
        }).collect();
        format!("{{\"style\":{},\"kind\":{},\"pieces\":[{}]}}", quote(&paragraph.style), quote(&paragraph.kind), pieces.join(","))
    }).collect();
    format!("[{}]", paragraphs.join(","))
}

/// A JSON string
pub fn quote(text: &str) -> String {
    let mut quoted = String::with_capacity(text.len() + 2);
    quoted.push('"');
    for character in text.chars() {
        match character {
            '"' => quoted.push_str("\\\""),
            '\\' => quoted.push_str("\\\\"),
            '\n' => quoted.push_str("\\n"),
            '\t' => quoted.push_str("\\t"),
            control if (control as u32) < 0x20 => quoted.push_str(&format!("\\u{:04x}", control as u32)),
            other => quoted.push(other),
        }
    }
    quoted.push('"');
    quoted
}

/// `[["form", count], …]` with the most common first
fn counts(forms: &BTreeMap<String, usize>, limit: usize) -> String {
    let mut sorted: Vec<(&String, &usize)> = forms.iter().collect();
    sorted.sort_by(|a, b| b.1.cmp(a.1).then(a.0.cmp(b.0)));
    format!("[{}]", sorted.iter().take(limit).map(|(form, count)| format!("[{},{count}]", quote(form))).collect::<Vec<_>>().join(","))
}

fn examples(examples: &[Example]) -> String {
    format!("[{}]", examples.iter().map(|example| format!("{{\"reference\":{},\"text\":{}}}", quote(&example.reference), quote(&example.text))).collect::<Vec<_>>().join(","))
}

#[cfg(test)]
mod tests {
    #[test]
    fn quoting() {
        assert_eq!(super::quote("“a\"b\\c\n\u{1}”"), "\"“a\\\"b\\\\c\\n\\u0001”\"");
    }
}
