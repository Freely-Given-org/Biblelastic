//! Scripture passages: `JHN 3:16`, `JHN 3:16-18`, `JHN 3:16-4:2`, `JHN 3`, `JHN 3-4`, or just `JHN`.
//!
//! The book is a BibleOrgSys code (GEN, SA1, MRK, etc.). Chapter and verse numbers are those of whichever work uses them:
//! nothing here maps between versification schemes.

use std::fmt;

use crate::format::Result;

/// The USFM book codes that aren't BibleOrgSys ones, and the BibleOrgSys code for each (e.g., 1CO → CO1, 4MA → MA4, DAG → DNG): from BibleOrgSys's
/// BibleBooksCodes table, as `pipeline/biblelastic_ingest/book_codes.py` writes it (which writes this too)
pub const USFM_TO_BOS: &[(&str, &str)] = &[
    ("1CH", "CH1"), ("1CL", "CL1"), ("1CO", "CO1"), ("1ES", "GES"), ("1JN", "JN1"), ("1KI", "KI1"), ("1MA", "MA1"), ("1MQ", "MQ1"), ("1PE", "PE1"), ("1SA", "SA1"),
    ("1TH", "TH1"), ("1TI", "TI1"), ("2BA", "BA2"), ("2CH", "CH2"), ("2CL", "CL2"), ("2CO", "CO2"), ("2ES", "LES"), ("2JN", "JN2"), ("2KI", "KI2"), ("2MA", "MA2"),
    ("2MQ", "MQ2"), ("2PE", "PE2"), ("2SA", "SA2"), ("2TH", "TH2"), ("2TI", "TI2"), ("3CO", "CO3"), ("3JN", "JN3"), ("3MA", "MA3"), ("3MQ", "MQ3"), ("4BA", "BA4"),
    ("4MA", "MA4"), ("5EZ", "EZ5"), ("6EZ", "EZ6"), ("ADE", "ESA"), ("DAG", "DNG"), ("EZK", "EZE"), ("GLO", "GLS"), ("JAS", "JAM"), ("JDA", "JGA"), ("JDB", "JGB"),
    ("JON", "JNA"), ("JUD", "JDE"), ("NAM", "NAH"), ("NDX", "IXN"), ("ODA", "ODE"), ("S3Y", "PAZ"), ("TDX", "IXT"),
];

/// The BibleOrgSys code for a book code, whichever kind it is (e.g., 1CO or CO1 → CO1, 4MA → MA4); anything else (e.g., `Intros`) as it is
pub fn bos_book(code: &str) -> String {
    USFM_TO_BOS.iter().find(|(usfm, _)| *usfm == code).map_or_else(|| code.to_string(), |(_, bos)| bos.to_string())
}

/// The largest chapter or verse number that can be packed, also used for ‘to the end’
pub const LAST: u32 = 1023;

/// A range of verses in one book, with both ends included
#[derive(Clone, Debug, PartialEq)]
pub struct Passage {
    pub book: String,
    /// (chapter, verse)
    pub from: (u32, u32),
    pub to: (u32, u32),
}

/// One position as a number, so that positions sort in order: `book` is the book's number in some list of books
pub fn pack(book: u32, (chapter, verse): (u32, u32)) -> u32 { book << 20 | chapter.min(LAST) << 10 | verse.min(LAST) }

pub fn unpack(packed: u32) -> (u32, (u32, u32)) { (packed >> 20, (packed >> 10 & LAST, packed & LAST)) }

impl Passage {
    pub fn parse(text: &str) -> Result<Passage> {
        let bad = || format!("'{text}' isn't a passage like JHN 3:16 or JHN 3:16-18 or JHN 3");
        let mut parts = text.split_whitespace();
        let book = parts.next().ok_or_else(bad)?;
        if book.len() != 3 || !book.chars().all(|character| character.is_ascii_alphanumeric()) { return Err(bad().into()); }
        let book = bos_book(&book.to_ascii_uppercase()); // (e.g., 1co 13:4 → CO1 13:4)
        let range: String = parts.collect();
        if range.is_empty() { return Ok(Passage { book, from: (0, 0), to: (LAST, LAST) }); }
        let number = |field: &str| field.parse::<u32>().ok().filter(|&value| value < LAST).ok_or_else(bad);
        let (first, last) = match range.split_once(['-', '–']) { Some((first, last)) => (first, Some(last)), None => (range.as_str(), None) };
        let (from, whole_chapters) = match first.split_once(':') {
            Some((chapter, verse)) => ((number(chapter)?, number(verse)?), false),
            None => ((number(first)?, 0), true),
        };
        let to = match last.map(|last| (last, last.split_once(':'))) {
            None if whole_chapters => (from.0, LAST),
            None => from,
            Some((_, Some((chapter, verse)))) => (number(chapter)?, number(verse)?),
            Some((last, None)) if whole_chapters => (number(last)?, LAST),
            Some((last, None)) => (from.0, number(last)?),
        };
        if to < from { return Err(bad().into()); }
        Ok(Passage { book, from, to })
    }
}

impl fmt::Display for Passage {
    fn fmt(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
        let Passage { book, from, to } = self;
        let end = |(chapter, verse): (u32, u32)| if chapter >= 999 { "end".to_string() } else { format!("{chapter}:{verse}") };
        match (from, to) {
            ((0, _), (LAST, _)) => write!(formatter, "{book}"),
            ((first, 0), (last, LAST)) if first == last => write!(formatter, "{book} {first}"),
            ((first, 0), (last, LAST)) => write!(formatter, "{book} {first}-{last}"),
            _ if from == to => write!(formatter, "{book} {}:{}", from.0, from.1),
            _ if from.0 == to.0 => write!(formatter, "{book} {}:{}-{}", from.0, from.1, to.1),
            _ => write!(formatter, "{book} {}:{}-{}", from.0, from.1, end(*to)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parsing_and_showing() {
        for (text, from, to, shown) in [
            ("JHN 3:16", (3, 16), (3, 16), "JHN 3:16"), ("jhn 3:16-18", (3, 16), (3, 18), "JHN 3:16-18"), ("JHN 3:16-4:2", (3, 16), (4, 2), "JHN 3:16-4:2"),
            ("GEN 1:22-1:25", (1, 22), (1, 25), "GEN 1:22-25"), ("JHN 3", (3, 0), (3, LAST), "JHN 3"), ("JHN 3–4", (3, 0), (4, LAST), "JHN 3-4"),
            ("JHN", (0, 0), (LAST, LAST), "JHN"), ("GEN 50:1-999:999", (50, 1), (999, 999), "GEN 50:1-end"),
            ("1CO 13:4", (13, 4), (13, 4), "CO1 13:4"), ("4ma 1", (1, 0), (1, LAST), "MA4 1"), ("DAG 3:24", (3, 24), (3, 24), "DNG 3:24"),
        ] {
            let passage = Passage::parse(text).unwrap();
            assert_eq!((passage.book.len(), passage.from, passage.to, passage.to_string().as_str()), (3, from, to, shown), "{text}");
        }
        for text in ["", "John 3:16", "JHN 3:x", "JHN 3:16-2", "JHN 4-3"] { assert!(Passage::parse(text).is_err(), "{text}"); }
        assert!(pack(3, (2, 0)) < pack(3, (2, 1)) && pack(3, (2, LAST)) < pack(3, (3, 0)) && pack(3, (LAST, LAST)) < pack(4, (0, 0)));
        assert_eq!(unpack(pack(70, (119, 176))), (70, (119, 176)));
    }
}
