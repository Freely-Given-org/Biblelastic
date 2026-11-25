//! The Biblelastic module container format (v1) -- see docs/ModuleFormat.md
//!
//! A module is one file: a fixed header, then named sections, then a table of contents.
//! Each section is stored as pages, which are read (and decompressed and checked) only when something in them is wanted,
//! and kept in a cache of limited size. Everything is read with explicit (offset, length) requests,
//! so that the same code works on a local file, on browser storage, or on bytes in memory.

use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

pub const MAGIC: &[u8; 8] = b"BLMODULE";
pub const FORMAT_VERSION: u16 = 1;
const HEADER_LENGTH: usize = 32;
const PADDING: usize = 8; // After packed data, so a value can always be read as part of eight bytes
/// Pages are 2^this bytes (before compression) unless the writer is told otherwise
pub const DEFAULT_PAGE_BITS: u8 = 14;
/// How much the page cache holds unless it's told otherwise
pub const DEFAULT_CACHE_BYTES: usize = 16 << 20;

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

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Compression { None = 0, Zstd = 1 }

/// Where one page is in the file
#[derive(Clone, Copy, Debug)]
pub struct Page {
    pub offset: u64,
    /// As stored, i.e., after any compression
    pub length: u32,
    /// Of the bytes as stored
    pub crc: u32,
}

#[derive(Clone, Debug)]
pub struct Entry {
    pub name: String,
    pub encoding: Encoding,
    pub bits: u8,
    pub compression: Compression,
    pub page_bits: u8,
    pub offset: u64,
    /// As stored, i.e., after any compression
    pub length: u64,
    /// Before compression
    pub raw_length: u64,
    pub count: u64,
    pub pages: Vec<Page>,
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

/// Compresses one page into a zstd frame. (The engine can only decompress, so whatever compiles modules provides this.)
pub type Compressor = Box<dyn Fn(&[u8]) -> Vec<u8>>;

pub struct ModuleWriter {
    buffer: Vec<u8>,
    entries: Vec<Entry>,
    page_bits: u8,
    compressor: Option<Compressor>,
}

impl Default for ModuleWriter { fn default() -> Self { Self::new() } }

impl ModuleWriter {
    pub fn new() -> Self { ModuleWriter { buffer: vec![0; HEADER_LENGTH], entries: Vec::new(), page_bits: DEFAULT_PAGE_BITS, compressor: None } }

    /// Pages of 2^`page_bits` bytes, and compress the sections that it helps
    pub fn with(page_bits: u8, compressor: Option<Compressor>) -> Self { ModuleWriter { page_bits, compressor, ..Self::new() } }

    fn add(&mut self, name: &str, encoding: Encoding, bits: u8, count: usize, data: &[u8]) {
        assert!(!self.entries.iter().any(|entry| entry.name == name), "duplicate section {name}");
        let chunks: Vec<&[u8]> = data.chunks(1 << self.page_bits).collect();
        // Compression is all or nothing for a section, and only used if it saves at least a tenth
        let compressed: Option<Vec<Vec<u8>>> = self.compressor.as_ref().map(|compress| chunks.iter().map(|chunk| compress(chunk)).collect::<Vec<_>>())
            .filter(|pages| pages.iter().map(Vec::len).sum::<usize>() * 10 <= data.len() * 9);
        let offset = self.buffer.len() as u64;
        let mut pages = Vec::with_capacity(chunks.len());
        for (n, chunk) in chunks.iter().enumerate() {
            let stored: &[u8] = compressed.as_ref().map_or(chunk, |pages| &pages[n]);
            pages.push(Page { offset: self.buffer.len() as u64, length: stored.len() as u32, crc: crc32(stored) });
            self.buffer.extend_from_slice(stored);
        }
        self.entries.push(Entry { name: name.to_string(), encoding, bits, compression: if compressed.is_some() { Compression::Zstd } else { Compression::None },
                                  page_bits: self.page_bits, offset, length: self.buffer.len() as u64 - offset, raw_length: data.len() as u64, count: count as u64, pages });
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
            toc.extend_from_slice(&[entry.encoding as u8, entry.bits, entry.compression as u8, entry.page_bits]);
            toc.extend_from_slice(&entry.offset.to_le_bytes());
            toc.extend_from_slice(&entry.raw_length.to_le_bytes());
            toc.extend_from_slice(&entry.count.to_le_bytes());
            for page in &entry.pages {
                toc.extend_from_slice(&page.length.to_le_bytes());
                toc.extend_from_slice(&page.crc.to_le_bytes());
            }
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

#[derive(Default)]
struct Cached {
    pages: HashMap<(u32, u32, u32), (Rc<Vec<u8>>, u64)>, // (module, section, page) → its bytes, and when they were last wanted
    bytes: usize,
    clock: u64,
    modules: u32,
}

/// The pages that have been read, shared by all the open modules. When it's over its limit, the pages that were used longest ago are dropped.
pub struct PageCache {
    limit: usize,
    cached: RefCell<Cached>,
}

impl PageCache {
    pub fn new(limit: usize) -> Rc<PageCache> { Rc::new(PageCache { limit, cached: RefCell::default() }) }

    /// How many bytes of pages are being held now
    pub fn bytes(&self) -> usize { self.cached.borrow().bytes }

    fn get(&self, key: (u32, u32, u32), load: impl FnOnce() -> Result<Vec<u8>>) -> Result<Rc<Vec<u8>>> {
        {
            let mut cached = self.cached.borrow_mut();
            cached.clock += 1;
            let clock = cached.clock;
            if let Some((page, used)) = cached.pages.get_mut(&key) { *used = clock; return Ok(page.clone()); }
        }
        let page = Rc::new(load()?);
        let mut cached = self.cached.borrow_mut();
        cached.bytes += page.len();
        let clock = cached.clock;
        cached.pages.insert(key, (page.clone(), clock));
        if cached.bytes > self.limit { // Make room for a while, not just for this page
            let mut oldest: Vec<((u32, u32, u32), u64)> = cached.pages.iter().map(|(&key, &(_, used))| (key, used)).collect();
            oldest.sort_unstable_by_key(|&(_, used)| used);
            for (key, _) in oldest {
                if cached.bytes <= self.limit / 4 * 3 { break; }
                if let Some((dropped, _)) = cached.pages.remove(&key) { cached.bytes -= dropped.len(); }
            }
        }
        Ok(page)
    }
}

struct Inner {
    storage: Box<dyn Storage>,
    entries: Vec<Entry>,
    by_name: HashMap<String, usize>,
    cache: Rc<PageCache>,
    id: u32,
    bytes_read: RefCell<u64>,
}

impl Inner {
    fn page(&self, section: usize, page: usize) -> Result<Rc<Vec<u8>>> {
        self.cache.get((self.id, section as u32, page as u32), || {
            let entry = &self.entries[section];
            let stored = entry.pages.get(page).ok_or_else(|| format!("section '{}' has no page {page}", entry.name))?;
            let data = self.storage.read_at(stored.offset, stored.length as usize)?;
            *self.bytes_read.borrow_mut() += stored.length as u64;
            if crc32(&data) != stored.crc { return Err(format!("section '{}' is corrupt (page {page})", entry.name).into()); }
            let raw_length = (entry.raw_length as usize - (page << entry.page_bits)).min(1 << entry.page_bits);
            let data = match entry.compression {
                Compression::None => data,
                Compression::Zstd => {
                    let mut raw = vec![0; raw_length];
                    let written = ruzstd::decoding::FrameDecoder::new().decode_all(&data, &mut raw).map_err(|error| format!("section '{}' can't be decompressed: {error:?}", entry.name))?;
                    raw.truncate(written);
                    raw
                }
            };
            if data.len() != raw_length { return Err(format!("section '{}' is corrupt (page {page} is the wrong length)", entry.name).into()); }
            Ok(data)
        })
    }
}

/// Reads any part of one section, a page at a time
#[derive(Clone)]
struct Reader {
    inner: Rc<Inner>,
    section: usize,
    page_bits: u8,
    /// The page that was used last, so that reading along a section doesn't keep going back to the cache
    last: RefCell<Option<(usize, Rc<Vec<u8>>)>>,
}

impl Reader {
    /// Panics if the page can't be read, because reads happen deep inside lookups that have no way to fail.
    fn page(&self, page: usize) -> Rc<Vec<u8>> {
        if let Some((number, data)) = &*self.last.borrow() { if *number == page { return data.clone(); } }
        let data = self.inner.page(self.section, page).unwrap_or_else(|error| panic!("{error}"));
        *self.last.borrow_mut() = Some((page, data.clone()));
        data
    }

    fn read(&self, start: usize, out: &mut [u8]) {
        let (mut at, mut done) = (start, 0);
        while done < out.len() {
            let data = self.page(at >> self.page_bits);
            let within = at & ((1 << self.page_bits) - 1);
            let length = (out.len() - done).min(data.len().checked_sub(within).filter(|&left| left > 0).expect("read past the end of a section"));
            out[done..done + length].copy_from_slice(&data[within..within + length]);
            at += length;
            done += length;
        }
    }

    fn u64_at(&self, start: usize) -> u64 {
        let within = start & ((1 << self.page_bits) - 1);
        if let Some((number, data)) = &*self.last.borrow() {
            if *number == start >> self.page_bits && within + 8 <= data.len() { return u64::from_le_bytes(data[within..within + 8].try_into().unwrap()); }
        }
        let mut bytes = [0; 8];
        self.read(start, &mut bytes);
        u64::from_le_bytes(bytes)
    }
}

/// An open module. Cloning it is cheap, and gives another handle on the same one.
#[derive(Clone)]
pub struct Module {
    inner: Rc<Inner>,
}

fn u16_at(data: &[u8], at: usize) -> usize { u16::from_le_bytes(data[at..at + 2].try_into().unwrap()) as usize }
fn u32_at(data: &[u8], at: usize) -> u32 { u32::from_le_bytes(data[at..at + 4].try_into().unwrap()) }
fn u64_at(data: &[u8], at: usize) -> u64 { u64::from_le_bytes(data[at..at + 8].try_into().unwrap()) }

impl Module {
    /// Open a module with a page cache of its own
    pub fn open(storage: Box<dyn Storage>) -> Result<Module> { Module::open_with(storage, &PageCache::new(DEFAULT_CACHE_BYTES)) }

    /// Open a module that shares a page cache with others. Only the header and the table of contents are read.
    pub fn open_with(storage: Box<dyn Storage>, cache: &Rc<PageCache>) -> Result<Module> {
        let header = storage.read_at(0, HEADER_LENGTH)?;
        if &header[0..8] != MAGIC { return Err("not a Biblelastic module".into()); }
        let version = u16_at(&header, 8) as u16;
        if version != FORMAT_VERSION { return Err(format!("module format version {version} isn't supported (expected {FORMAT_VERSION}): the modules need to be compiled again").into()); }
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
            let compression = match toc[at + 2] { 0 => Compression::None, 1 => Compression::Zstd, other => return Err(format!("unknown compression {other}").into()) };
            let (bits, page_bits) = (toc[at + 1], toc[at + 3]);
            let (offset, raw_length, count) = (u64_at(&toc, at + 4), u64_at(&toc, at + 12), u64_at(&toc, at + 20));
            at += 28;
            let mut pages = Vec::new();
            let mut page_offset = offset;
            for _ in 0..(raw_length as usize).div_ceil(1 << page_bits) {
                pages.push(Page { offset: page_offset, length: u32_at(&toc, at), crc: u32_at(&toc, at + 4) });
                page_offset += u32_at(&toc, at) as u64;
                at += 8;
            }
            entries.push(Entry { name, encoding, bits, compression, page_bits, offset, length: page_offset - offset, raw_length, count, pages });
        }
        let by_name = entries.iter().enumerate().map(|(n, entry)| (entry.name.clone(), n)).collect();
        let id = { let mut cached = cache.cached.borrow_mut(); cached.modules += 1; cached.modules };
        Ok(Module { inner: Rc::new(Inner { storage, entries, by_name, cache: cache.clone(), id, bytes_read: RefCell::new((HEADER_LENGTH + toc.len()) as u64) }) })
    }

    #[cfg(not(target_arch = "wasm32"))]
    pub fn open_file(path: &std::path::Path) -> Result<Module> { Module::open_file_with(path, &PageCache::new(DEFAULT_CACHE_BYTES)) }

    #[cfg(not(target_arch = "wasm32"))]
    pub fn open_file_with(path: &std::path::Path, cache: &Rc<PageCache>) -> Result<Module> {
        let file = std::fs::File::open(path).map_err(|error| format!("{}: {error}", path.display()))?;
        Module::open_with(Box::new(RefCell::new(file)), cache)
    }

    pub fn entries(&self) -> &[Entry] { &self.inner.entries }
    pub fn has(&self, name: &str) -> bool { self.inner.by_name.contains_key(name) }
    /// How many bytes have been requested from storage so far (to keep an eye on what queries cost)
    pub fn bytes_read(&self) -> u64 { *self.inner.bytes_read.borrow() }

    fn reader(&self, name: &str, encoding: Encoding) -> Result<(Reader, &Entry)> {
        let &section = self.inner.by_name.get(name).ok_or_else(|| format!("the module has no '{name}' section"))?;
        let entry = &self.inner.entries[section];
        if entry.encoding != encoding { return Err(format!("section '{name}' is {:?}, not {encoding:?}", entry.encoding).into()); }
        Ok((Reader { inner: self.inner.clone(), section, page_bits: entry.page_bits, last: RefCell::new(None) }, entry))
    }

    /// A whole section of text
    pub fn text(&self, name: &str) -> Result<String> {
        let &section = self.inner.by_name.get(name).ok_or_else(|| format!("the module has no '{name}' section"))?;
        let entry = &self.inner.entries[section];
        if entry.encoding != Encoding::Raw { return Err(format!("section '{name}' is {:?}, not Raw", entry.encoding).into()); }
        let mut data = Vec::with_capacity(entry.raw_length as usize);
        for page in 0..entry.pages.len() { data.extend_from_slice(&self.inner.page(section, page)?); }
        Ok(String::from_utf8(data)?)
    }

    /// A whole raw section, as bytes
    pub fn bytes(&self, name: &str) -> Result<Vec<u8>> {
        let &section = self.inner.by_name.get(name).ok_or_else(|| format!("the module has no '{name}' section"))?;
        let entry = &self.inner.entries[section];
        if entry.encoding != Encoding::Raw { return Err(format!("section '{name}' is {:?}, not Raw", entry.encoding).into()); }
        let mut data = Vec::with_capacity(entry.raw_length as usize);
        for page in 0..entry.pages.len() { data.extend_from_slice(&self.inner.page(section, page)?); }
        Ok(data)
    }

    pub fn packed(&self, name: &str) -> Result<Packed> {
        let (reader, entry) = self.reader(name, Encoding::Packed)?;
        Ok(Packed { reader, bits: entry.bits as usize, length: entry.count as usize })
    }

    pub fn strings(&self, name: &str) -> Result<Strings> {
        let (reader, entry) = self.reader(name, Encoding::Strings)?;
        Ok(Strings { reader, length: entry.count as usize })
    }

    /// One list from a postings pair written by `ModuleWriter::postings`. Only the pages that the list is in are read.
    pub fn postings(&self, prefix: &str, index: usize) -> Result<Vec<u32>> {
        let offsets = self.packed(&format!("{prefix}.offsets"))?;
        let (reader, entry) = self.reader(&format!("{prefix}.data"), Encoding::Varints)?;
        let (start, end) = (offsets.get(index) as usize, offsets.get(index + 1) as usize);
        let mut list = Vec::new();
        let (mut value, mut difference, mut shift) = (0u32, 0u32, 0);
        for page in start >> entry.page_bits..(end + (1 << entry.page_bits) - 1) >> entry.page_bits {
            let data = self.inner.page(reader.section, page)?;
            let base = page << entry.page_bits;
            for &byte in &data[start.max(base) - base..end.min(base + data.len()) - base] {
                difference |= ((byte & 0x7F) as u32) << shift;
                if byte & 0x80 != 0 { shift += 7; continue; }
                value += difference;
                list.push(value);
                difference = 0; shift = 0;
            }
        }
        Ok(list)
    }
}

/// A read-only array of unsigned integers
#[derive(Clone)]
pub struct Packed {
    reader: Reader,
    bits: usize,
    length: usize,
}

impl Packed {
    pub fn len(&self) -> usize { self.length }
    pub fn is_empty(&self) -> bool { self.length == 0 }

    pub fn get(&self, index: usize) -> u32 {
        assert!(index < self.length, "index {index} is out of range ({})", self.length);
        let bit = index * self.bits;
        ((self.reader.u64_at(bit / 8) >> (bit % 8)) & ((1u64 << self.bits) - 1)) as u32
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
    reader: Reader,
    length: usize,
}

impl Strings {
    pub fn len(&self) -> usize { self.length }
    pub fn is_empty(&self) -> bool { self.length == 0 }

    pub fn get(&self, index: usize) -> String {
        assert!(index < self.length, "index {index} is out of range ({})", self.length);
        let offsets = self.reader.u64_at(4 * index); // This string's offset and the next one's (the bytes after the last offset are text, so there are always eight)
        let (start, end) = (offsets as u32 as usize, (offsets >> 32) as usize);
        let mut data = vec![0; end - start];
        self.reader.read(4 * (self.length + 1) + start, &mut data);
        String::from_utf8(data).expect("module strings are UTF-8")
    }

    fn first_not_less(&self, wanted: &str) -> usize {
        let (mut low, mut high) = (0, self.length);
        while low < high {
            let middle = (low + high) / 2;
            if self.get(middle).as_str() < wanted { low = middle + 1 } else { high = middle }
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

    fn check(module: &Module) {
        assert_eq!(module.text("note").unwrap(), "kia ora");
        let numbers = module.packed("numbers").unwrap();
        assert_eq!((0..numbers.len()).map(|n| numbers.get(n)).collect::<Vec<_>>(), [0, 5, 1000, 3, 70000, 2]);
        let ascending = module.packed("ascending").unwrap();
        assert_eq!((ascending.lower_bound(9), ascending.upper_bound(9), ascending.lower_bound(41), ascending.lower_bound(0)), (3, 6, 7, 0));
        assert!(module.packed("empty").unwrap().is_empty());
        let words = module.strings("words").unwrap();
        assert_eq!((words.get(4).as_str(), words.find("beta"), words.find("bet"), words.find_prefix("beta"), words.find_prefix("z")), ("λόγος", Some(1), None, 1..3, 4..4)); // Sorted by bytes, so z is before λ
        assert_eq!(module.postings("lists", 0).unwrap(), [1, 2, 300, 70000]);
        assert!(module.postings("lists", 1).unwrap().is_empty());
        assert_eq!(module.postings("lists", 2).unwrap(), [0, 4_000_000_000]);
        let many = module.packed("many").unwrap();
        assert!((0..many.len()).all(|n| many.get(n) as usize == n * 7) && many.lower_bound(7 * 1234) == 1234);
        let repeated = module.strings("repeated").unwrap();
        assert!(repeated.len() == 300 && repeated.get(299) == "the same words again");
        assert!(module.packed("words").is_err() && module.packed("missing").is_err());
    }

    fn write(mut writer: ModuleWriter) -> Vec<u8> {
        writer.raw("note", "kia ora".as_bytes());
        writer.packed("numbers", &[0, 5, 1000, 3, 70000, 2]);
        writer.packed("ascending", &[2, 2, 5, 9, 9, 9, 40]);
        writer.packed("empty", &[]);
        writer.strings("words", &["alpha", "beta", "betamax", "gamma", "λόγος"]);
        writer.postings("lists", &[vec![1, 2, 300, 70000], vec![], vec![0, 4_000_000_000]]);
        writer.packed("many", &(0..5000).map(|n| n * 7).collect::<Vec<_>>());
        writer.strings("repeated", &vec!["the same words again"; 300]);
        writer.finish()
    }

    #[test]
    fn round_trip() {
        check(&Module::open(Box::new(write(ModuleWriter::new()))).unwrap());
    }

    /// Pages of only eight bytes, so that values, strings and lists all cross from one page to the next
    #[test]
    fn tiny_pages_and_a_tiny_cache() {
        let cache = PageCache::new(64);
        let module = Module::open_with(Box::new(write(ModuleWriter::with(3, None))), &cache).unwrap();
        check(&module);
        assert!(cache.bytes() <= 64 && module.entries().iter().any(|entry| entry.pages.len() > 100));
    }

    #[test]
    fn compressed() {
        let compress: Compressor = Box::new(|page| ruzstd::encoding::compress_to_vec(page, ruzstd::encoding::CompressionLevel::Fastest));
        let bytes = write(ModuleWriter::with(10, Some(compress)));
        let module = Module::open(Box::new(bytes)).unwrap();
        check(&module);
        let repeated = module.entries().iter().find(|entry| entry.name == "repeated").unwrap();
        assert!(repeated.compression == Compression::Zstd && repeated.length < repeated.raw_length / 2 && repeated.pages.len() > 1);
        assert!(module.entries().iter().any(|entry| entry.compression == Compression::None)); // The ones that it doesn't help
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
