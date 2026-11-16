//! The Biblelastic module container format (v0) -- see docs/ModuleFormat.md
//!
//! A module is one file: a fixed header, then named sections, then a table of contents.
//! Everything is read with explicit (offset, length) requests so that the same code works
//! on a local file, on browser storage, or on bytes in memory.

use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

pub const MAGIC: &[u8; 8] = b"BLMODULE";
pub const FORMAT_VERSION: u16 = 0;
const HEADER_LENGTH: usize = 32;
const PADDING: usize = 8; // After packed data, so a value can always be read as part of eight bytes

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Encoding {
    /// Uninterpreted bytes (e.g., UTF-8 text)
    Raw = 0,
    /// `count` unsigned integers of `bits` bits each, packed from the least-significant bit
    Packed = 1,
    /// `count` strings: (count + 1) little-endian u32 offsets, then the UTF-8 bytes
    Strings = 2,
    /// Concatenated lists of ascending integers, each list stored as LEB128 differences
    Varints = 3,
}

#[derive(Clone, Debug)]
pub struct Entry {
    pub name: String,
    pub encoding: Encoding,
    pub bits: u8,
    pub offset: u64,
    pub length: u64,
    pub count: u64,
    pub crc: u32,
}

/// CRC-32 (IEEE), bit-at-a-time with a lazily-built table
pub fn crc32(data: &[u8]) -> u32 {
    thread_local! {
        static TABLE: [u32; 256] = {
            let mut table = [0u32; 256];
            for (n, slot) in table.iter_mut().enumerate() {
                let mut value = n as u32;
                for _ in 0..8 { value = if value & 1 == 1 { 0xEDB8_8320 ^ (value >> 1) } else { value >> 1 }; }
                *slot = value;
            }
            table
        };
    }
    TABLE.with(|table| !data.iter().fold(!0u32, |crc, &byte| table[((crc ^ byte as u32) & 0xFF) as usize] ^ (crc >> 8)))
}

fn bits_needed(max: u32) -> u8 { (32 - max.leading_zeros()).max(1) as u8 }

// ---------------------------------------------------------------------------------------------
// Writing

#[derive(Default)]
pub struct ModuleWriter {
    buffer: Vec<u8>,
    entries: Vec<Entry>,
}

impl ModuleWriter {
    pub fn new() -> Self { ModuleWriter { buffer: vec![0; HEADER_LENGTH], entries: Vec::new() } }

    fn add(&mut self, name: &str, encoding: Encoding, bits: u8, count: usize, data: &[u8]) {
        assert!(!self.entries.iter().any(|entry| entry.name == name), "duplicate section {name}");
        self.entries.push(Entry { name: name.to_string(), encoding, bits, offset: self.buffer.len() as u64,
                                  length: data.len() as u64, count: count as u64, crc: crc32(data) });
        self.buffer.extend_from_slice(data);
    }

    pub fn raw(&mut self, name: &str, data: &[u8]) { self.add(name, Encoding::Raw, 0, data.len(), data); }

    pub fn packed(&mut self, name: &str, values: &[u32]) {
        let bits = bits_needed(values.iter().copied().max().unwrap_or(0));
        let mut data = vec![0u8; (values.len() * bits as usize).div_ceil(8) + PADDING];
        for (n, &value) in values.iter().enumerate() {
            let bit = n * bits as usize;
            let (byte, shift) = (bit / 8, bit % 8);
            let mut window = u64::from_le_bytes(data[byte..byte + 8].try_into().unwrap());
            window |= (value as u64) << shift;
            data[byte..byte + 8].copy_from_slice(&window.to_le_bytes());
        }
        self.add(name, Encoding::Packed, bits, values.len(), &data);
    }

    pub fn strings<S: AsRef<str>>(&mut self, name: &str, strings: &[S]) {
        let mut data = Vec::with_capacity(4 * (strings.len() + 1));
        let mut offset = 0u32;
        for string in strings {
            data.extend_from_slice(&offset.to_le_bytes());
            offset += string.as_ref().len() as u32;
        }
        data.extend_from_slice(&offset.to_le_bytes());
        for string in strings { data.extend_from_slice(string.as_ref().as_bytes()); }
        self.add(name, Encoding::Strings, 0, strings.len(), &data);
    }

    /// Writes `<prefix>.offsets` (where each list starts, plus the total length) and `<prefix>.data`.
    /// Each list must be in ascending order.
    pub fn postings(&mut self, prefix: &str, lists: &[Vec<u32>]) {
        let mut data = Vec::new();
        let mut offsets = Vec::with_capacity(lists.len() + 1);
        for list in lists {
            offsets.push(data.len() as u32);
            let mut previous = 0u32;
            for &value in list {
                let mut difference = value - previous;
                previous = value;
                while difference >= 0x80 { data.push((difference as u8 & 0x7F) | 0x80); difference >>= 7; }
                data.push(difference as u8);
            }
        }
        offsets.push(data.len() as u32);
        self.packed(&format!("{prefix}.offsets"), &offsets);
        self.add(&format!("{prefix}.data"), Encoding::Varints, 0, lists.iter().map(Vec::len).sum(), &data);
    }

    pub fn finish(mut self) -> Vec<u8> {
        let mut toc = Vec::new();
        toc.extend_from_slice(&(self.entries.len() as u32).to_le_bytes());
        for entry in &self.entries {
            toc.extend_from_slice(&(entry.name.len() as u16).to_le_bytes());
            toc.extend_from_slice(entry.name.as_bytes());
            toc.extend_from_slice(&[entry.encoding as u8, entry.bits, 0, 0]);
            toc.extend_from_slice(&entry.offset.to_le_bytes());
            toc.extend_from_slice(&entry.length.to_le_bytes());
            toc.extend_from_slice(&entry.count.to_le_bytes());
            toc.extend_from_slice(&entry.crc.to_le_bytes());
        }
        let toc_offset = self.buffer.len() as u64;
        self.buffer[0..8].copy_from_slice(MAGIC);
        self.buffer[8..10].copy_from_slice(&FORMAT_VERSION.to_le_bytes());
        self.buffer[12..16].copy_from_slice(&(toc.len() as u32).to_le_bytes());
        self.buffer[16..24].copy_from_slice(&toc_offset.to_le_bytes());
        self.buffer[24..28].copy_from_slice(&crc32(&toc).to_le_bytes());
        self.buffer.extend_from_slice(&toc);
        self.buffer
    }
}

// ---------------------------------------------------------------------------------------------
// Reading

/// Where a module's bytes come from. Only ranges are ever requested.
pub trait Storage {
    fn read_at(&self, offset: u64, length: usize) -> Result<Vec<u8>>;
}

impl Storage for Vec<u8> {
    fn read_at(&self, offset: u64, length: usize) -> Result<Vec<u8>> {
        let start = offset as usize;
        self.get(start..start + length).map(<[u8]>::to_vec).ok_or_else(|| "read past the end of the module".into())
    }
}

#[cfg(not(target_arch = "wasm32"))]
impl Storage for RefCell<std::fs::File> {
    fn read_at(&self, offset: u64, length: usize) -> Result<Vec<u8>> {
        use std::io::{Read, Seek, SeekFrom};
        let mut file = self.borrow_mut();
        let mut data = vec![0; length];
        file.seek(SeekFrom::Start(offset))?;
        file.read_exact(&mut data)?;
        Ok(data)
    }
}

pub struct Module {
    storage: Box<dyn Storage>,
    entries: Vec<Entry>,
    by_name: HashMap<String, usize>,
    cache: RefCell<HashMap<String, Rc<Vec<u8>>>>,
    bytes_read: RefCell<u64>,
}

fn u16_at(data: &[u8], at: usize) -> usize { u16::from_le_bytes(data[at..at + 2].try_into().unwrap()) as usize }
fn u32_at(data: &[u8], at: usize) -> u32 { u32::from_le_bytes(data[at..at + 4].try_into().unwrap()) }
fn u64_at(data: &[u8], at: usize) -> u64 { u64::from_le_bytes(data[at..at + 8].try_into().unwrap()) }

impl Module {
    pub fn open(storage: Box<dyn Storage>) -> Result<Module> {
        let header = storage.read_at(0, HEADER_LENGTH)?;
        if &header[0..8] != MAGIC { return Err("not a Biblelastic module".into()); }
        let version = u16_at(&header, 8) as u16;
        if version != FORMAT_VERSION { return Err(format!("module format version {version} isn't supported (expected {FORMAT_VERSION})").into()); }
        let toc = storage.read_at(u64_at(&header, 16), u32_at(&header, 12) as usize)?;
        if crc32(&toc) != u32_at(&header, 24) { return Err("the module's table of contents is corrupt".into()); }
        let mut entries = Vec::new();
        let mut at = 4;
        for _ in 0..u32_at(&toc, 0) {
            let name_length = u16_at(&toc, at);
            let name = String::from_utf8(toc[at + 2..at + 2 + name_length].to_vec())?;
            at += 2 + name_length;
            let encoding = match toc[at] { 0 => Encoding::Raw, 1 => Encoding::Packed, 2 => Encoding::Strings, 3 => Encoding::Varints,
                                           other => return Err(format!("unknown section encoding {other}").into()) };
            entries.push(Entry { name, encoding, bits: toc[at + 1], offset: u64_at(&toc, at + 4), length: u64_at(&toc, at + 12),
                                 count: u64_at(&toc, at + 20), crc: u32_at(&toc, at + 28) });
            at += 32;
        }
        let by_name = entries.iter().enumerate().map(|(n, entry)| (entry.name.clone(), n)).collect();
        Ok(Module { storage, entries, by_name, cache: RefCell::default(), bytes_read: RefCell::new((HEADER_LENGTH + toc.len()) as u64) })
    }

    #[cfg(not(target_arch = "wasm32"))]
    pub fn open_file(path: &std::path::Path) -> Result<Module> {
        let file = std::fs::File::open(path).map_err(|error| format!("{}: {error}", path.display()))?;
        Module::open(Box::new(RefCell::new(file)))
    }

    pub fn entries(&self) -> &[Entry] { &self.entries }
    pub fn has(&self, name: &str) -> bool { self.by_name.contains_key(name) }
    /// How many bytes have been requested from storage so far (to keep an eye on what queries cost)
    pub fn bytes_read(&self) -> u64 { *self.bytes_read.borrow() }

    fn entry(&self, name: &str) -> Result<&Entry> {
        self.by_name.get(name).map(|&n| &self.entries[n]).ok_or_else(|| format!("the module has no '{name}' section").into())
    }

    /// A whole section, checked against its checksum, and kept for next time
    fn section(&self, name: &str, encoding: Encoding) -> Result<(Rc<Vec<u8>>, &Entry)> {
        let entry = self.entry(name)?;
        if entry.encoding != encoding { return Err(format!("section '{name}' is {:?}, not {encoding:?}", entry.encoding).into()); }
        if let Some(data) = self.cache.borrow().get(name) { return Ok((data.clone(), entry)); }
        let data = Rc::new(self.storage.read_at(entry.offset, entry.length as usize)?);
        *self.bytes_read.borrow_mut() += entry.length;
        if crc32(&data) != entry.crc { return Err(format!("section '{name}' is corrupt").into()); }
        self.cache.borrow_mut().insert(name.to_string(), data.clone());
        Ok((data, entry))
    }

    pub fn text(&self, name: &str) -> Result<String> {
        Ok(String::from_utf8(self.section(name, Encoding::Raw)?.0.to_vec())?)
    }

    pub fn packed(&self, name: &str) -> Result<Packed> {
        let (data, entry) = self.section(name, Encoding::Packed)?;
        Ok(Packed { data, bits: entry.bits as usize, length: entry.count as usize })
    }

    pub fn strings(&self, name: &str) -> Result<Strings> {
        let (data, entry) = self.section(name, Encoding::Strings)?;
        Ok(Strings { data, length: entry.count as usize })
    }

    /// One list from a postings pair written by `ModuleWriter::postings`. Only that list's bytes are read.
    pub fn postings(&self, prefix: &str, index: usize) -> Result<Vec<u32>> {
        let offsets = self.packed(&format!("{prefix}.offsets"))?;
        let entry = self.entry(&format!("{prefix}.data"))?;
        let (start, end) = (offsets.get(index) as u64, offsets.get(index + 1) as u64);
        let data = self.storage.read_at(entry.offset + start, (end - start) as usize)?;
        *self.bytes_read.borrow_mut() += end - start;
        let mut list = Vec::new();
        let (mut value, mut difference, mut shift) = (0u32, 0u32, 0);
        for byte in data {
            difference |= ((byte & 0x7F) as u32) << shift;
            if byte & 0x80 != 0 { shift += 7; continue; }
            value += difference;
            list.push(value);
            difference = 0; shift = 0;
        }
        Ok(list)
    }
}

/// A read-only array of unsigned integers
#[derive(Clone)]
pub struct Packed {
    data: Rc<Vec<u8>>,
    bits: usize,
    length: usize,
}

impl Packed {
    pub fn len(&self) -> usize { self.length }
    pub fn is_empty(&self) -> bool { self.length == 0 }

    pub fn get(&self, index: usize) -> u32 {
        assert!(index < self.length, "index {index} is out of range ({})", self.length);
        let bit = index * self.bits;
        let window = u64::from_le_bytes(self.data[bit / 8..bit / 8 + 8].try_into().unwrap());
        ((window >> (bit % 8)) & ((1u64 << self.bits) - 1)) as u32
    }

    /// For an ascending array: the index of the first value that's >= `value` (or len() if there's none)
    pub fn lower_bound(&self, value: u32) -> usize {
        let (mut low, mut high) = (0, self.length);
        while low < high {
            let middle = (low + high) / 2;
            if self.get(middle) < value { low = middle + 1 } else { high = middle }
        }
        low
    }

    /// For an ascending array: the index of the first value that's > `value` (or len() if there's none)
    pub fn upper_bound(&self, value: u32) -> usize {
        match value.checked_add(1) { Some(next) => self.lower_bound(next), None => self.length }
    }
}

/// A read-only array of strings (a dictionary if they're sorted)
#[derive(Clone)]
pub struct Strings {
    data: Rc<Vec<u8>>,
    length: usize,
}

impl Strings {
    pub fn len(&self) -> usize { self.length }
    pub fn is_empty(&self) -> bool { self.length == 0 }

    pub fn get(&self, index: usize) -> &str {
        assert!(index < self.length, "index {index} is out of range ({})", self.length);
        let base = 4 * (self.length + 1);
        let (start, end) = (u32_at(&self.data, 4 * index) as usize, u32_at(&self.data, 4 * index + 4) as usize);
        std::str::from_utf8(&self.data[base + start..base + end]).expect("module strings are UTF-8")
    }

    fn first_not_less(&self, wanted: &str) -> usize {
        let (mut low, mut high) = (0, self.length);
        while low < high {
            let middle = (low + high) / 2;
            if self.get(middle) < wanted { low = middle + 1 } else { high = middle }
        }
        low
    }

    /// For a sorted dictionary: the index of exactly this string
    pub fn find(&self, wanted: &str) -> Option<usize> {
        let index = self.first_not_less(wanted);
        (index < self.length && self.get(index) == wanted).then_some(index)
    }

    /// For a sorted dictionary: the indexes of all the strings that start with this prefix
    pub fn find_prefix(&self, prefix: &str) -> std::ops::Range<usize> {
        let start = self.first_not_less(prefix);
        let mut end = start;
        while end < self.length && self.get(end).starts_with(prefix) { end += 1; }
        start..end
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let mut writer = ModuleWriter::new();
        writer.raw("note", "kia ora".as_bytes());
        writer.packed("numbers", &[0, 5, 1000, 3, 70000, 2]);
        writer.packed("ascending", &[2, 2, 5, 9, 9, 9, 40]);
        writer.packed("empty", &[]);
        writer.strings("words", &["alpha", "beta", "betamax", "gamma", "λόγος"]);
        writer.postings("lists", &[vec![1, 2, 300, 70000], vec![], vec![0, 4_000_000_000]]);
        let module = Module::open(Box::new(writer.finish())).unwrap();

        assert_eq!(module.text("note").unwrap(), "kia ora");
        let numbers = module.packed("numbers").unwrap();
        assert_eq!((0..numbers.len()).map(|n| numbers.get(n)).collect::<Vec<_>>(), [0, 5, 1000, 3, 70000, 2]);
        let ascending = module.packed("ascending").unwrap();
        assert_eq!((ascending.lower_bound(9), ascending.upper_bound(9), ascending.lower_bound(41), ascending.lower_bound(0)), (3, 6, 7, 0));
        assert!(module.packed("empty").unwrap().is_empty());
        let words = module.strings("words").unwrap();
        assert_eq!((words.get(4), words.find("beta"), words.find("bet"), words.find_prefix("beta"), words.find_prefix("z")), ("λόγος", Some(1), None, 1..3, 4..4)); // Sorted by bytes, so z is before λ
        assert_eq!(module.postings("lists", 0).unwrap(), [1, 2, 300, 70000]);
        assert!(module.postings("lists", 1).unwrap().is_empty());
        assert_eq!(module.postings("lists", 2).unwrap(), [0, 4_000_000_000]);
        assert!(module.packed("words").is_err() && module.packed("missing").is_err());
    }

    #[test]
    fn corruption_is_detected() {
        let mut writer = ModuleWriter::new();
        writer.raw("note", b"text");
        let mut bytes = writer.finish();
        bytes[HEADER_LENGTH] ^= 1;
        assert!(Module::open(Box::new(bytes.clone())).unwrap().text("note").is_err());
        bytes[0] = b'X';
        assert!(Module::open(Box::new(bytes)).is_err());
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
    }
}
