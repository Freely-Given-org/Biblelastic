//! The catalogue of a folder of modules (`index.json`), and publishing: copying the modules that may be passed on to a web server's folder, with their catalogue.
//!
//! Each module in the catalogue has its size, its SHA-256 (so that an app can tell when it has changed, and ask for it by an address that a cache won't
//! have an old copy of), and what it is and what may be done with it (from the module's own header).

use std::fs;
use std::path::Path;

use biblelastic_engine::format::{Module, Result};

/// One module, as the catalogue lists it
struct Listed {
    name: String,
    bytes: u64,
    sha256: String,
    fields: Vec<(&'static str, String)>,
    redistributable: bool,
    verified: bool,
}

fn list(folder: &Path) -> Result<Vec<Listed>> {
    let mut names: Vec<String> = fs::read_dir(folder)?.flatten()
        .filter_map(|entry| entry.file_name().to_string_lossy().strip_suffix(".blm").map(str::to_string)).collect();
    names.sort();
    let mut listed = Vec::new();
    for name in names {
        let path = folder.join(format!("{name}.blm"));
        let data = fs::read(&path)?;
        let module = Module::open_file(&path)?;
        let field = |section: &str| if module.has(section) { module.text(section).unwrap_or_default() } else { String::new() };
        let fields = [("kind", "module.kind"), ("work", "module.work"), ("edition", "module.edition"), ("layer", "module.layer"), ("title", "module.title"),
                      ("language", "module.language"), ("licence", "module.licence"), ("copyright", "module.copyright"), ("attribution", "module.attribution"), ("starter", "module.starter")]
            .into_iter().map(|(key, section)| (key, field(section))).filter(|(_, value)| !value.is_empty()).collect();
        // (A module from before rights were recorded is taken to be redistributable, as everything so far is; publishing says which those are)
        listed.push(Listed { name, bytes: data.len() as u64, sha256: sha256_hex(&data), fields, redistributable: field("module.redistributable") != "false",
                             verified: field("module.licence_verified") == "true" });
    }
    Ok(listed)
}

fn catalogue(modules: &[&Listed]) -> String {
    let entries: Vec<String> = modules.iter().map(|module| {
        let mut fields = vec![format!("\"name\": {}", quote(&module.name)), format!("\"bytes\": {}", module.bytes), format!("\"sha256\": \"{}\"", module.sha256)];
        fields.extend(module.fields.iter().map(|(key, value)| format!("\"{key}\": {}", quote(value))));
        fields.push(format!("\"licence_verified\": {}", module.verified));
        format!("    {{{}}}", fields.join(", "))
    }).collect();
    format!("{{\n  \"format\": {},\n  \"modules\": [\n{}\n  ]\n}}\n", biblelastic_engine::format::FORMAT_VERSION, entries.join(",\n"))
}

/// The catalogue of every module in a folder (`index.json`), which an installer downloads first to see what there is
pub fn write_index(folder: &Path) -> Result<()> {
    let listed = list(folder)?;
    fs::write(folder.join("index.json"), catalogue(&listed.iter().collect::<Vec<_>>())).map_err(|error| format!("{}: {error}", folder.display()).into())
}

/// Copy the modules that may be passed on into `to` (only those that have changed), with their catalogue, and take away any there that aren't in it any more.
/// Says which were left out, and how many licences haven't been checked.
pub fn publish(modules: &Path, to: &Path) -> Result<()> {
    fs::create_dir_all(to).map_err(|error| format!("{}: {error}", to.display()))?;
    let listed = list(modules)?;
    let (wanted, left_out): (Vec<&Listed>, Vec<&Listed>) = listed.iter().partition(|module| module.redistributable);
    let (mut copied, mut unchanged) = (0, 0);
    for module in &wanted {
        let target = to.join(format!("{}.blm", module.name));
        if fs::read(&target).is_ok_and(|data| sha256_hex(&data) == module.sha256) { unchanged += 1; continue; }
        let partial = to.join(format!("{}.blm.part", module.name));
        fs::copy(modules.join(format!("{}.blm", module.name)), &partial)?;
        fs::rename(&partial, &target)?; // So that nothing is ever served half-copied
        copied += 1;
    }
    let mut removed = Vec::new();
    for entry in fs::read_dir(to)?.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        if let Some(stem) = name.strip_suffix(".blm") {
            if !wanted.iter().any(|module| module.name == stem) { fs::remove_file(entry.path())?; removed.push(stem.to_string()); }
        }
    }
    let index = to.join("index.json");
    let partial = to.join("index.json.part");
    fs::write(&partial, catalogue(&wanted))?;
    fs::rename(&partial, &index)?;
    let total: u64 = wanted.iter().map(|module| module.bytes).sum();
    println!("{} modules ({:.0} MB) in {}: {copied} copied, {unchanged} unchanged{}", wanted.len(), total as f64 / 1048576.0, to.display(),
             if removed.is_empty() { String::new() } else { format!(", {} removed ({})", removed.len(), removed.join(", ")) });
    if !left_out.is_empty() { println!("Left out, as they mayn't be passed on: {}", left_out.iter().map(|module| module.name.as_str()).collect::<Vec<_>>().join(", ")); }
    let unchecked: Vec<&str> = wanted.iter().filter(|module| !module.verified).map(|module| module.name.as_str()).collect();
    if !unchecked.is_empty() { println!("{} of them have licences that haven't been checked against their sources (licence_verified = false in the registry)", unchecked.len()); }
    let unknown: Vec<&str> = wanted.iter().filter(|module| !module.fields.iter().any(|(key, _)| *key == "licence")).map(|module| module.name.as_str()).collect();
    if !unknown.is_empty() { println!("{} of them don't say what their licence is: {}", unknown.len(), unknown.join(", ")); }
    Ok(())
}

fn quote(text: &str) -> String { biblelastic_engine::api::quote(text) }

/// SHA-256 (FIPS 180-4), written out here so that the tool needs no other crate
pub fn sha256_hex(data: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
        0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
        0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    let mut state: [u32; 8] = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    let mut message = data.to_vec();
    message.push(0x80);
    while message.len() % 64 != 56 { message.push(0); }
    message.extend_from_slice(&((data.len() as u64) * 8).to_be_bytes());
    for block in message.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (index, word) in block.chunks_exact(4).enumerate() { w[index] = u32::from_be_bytes([word[0], word[1], word[2], word[3]]); }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7) ^ w[index - 15].rotate_right(18) ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17) ^ w[index - 2].rotate_right(19) ^ (w[index - 2] >> 10);
            w[index] = w[index - 16].wrapping_add(s0).wrapping_add(w[index - 7]).wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = state;
        for index in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choice = (e & f) ^ (!e & g);
            let temp1 = h.wrapping_add(s1).wrapping_add(choice).wrapping_add(K[index]).wrapping_add(w[index]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let majority = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(majority);
            (h, g, f, e, d, c, b, a) = (g, f, e, d.wrapping_add(temp1), c, b, a, temp1.wrapping_add(temp2));
        }
        for (value, add) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) { *value = value.wrapping_add(add); }
    }
    state.iter().map(|value| format!("{value:08x}")).collect()
}

#[cfg(test)]
mod tests {
    #[test]
    fn sha256_is_right() {
        assert_eq!(super::sha256_hex(b""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
        assert_eq!(super::sha256_hex(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        assert_eq!(super::sha256_hex(&[b'a'; 1000]), "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3");
    }
}
