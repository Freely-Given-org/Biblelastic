//! `biblelastic`: compile modules and run the first queries from the command line.

mod compile;
mod json;
mod meaning;
mod publish;

use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::Instant;

use biblelastic_engine::format::Module;
use biblelastic_engine::library::{Folder, Library};
use biblelastic_engine::query;

const USAGE: &str = "\
Usage: biblelastic <command> [options]

Commands:
  compile                 Compile the intermediate files into modules
  info [MODULE]           List the installed modules, or the sections of one of them
  terms WORD...           Find the original-language terms that these words translate, e.g., terms love loves loved loving
  find WORD...            Find where all of these words occur together, e.g., find grace truth --within sentence
  marked REASON           Find where the translators marked an addition or change, e.g., marked pronoun_to_name
  about PASSAGE           Find what the commentaries and dictionaries say about a passage, e.g., about JHN 3:16 or about PSA 23
  entry WORD...           Look up a dictionary entry by its title, e.g., entry aaron or entry abel*
  topic WORD...           Find what the Scriptures and the commentators say about a subject, e.g., topic once saved always saved
  meaning WORDS...        Find passages by what they're about, e.g., meaning why do good people suffer (needs a model and vectors: see model and embed)
  model FOLDER            Make a model for meaning-based search from a Hugging Face model's folder (bge-small-en-v1.5 or multilingual-e5-small)
  embed [EDITION...]      Make the vectors of the installed works' passages (all of those in the model's language, if none are named)
  publish FOLDER          Copy the modules that may be passed on, with their catalogue (index.json), to a web server's folder
  request KEY=VALUE...    Send a request as an app would, and show the JSON response, e.g., request command=find 'words=grace truth'

A word can end with * to match any ending, e.g., lov*

Options:
  --intermediate DIR      Where the ingest wrote its files (default: build/intermediate)
  --modules DIR           Where the modules are (default: build/modules)
  --edition ID            The edition to search (default: OET-RV; for about and entry: all of them)
  --within TYPE           For find: sentence, verse, para, section, or chapter (default: sentence)
  --examples N            For terms: how many example verses to show for each term (default: 1)
  --limit N               How many results to show (default: 20)
  --length N              For about and entry: how many characters of each entry to show (default: 300)
  --cache N               How many megabytes of the modules may be kept in memory (default: 16)
  --page-bits N           For compile: store sections as pages of 2^N bytes (default: 14, i.e., 16 kB)
  --no-compress           For compile: don't compress anything
  --repeat N              For meaning: run the query N times, and show how long each took (the first loads the model and vectors)
";

struct Arguments {
    words: Vec<String>,
    intermediate: PathBuf,
    modules: PathBuf,
    edition: String,
    /// The edition, if one was asked for
    only: Option<String>,
    length: usize,
    within: String,
    examples: usize,
    limit: usize,
    page_bits: u8,
    compress: bool,
    cache: usize,
    repeat: usize,
}

fn parse(arguments: &[String]) -> Result<Arguments, String> {
    let mut parsed = Arguments { words: Vec::new(), intermediate: "build/intermediate".into(), modules: "build/modules".into(),
                                 edition: "OET-RV".into(), only: None, length: 300, within: "sentence".into(), examples: 1, limit: 20,
                                 page_bits: compile::Options::default().page_bits, compress: true, cache: biblelastic_engine::format::DEFAULT_CACHE_BYTES >> 20, repeat: 1 };
    let mut iterator = arguments.iter();
    while let Some(argument) = iterator.next() {
        if !argument.starts_with("--") { parsed.words.push(argument.clone()); continue; }
        if argument == "--no-compress" { parsed.compress = false; continue; }
        let value = iterator.next().ok_or_else(|| format!("{argument} needs a value"))?;
        let number = || value.parse::<usize>().map_err(|_| format!("{argument} needs a number, not '{value}'"));
        match argument.as_str() {
            "--intermediate" => parsed.intermediate = value.into(),
            "--modules" => parsed.modules = value.into(),
            "--edition" => { parsed.edition = value.clone(); parsed.only = Some(value.clone()); }
            "--length" => parsed.length = number()?,
            "--within" => parsed.within = value.clone(),
            "--examples" => parsed.examples = number()?,
            "--limit" => parsed.limit = number()?,
            "--page-bits" => parsed.page_bits = number()?.clamp(3, 24) as u8,
            "--cache" => parsed.cache = number()?,
            "--repeat" => parsed.repeat = number()?.max(1),
            _ => return Err(format!("unknown option {argument}")),
        }
    }
    Ok(parsed)
}

fn size(bytes: u64) -> String {
    if bytes >= 1_048_576 { format!("{:.1} MB", bytes as f64 / 1_048_576.0) } else { format!("{:.1} kB", bytes as f64 / 1024.0) }
}

fn folder_size(folder: &Path) -> u64 {
    std::fs::read_dir(folder).into_iter().flatten().flatten().map(|entry| {
        let path = entry.path();
        if path.is_dir() { folder_size(&path) } else { entry.metadata().map_or(0, |metadata| metadata.len()) }
    }).sum()
}

fn run(command: &str, arguments: Arguments) -> Result<(), Box<dyn std::error::Error>> {
    let started = Instant::now();
    match command {
        "compile" => {
            let written = compile::compile(&arguments.intermediate, &arguments.modules, compile::Options { page_bits: arguments.page_bits, compress: arguments.compress })?;
            let total: u64 = written.iter().map(|module| module.bytes).sum();
            for module in &written { println!("{:<28}{:>10}  {} sections", module.name, size(module.bytes), module.sections); }
            println!("{} modules, {} (from {} of intermediate files) in {:.1}s -- output in {}", written.len(), size(total),
                     size(folder_size(&arguments.intermediate)), started.elapsed().as_secs_f64(), arguments.modules.display());
        }
        "info" => match arguments.words.first() {
            Some(name) => {
                let module = Module::open_file(&arguments.modules.join(format!("{name}.blm")))?;
                for entry in module.entries() {
                    println!("{:<34}{:<9}{:>10}{:>12}  {} items{}", entry.name, format!("{:?}", entry.encoding), size(entry.length),
                             if entry.length < entry.raw_length { format!("({:.0}%)", 100.0 * entry.length as f64 / entry.raw_length as f64) } else { String::new() },
                             entry.count, if entry.bits > 0 { format!(" of {} bits", entry.bits) } else { String::new() });
                }
            }
            None => for installed in Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?.modules {
                let description = if installed.kind == "alignment" { format!("{} → {}", installed.from, installed.to) } else { format!("{} {}", installed.edition, installed.layer) };
                println!("{:<28}{:<11}{}", installed.name, installed.kind, description);
            }
        },
        "terms" => {
            if arguments.words.is_empty() { return Err("terms needs at least one word".into()); }
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let result = query::original_terms(&library, &arguments.edition, &arguments.words, arguments.examples)?;
            let occurrences: usize = result.forms.values().sum();
            println!("{} matched {} words: {}", arguments.edition, occurrences, result.forms.iter().map(|(form, count)| format!("{form} ({count})")).collect::<Vec<_>>().join(", "));
            println!("{} of them are linked to original-language words, of {} different terms:\n", result.linked, result.terms.len());
            for term in result.terms.iter().take(arguments.limit) {
                println!("{:>5}× {}  {}  {}  ‘{}’  in {} verses", term.count, term.lemma, term.transliteration, term.strong, term.gloss, term.verses);
                for example in &term.examples { println!("          {}: {}", example.reference, example.text); }
            }
            if result.terms.len() > arguments.limit { println!("   … and {} more (use --limit)", result.terms.len() - arguments.limit); }
            println!("\n{:.1} ms, reading {} from the modules", started.elapsed().as_secs_f64() * 1000.0, size(library.bytes_read()));
        }
        "find" => {
            if arguments.words.is_empty() { return Err("find needs at least one word".into()); }
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let found = query::find_together(&library, &arguments.edition, &arguments.words, &arguments.within, arguments.limit)?;
            println!("{} matched: {}", arguments.edition, found.forms.iter().map(|(form, count)| format!("{form} ({count})")).collect::<Vec<_>>().join(", "));
            println!("{} {} nodes contain all of them:\n", found.total, arguments.within);
            for example in &found.examples { println!("{}: {}", example.reference, example.text); }
            if found.total > found.examples.len() { println!("… and {} more (use --limit)", found.total - found.examples.len()); }
            println!("\n{:.1} ms, reading {} from the modules", started.elapsed().as_secs_f64() * 1000.0, size(library.bytes_read()));
        }
        "marked" => {
            let reason = arguments.words.first().ok_or("marked needs a reason, e.g., pronoun_to_name, name_to_pronoun, reworded, measure, number")?;
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let found = query::find_spans(&library, &arguments.edition, "add", "reason", reason, arguments.limit)?;
            let mut forms: Vec<(&String, &usize)> = found.forms.iter().collect();
            forms.sort_by(|a, b| b.1.cmp(a.1).then(a.0.cmp(b.0)));
            println!("{} has {} places marked ‘{reason}’. Most common: {}\n", arguments.edition, found.total,
                     forms.iter().take(10).map(|(form, count)| format!("{form} ({count})")).collect::<Vec<_>>().join(", "));
            for example in &found.examples { println!("{}: {}", example.reference, example.text); }
            if found.total > found.examples.len() { println!("… and {} more (use --limit)", found.total - found.examples.len()); }
            println!("\n{:.1} ms, reading {} from the modules", started.elapsed().as_secs_f64() * 1000.0, size(library.bytes_read()));
        }
        "about" => {
            let passage = biblelastic_engine::reference::Passage::parse(&arguments.words.join(" "))?;
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let found = query::about(&library, &passage, arguments.only.as_deref(), arguments.limit, arguments.length)?;
            println!("{} entries are about {passage} or cite it:\n", found.total);
            for comment in &found.comments {
                let title = if comment.title.is_empty() { String::new() } else { format!(" ‘{}’", comment.title) };
                println!("{} {}{title} ({} {}): {}\n", comment.edition, comment.locator, comment.kind, comment.passage, comment.text);
            }
            if found.total > found.comments.len() { println!("… and {} more (use --limit)", found.total - found.comments.len()); }
            println!("{:.1} ms, reading {} from the modules", started.elapsed().as_secs_f64() * 1000.0, size(library.bytes_read()));
        }
        "entry" => {
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let found = query::entries(&library, &arguments.words, arguments.only.as_deref(), arguments.limit, arguments.length)?;
            println!("{} entries have a title with: {}\n", found.total, arguments.words.join(" "));
            for entry in &found.entries {
                println!("{} {} ‘{}’ ({}): {}", entry.edition, entry.locator, entry.title, entry.kind, entry.text);
                if !entry.see.is_empty() { println!("    See: {}", entry.see.join("; ")); }
                println!();
            }
            if found.total > found.entries.len() { println!("… and {} more (use --limit)", found.total - found.entries.len()); }
            println!("{:.1} ms, reading {} from the modules", started.elapsed().as_secs_f64() * 1000.0, size(library.bytes_read()));
        }
        "topic" => {
            if arguments.words.is_empty() { return Err("topic needs at least one word".into()); }
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let topic = query::topic(&library, &arguments.edition, &arguments.words, arguments.limit.min(8), arguments.length.min(160))?;
            let show = |heading: &str, entries: &[query::EntryFound], passages: &[query::KeyPassage]| {
                if entries.is_empty() && passages.is_empty() { return; }
                println!("{heading}\n");
                for entry in entries { println!("  {} ‘{}’: {}", entry.edition, entry.title, entry.text); }
                println!();
                for passage in passages { println!("  {} (in {}): {}", passage.passage, passage.sources.join("; "), passage.text); }
                println!();
            };
            if !topic.see.is_empty() { println!("The thesaurus points to: {}\n", topic.see.join("; ")); }
            show("ENTRIES ON THE SUBJECT, AND THE PASSAGES THEY REFER TO MOST", &topic.entries, &topic.passages);
            if !topic.contrast.is_empty() { show(&format!("THE OTHER SIDE OF THE QUESTION ({})", topic.contrast.join("; ")), &topic.other_entries, &topic.other_passages); }
            if !topic.scripture.is_empty() { println!("THE WORDS TOGETHER IN A SENTENCE OF THE {}\n", arguments.edition); }
            for example in &topic.scripture { println!("  {}: {}", example.reference, example.text); }
            if !topic.mentions.is_empty() { println!("\nTHE WORDS TOGETHER IN A PARAGRAPH OF A COMMENTARY OR DICTIONARY\n"); }
            for example in &topic.mentions { println!("  {}: {}", example.reference, example.text); }
            println!("\n{:.1} ms, reading {} from the modules", started.elapsed().as_secs_f64() * 1000.0, size(library.bytes_read()));
        }
        "meaning" => {
            if arguments.words.is_empty() { return Err("meaning needs a query".into()); }
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            // --edition names a work (or, as `spa` or `eng`, a language)
            let (editions, language): (Vec<String>, Option<&str>) = match arguments.only.as_deref() {
                Some(language @ ("eng" | "spa")) => (Vec::new(), Some(language)), Some(edition) => (vec![edition.to_string()], None), None => (Vec::new(), None) };
            let mut times = Vec::new();
            let mut found = None;
            for _ in 0..arguments.repeat {
                let started = Instant::now();
                found = Some(query::meaning(&library, &arguments.words.join(" "), &editions, language, arguments.limit, arguments.length)?);
                times.push(format!("{:.0} ms", started.elapsed().as_secs_f64() * 1000.0));
            }
            let (scripture, others) = found.expect("at least once");
            if arguments.repeat > 1 { println!("Each time: {}\n", times.join(", ")); }
            for found in scripture.iter().chain(&others) {
                println!("{:.3}  {} {}{}: {}\n", found.score, found.edition, found.locator, if found.label.is_empty() { String::new() } else { format!(" ‘{}’", found.label) }, found.text);
            }
            println!("({:.0} ms)", started.elapsed().as_secs_f64() * 1000.0);
        }
        "vector" => { // For checking a model against another implementation: a text's vector (--edition names the model)
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            let model = library.model(arguments.only.as_deref())?; // --edition names the model
            let text = arguments.words.join(" ");
            let started = Instant::now();
            let vector = model.embed(&text); // (No prefix: give it with the text, e.g., query: …)
            eprintln!("({:.1} ms)", started.elapsed().as_secs_f64() * 1000.0);
            println!("[{}]", vector.iter().map(|value| format!("{value:.6}")).collect::<Vec<_>>().join(","));
        }
        "model" => {
            let folder = arguments.words.first().ok_or("model needs the folder of a Hugging Face model")?;
            meaning::convert_model(Path::new(folder), &arguments.intermediate, &arguments.modules, compile::Options { page_bits: arguments.page_bits, compress: arguments.compress })?;
        }
        "publish" => { // Copy the modules that may be passed on to a web server's folder, with their catalogue
            let to = arguments.words.first().ok_or("publish needs the folder to publish to, e.g., /srv/www/Freely-Given.org/Software/Biblelastic/modules")?;
            publish::publish(&arguments.modules, Path::new(to))?;
        }
        "embed" => meaning::embed(&arguments.modules, &arguments.words, None, compile::Options { page_bits: arguments.page_bits, compress: arguments.compress })?,
        "request" => {
            let library = Library::open_with(&Folder(arguments.modules.clone()), arguments.cache << 20)?;
            println!("{}", biblelastic_engine::api::respond(&library, &arguments.words.join("\n")));
        }
        _ => return Err(format!("unknown command '{command}'\n\n{USAGE}").into()),
    }
    Ok(())
}

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let Some(command) = arguments.first().filter(|command| !matches!(command.as_str(), "help" | "--help" | "-h")) else {
        print!("{USAGE}");
        return ExitCode::SUCCESS;
    };
    match parse(&arguments[1..]).map_err(Into::into).and_then(|parsed| run(command, parsed)) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => { eprintln!("biblelastic: {error}"); ExitCode::FAILURE }
    }
}
