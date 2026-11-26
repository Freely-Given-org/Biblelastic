/// The app's own words, in English and Spanish (more languages can be added to each list).
library;

import 'dart:ui';

class Strings {
  Strings(Locale locale) : _column = locale.languageCode == 'es' ? 1 : 0;
  final int _column;

  String _pick(List<String> texts) => texts[_column];

  String get appName => 'Biblelastic';
  String get starting => _pick(['Starting…', 'Iniciando…']);
  String get modules => _pick(['Modules', 'Módulos']);
  String get search => _pick(['Search', 'Buscar']);
  String get introduction => _pick(['Introduction', 'Introducción']);
  String get chooseBook => _pick(['Choose a book', 'Elija un libro']);
  String get chooseChapter => _pick(['Choose a chapter', 'Elija un capítulo']);
  String get previousSection => _pick(['Previous section', 'Sección anterior']);
  String get nextSection => _pick(['Next section', 'Sección siguiente']);
  String get noBible => _pick(['No Bible is installed yet.', 'Aún no hay ninguna Biblia instalada.']);
  String get getModules => _pick(['Get modules', 'Obtener módulos']);
  String get installAll => _pick(['Install all', 'Instalar todos']);
  String get updateAll => _pick(['Install and update all', 'Instalar y actualizar todos']);
  String get updateAvailable => _pick(['Update available', 'Hay una actualización']);
  String get update => _pick(['Update', 'Actualizar']);
  String get aboutWorks => _pick(['Licences and sources', 'Licencias y fuentes']);
  String get licence => _pick(['Licence', 'Licencia']);
  String get notStated => _pick(['not stated', 'no se indica']);
  String get removeAll => _pick(['Remove all', 'Quitar todos']);
  String get installed => _pick(['Installed', 'Instalado']);
  String get notInstalled => _pick(['Not installed', 'No instalado']);
  String get modulesFrom => _pick(['Modules come from', 'Los módulos vienen de']);
  String get noCatalogue => _pick(["The list of modules couldn't be fetched.", 'No se pudo obtener la lista de módulos.']);
  String get searchHint => _pick(['Words, e.g., grace truth', 'Palabras, p. ej., grace truth']);
  String get readersVersion => _pick(['Readers’', 'Lectores']);
  String get literalVersion => _pick(['Literal', 'Literal']);
  String get bothVersions => _pick(['Both', 'Ambas']);
  String get topic => _pick(['Topic', 'Tema']);
  String get together => _pick(['Sentence', 'Oración']);
  String get originalTerms => _pick(['Originals', 'Originales']);
  String get topicHint => _pick(['A subject, e.g., once saved always saved', 'Un tema, p. ej., once saved always saved']);
  String get articles => _pick(['Articles', 'Artículos']);
  String get keyPassages => _pick(['Passages they refer to most', 'Pasajes que más citan']);
  String get otherSide => _pick(['The other side of the question', 'El otro lado de la cuestión']);
  String get inTheBible => _pick(['These words in one sentence', 'Estas palabras en una oración']);
  String get inTheNotes => _pick(['These words in notes and articles', 'Estas palabras en notas y artículos']);
  String get meaningHere => _pick(['Meaning here', 'Significado aquí']);
  String get similarMeaning => _pick(['Words with a similar meaning:', 'Palabras de significado parecido:']);
  String get aboutThis => _pick(['About this:', 'Sobre esto:']);
  String get library => _pick(['Library', 'Biblioteca']);
  String get bible => _pick(['Bible', 'Biblia']);
  String get byMeaning => _pick(['Passages about this (by meaning)', 'Pasajes sobre esto (por significado)']);
  String get byMeaningElsewhere => _pick(['Notes, articles, and books about this (by meaning)', 'Notas, artículos y libros sobre esto (por significado)']);
  String get findingByMeaning => _pick(['Looking for passages about this…', 'Buscando pasajes sobre esto…']);
  String get chooseBible => _pick(['Choose a Bible', 'Elija una Biblia']);
  String get books => _pick(['Books', 'Libros']);
  String get commentaries => _pick(['Commentaries', 'Comentarios']);
  String get dictionaries => _pick(['Dictionaries and handbooks', 'Diccionarios y manuales']);
  String get more => _pick(['More', 'Más']);
  String get previous => _pick(['Previous', 'Anterior']);
  String get next => _pick(['Next', 'Siguiente']);
  String get seeAlso => _pick(['See also', 'Véase también']);
  String domainWords(int total) => _pick(['$total words have a meaning in', '$total palabras tienen un significado en']);
  String timesHere(int count) => count == 1 ? _pick(['once', 'una vez']) : _pick(['$count times', '$count veces']);
  String citedIn(String titles) => _pick(['In: $titles', 'En: $titles']);
  String get dictionary => _pick(['Dictionary', 'Diccionario']);
  String get noResults => _pick(['Nothing found.', 'No se encontró nada.']);
  String get notes => _pick(['Notes', 'Notas']);
  String noNotesFor(String verse) => _pick(['No notes for v$verse', 'No hay notas para el v. $verse']);
  String get tapVerse => _pick(['Tap a word to see what it translates, or a verse number for notes on it (an underlined number has a note of its own).', 'Toque una palabra para ver qué traduce, o un número de versículo para ver las notas (un número subrayado tiene su propia nota).']);
  String get noOriginal => _pick(["This word isn't linked to a word of the original (it may have been added to make the meaning clear).", 'Esta palabra no está enlazada con ninguna palabra del original (puede haberse añadido para aclarar el sentido).']);
  String get lemma => _pick(['Dictionary form', 'Forma de diccionario']);
  String get everyPlace => _pick(['Every place it’s translated', 'Todos los lugares donde se traduce']);
  String translatedAs(int counted, int total) => counted < total
      ? _pick(['Used $total times. In the first $counted, translated as:', 'Aparece $total veces. En las primeras $counted, se traduce como:'])
      : _pick(['Used $total times, translated as:', 'Aparece $total veces, traducida como:']);
  String results(int shown, int total) => _pick(['$shown of $total results', '$shown de $total resultados']);
  String verses(int count) => _pick(['in $count verses', 'en $count versículos']);
  String megabytes(int bytes) => '${(bytes / 1048576).toStringAsFixed(1)} MB';

  /// A book's name from its code (or the code itself, for one that isn't in the list)
  String book(String code) => _books[code]?[_column] ?? code;

  /// `JHN 3:16` → `John 3:16` (anything that doesn't start with a known book code is left as it is)
  String reference(String reference) {
    final code = reference.split(' ').first;
    return _books.containsKey(code) ? book(code) + reference.substring(code.length) : reference;
  }

  String passage(String code, int chapter) => chapter == 0 ? '${book(code)}: $introduction' : '${book(code)} $chapter';
}

const _books = <String, List<String>>{
  'FRT': ['Front matter', 'Preliminares'], 'INT': ['Introduction', 'Introducción'],
  'GEN': ['Genesis', 'Génesis'], 'EXO': ['Exodus', 'Éxodo'], 'LEV': ['Leviticus', 'Levítico'], 'NUM': ['Numbers', 'Números'], 'DEU': ['Deuteronomy', 'Deuteronomio'],
  'JOS': ['Joshua', 'Josué'], 'JDG': ['Judges', 'Jueces'], 'RUT': ['Ruth', 'Rut'], 'SA1': ['1 Samuel', '1 Samuel'], 'SA2': ['2 Samuel', '2 Samuel'],
  'KI1': ['1 Kings', '1 Reyes'], 'KI2': ['2 Kings', '2 Reyes'], 'CH1': ['1 Chronicles', '1 Crónicas'], 'CH2': ['2 Chronicles', '2 Crónicas'],
  'EZR': ['Ezra', 'Esdras'], 'NEH': ['Nehemiah', 'Nehemías'], 'EST': ['Esther', 'Ester'], 'JOB': ['Job', 'Job'], 'PSA': ['Psalms', 'Salmos'],
  'PRO': ['Proverbs', 'Proverbios'], 'ECC': ['Ecclesiastes', 'Eclesiastés'], 'SNG': ['Song of Songs', 'Cantar de los Cantares'],
  'ISA': ['Isaiah', 'Isaías'], 'JER': ['Jeremiah', 'Jeremías'], 'LAM': ['Lamentations', 'Lamentaciones'], 'EZE': ['Ezekiel', 'Ezequiel'], 'DAN': ['Daniel', 'Daniel'],
  'HOS': ['Hosea', 'Oseas'], 'JOL': ['Joel', 'Joel'], 'AMO': ['Amos', 'Amós'], 'OBA': ['Obadiah', 'Abdías'], 'JNA': ['Jonah', 'Jonás'], 'MIC': ['Micah', 'Miqueas'],
  'NAH': ['Nahum', 'Nahúm'], 'HAB': ['Habakkuk', 'Habacuc'], 'ZEP': ['Zephaniah', 'Sofonías'], 'HAG': ['Haggai', 'Hageo'], 'ZEC': ['Zechariah', 'Zacarías'],
  'MAL': ['Malachi', 'Malaquías'],
  'MAT': ['Matthew', 'Mateo'], 'MRK': ['Mark', 'Marcos'], 'LUK': ['Luke', 'Lucas'], 'JHN': ['John', 'Juan'], 'ACT': ['Acts', 'Hechos'], 'ROM': ['Romans', 'Romanos'],
  'CO1': ['1 Corinthians', '1 Corintios'], 'CO2': ['2 Corinthians', '2 Corintios'], 'GAL': ['Galatians', 'Gálatas'], 'EPH': ['Ephesians', 'Efesios'],
  'PHP': ['Philippians', 'Filipenses'], 'COL': ['Colossians', 'Colosenses'], 'TH1': ['1 Thessalonians', '1 Tesalonicenses'], 'TH2': ['2 Thessalonians', '2 Tesalonicenses'],
  'TI1': ['1 Timothy', '1 Timoteo'], 'TI2': ['2 Timothy', '2 Timoteo'], 'TIT': ['Titus', 'Tito'], 'PHM': ['Philemon', 'Filemón'], 'HEB': ['Hebrews', 'Hebreos'],
  'JAM': ['James', 'Santiago'], 'PE1': ['1 Peter', '1 Pedro'], 'PE2': ['2 Peter', '2 Pedro'], 'JN1': ['1 John', '1 Juan'], 'JN2': ['2 John', '2 Juan'],
  'JN3': ['3 John', '3 Juan'], 'JDE': ['Jude', 'Judas'], 'REV': ['Revelation', 'Apocalipsis'],
  'TOB': ['Tobit', 'Tobías'], 'JDT': ['Judith', 'Judit'], 'ESG': ['Esther (Greek)', 'Ester (griego)'], 'WIS': ['Wisdom', 'Sabiduría'], 'SIR': ['Sirach', 'Eclesiástico'],
  'BAR': ['Baruch', 'Baruc'], 'LJE': ['Letter of Jeremiah', 'Carta de Jeremías'], 'DAG': ['Daniel (Greek)', 'Daniel (griego)'], 'PAZ': ['Prayer of Azariah', 'Oración de Azarías'],
  'SUS': ['Susanna', 'Susana'], 'BEL': ['Bel and the Dragon', 'Bel y el Dragón'], 'MA1': ['1 Maccabees', '1 Macabeos'], 'MA2': ['2 Maccabees', '2 Macabeos'],
  'MA3': ['3 Maccabees', '3 Macabeos'], 'MA4': ['4 Maccabees', '4 Macabeos'], 'ES1': ['1 Esdras', '1 Esdras'], 'ES2': ['2 Esdras', '2 Esdras'],
  'MAN': ['Prayer of Manasseh', 'Oración de Manasés'], 'PS2': ['Psalm 151', 'Salmo 151'],
};
