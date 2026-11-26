//! A small JSON reader, for the files that the CLI reads (models' configurations and manifests), so that it needs no other crate.

use biblelastic_engine::format::Result;

/// Just enough JSON for a model's configuration, a safetensors header, and a manifest
pub enum Json {
    Null,
    Bool(bool),
    Number(f64),
    Text(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    pub fn parse(text: &str) -> Result<Json> {
        let characters: Vec<char> = text.chars().collect();
        let mut position = 0;
        let value = Json::value(&characters, &mut position)?;
        Ok(value)
    }

    pub fn get(&self, key: &str) -> Option<&Json> { match self { Json::Object(fields) => fields.iter().find(|(name, _)| name == key).map(|(_, value)| value), _ => None } }
    pub fn number(&self) -> Option<f64> { match self { Json::Number(value) => Some(*value), _ => None } }
    pub fn text(&self) -> Option<&str> { match self { Json::Text(value) => Some(value), _ => None } }

    fn value(characters: &[char], position: &mut usize) -> Result<Json> {
        let skip = |position: &mut usize| while *position < characters.len() && characters[*position].is_whitespace() { *position += 1; };
        skip(position);
        let character = *characters.get(*position).ok_or("unexpected end of JSON")?;
        match character {
            '{' | '[' => {
                *position += 1;
                let (mut fields, mut items) = (Vec::new(), Vec::new());
                loop {
                    skip(position);
                    if characters.get(*position) == Some(&if character == '{' { '}' } else { ']' }) { *position += 1; break; }
                    if character == '{' {
                        let Json::Text(key) = Json::value(characters, position)? else { return Err("a JSON key must be a string".into()) };
                        skip(position);
                        if characters.get(*position) != Some(&':') { return Err("expected : in JSON".into()); }
                        *position += 1;
                        fields.push((key, Json::value(characters, position)?));
                    } else { items.push(Json::value(characters, position)?); }
                    skip(position);
                    if characters.get(*position) == Some(&',') { *position += 1; }
                }
                Ok(if character == '{' { Json::Object(fields) } else { Json::Array(items) })
            }
            '"' => {
                *position += 1;
                let mut text = String::new();
                while let Some(&next) = characters.get(*position) {
                    *position += 1;
                    match next {
                        '"' => return Ok(Json::Text(text)),
                        '\\' => {
                            let escaped = *characters.get(*position).ok_or("unexpected end of JSON")?;
                            *position += 1;
                            match escaped {
                                'n' => text.push('\n'), 't' => text.push('\t'), 'r' => text.push('\r'), 'b' => text.push('\u{8}'), 'f' => text.push('\u{c}'),
                                'u' => {
                                    let hex: String = characters.get(*position..*position + 4).ok_or("bad \\u in JSON")?.iter().collect();
                                    *position += 4;
                                    text.push(char::from_u32(u32::from_str_radix(&hex, 16)?).unwrap_or('\u{FFFD}'));
                                }
                                other => text.push(other),
                            }
                        }
                        other => text.push(other),
                    }
                }
                Err("unterminated string in JSON".into())
            }
            't' | 'f' | 'n' => {
                let word: String = characters[*position..].iter().take_while(|character| character.is_ascii_alphabetic()).collect();
                *position += word.len();
                match word.as_str() { "true" => Ok(Json::Bool(true)), "false" => Ok(Json::Bool(false)), "null" => Ok(Json::Null), _ => Err(format!("unexpected '{word}' in JSON").into()) }
            }
            _ => {
                let number: String = characters[*position..].iter().take_while(|character| character.is_ascii_digit() || "+-.eE".contains(**character)).collect();
                *position += number.len();
                Ok(Json::Number(number.parse().map_err(|_| format!("unexpected '{character}' in JSON"))?))
            }
        }
    }
}
