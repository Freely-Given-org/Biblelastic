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
//! Commands: `info`, `terms`, `find` and `marked`. The response is always a JSON object with `"ok"`.

use std::collections::{BTreeMap, HashMap};

use crate::format::Result;
use crate::library::Library;
use crate::query::{self, Example};

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
                "{{\"name\":{},\"kind\":{},\"edition\":{},\"layer\":{},\"from\":{},\"to\":{},\"sections\":{}}}", quote(&installed.name), quote(&installed.kind),
                quote(&installed.edition), quote(&installed.layer), quote(&installed.from), quote(&installed.to), installed.module.entries().len())).collect();
            Ok(format!("\"modules\":[{}]", modules.join(",")))
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
        other => Err(format!("unknown command '{other}'").into()),
    }
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
