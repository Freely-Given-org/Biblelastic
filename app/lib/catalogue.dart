// The modules that can be downloaded (from the catalogue, `index.json`), and what's installed, grouped as people choose them:
// a language's starter set, search by meaning in a language, and each work (with its layers, its alignments, and, with search by meaning, its passages' vectors).
import 'dart:convert';

import 'package:flutter/foundation.dart' show ChangeNotifier, kReleaseMode;
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'engine/engine.dart';

/// Where modules are downloaded from: Freely-Given.org for a release build, and this computer (through `adb reverse tcp:8377 tcp:8377`) for a debug one.
/// In a browser this is relative to the page's own server. Set it when building, e.g., --dart-define=MODULES=https://example.org/modules/
const modulesLocation = String.fromEnvironment('MODULES',
    defaultValue: kReleaseMode ? 'https://Freely-Given.org/Software/Biblelastic/modules/' : 'http://localhost:8377/build/modules/');

/// The languages of the original texts, which every starter set has (for what a word translates)
const originalLanguages = {'grc', 'hbo', 'arc'};

/// A module as the catalogue lists it: its size, its SHA-256 (which changes when it does), what it is, and what may be done with it
class Listed {
  Listed(Map<String, dynamic> entry)
      : name = entry['name'] as String, bytes = entry['bytes'] as int, sha256 = entry['sha256'] as String? ?? '',
        licence = entry['licence'] as String? ?? '', copyright = entry['copyright'] as String? ?? '',
        kind = entry['kind'] as String? ?? '', work = entry['work'] as String? ?? '', title = entry['title'] as String? ?? '',
        language = entry['language'] as String? ?? '',
        // An alignment (e.g., `OET-RV--UHB`) goes with the translation whose words it links
        edition = entry['edition'] as String? ?? ((entry['name'] as String).contains('--') ? (entry['name'] as String).split('--').first : '');
  final String name, sha256, licence, copyright, kind, work, title, language, edition;
  final int bytes;
}

/// A work as it's chosen: its text and layers and the alignments of its words, and its passages' vectors (for search by meaning, if that's installed)
class Work {
  Work(this.edition);
  final String edition;
  final List<Listed> modules = [];
  Listed? vectors;
  Listed get text => modules.firstWhere((module) => module.kind == 'text', orElse: () => modules.first);
  String get title => text.title.isEmpty ? edition : text.title;
  /// `scripture`, `commentary`, `dictionary`, or `book`
  String get kind => text.work;
  String get language => text.language;
  String get licence => text.licence;
}

/// Everything that can be downloaded, and what's installed: one for the app, shared by the pages that offer downloads
class Catalogue extends ChangeNotifier {
  Catalogue._(this.engine);
  static Catalogue? _one;
  factory Catalogue.of(Engine engine) => _one ??= Catalogue._(engine);

  final Engine engine;
  final Uri location = Uri.base.resolve(modulesLocation);
  List<Listed> modules = [];
  Map<String, int> installed = {};
  /// The SHA-256 of each installed module, as the catalogue gave it when it was installed (remembered on the device)
  Map<String, String> hashes = {};
  /// How much of each module that's downloading has been stored
  final Map<String, int> progress = {};
  String? problem;
  bool busy = false;
  /// For the downloads under way: how many bytes in all, and how many of them are in the modules already stored
  int _jobBytes = 0, _jobDone = 0;
  /// How far the downloads under way have got (0–1), if any are
  double? get fraction => !busy || _jobBytes == 0 ? null : (_jobDone + progress.values.fold(0, (total, written) => total + written)) / _jobBytes;

  /// What's installed, and (if it hasn't been fetched yet, or `fetch` is set) the catalogue
  Future<void> refresh({bool fetch = false}) async {
    installed = {for (final module in await engine.installed()) module.name: module.bytes};
    try { hashes = (jsonDecode((await SharedPreferences.getInstance()).getString('moduleHashes') ?? '{}') as Map<String, dynamic>).cast<String, String>(); } catch (_) {}
    notifyListeners();
    if (modules.isNotEmpty && !fetch) return;
    try {
      // (Asked for by an address of its own each time, so that no cache gives an old one)
      final response = await http.get(location.resolve('index.json?t=${DateTime.now().millisecondsSinceEpoch}'));
      if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
      final entries = (jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>)['modules'] as List<dynamic>;
      modules = [for (final entry in entries) Listed(entry as Map<String, dynamic>)];
      problem = null;
    } catch (error) {
      problem = '$error';
    }
    notifyListeners();
  }

  bool isInstalled(Listed module) => installed.containsKey(module.name);

  /// Whether an installed module differs from the catalogue's: by its SHA-256 if that was remembered when it was installed, or else by its size
  bool changed(Listed module) {
    final known = hashes[module.name];
    return isInstalled(module) && (known != null && module.sha256.isNotEmpty ? known != module.sha256 : installed[module.name] != module.bytes);
  }

  /// Those of these modules that aren't installed, or have changed
  List<Listed> wanted(Iterable<Listed> these) => these.where((module) => !isInstalled(module) || changed(module)).toList();

  Future<void> install(Iterable<Listed> these) async {
    final list = wanted(these);
    if (list.isEmpty) return;
    busy = true;
    problem = null;
    _jobBytes = bytes(list);
    _jobDone = 0;
    notifyListeners();
    try {
      for (final module in list) {
        // Asked for by its SHA-256 too, so that a changed module has a new address, which no cache (e.g., Cloudflare's) can have an old copy of
        final version = module.sha256.isEmpty ? '' : '?v=${module.sha256.substring(0, 16)}';
        await engine.install(module.name, location.resolve('${module.name}.blm$version'), (written) { progress[module.name] = written; notifyListeners(); });
        progress.remove(module.name);
        if (module.sha256.isNotEmpty) await _remember({...hashes, module.name: module.sha256});
        installed[module.name] = module.bytes;
        _jobDone += module.bytes;
        notifyListeners();
      }
    } catch (error) {
      problem = '$error';
    }
    busy = false;
    progress.clear();
    await refresh();
  }

  Future<void> remove(Iterable<String> names) async {
    final list = names.where(installed.containsKey).toList();
    if (list.isEmpty) return;
    busy = true;
    notifyListeners();
    await engine.remove(list);
    await _remember({...hashes}..removeWhere((name, _) => list.contains(name)));
    busy = false;
    await refresh();
  }

  Future<void> removeAll() async {
    busy = true;
    notifyListeners();
    await engine.removeAll();
    await _remember({});
    busy = false;
    await refresh();
  }

  Future<void> _remember(Map<String, String> newHashes) async {
    hashes = newHashes;
    try { await (await SharedPreferences.getInstance()).setString('moduleHashes', jsonEncode(newHashes)); } catch (_) {}
  }

  /// The works, by edition, in the catalogue's order
  Map<String, Work> get works {
    final found = <String, Work>{};
    for (final module in modules) {
      if (module.edition.isEmpty || module.kind == 'model') continue;
      final work = found.putIfAbsent(module.edition, () => Work(module.edition));
      if (module.kind == 'vectors') { work.vectors = module; } else { work.modules.add(module); }
    }
    return found..removeWhere((_, work) => work.modules.isEmpty);
  }

  /// The languages that there are Bibles in (not the original languages), each of which has a starter set
  List<String> get languages => {for (final work in works.values) if (work.kind == 'scripture' && !originalLanguages.contains(work.language)) work.language}.toList();

  /// A language's starter set: its Bibles, commentaries, and dictionaries (not the books, which can be added one by one), the original texts
  /// (for what each word translates), and its thesaurus (for searching by subject). Search by meaning is separate, as its model is big.
  List<Listed> starter(String language) => [
    for (final work in works.values)
      if (work.kind != 'book' && (work.language == language || work.kind == 'scripture' && originalLanguages.contains(work.language))) ...work.modules,
    ...modules.where((module) => module.kind == 'thesaurus' && module.language == language),
  ];

  /// The model for search by meaning in a language
  Listed? model(String language) => modules.where((module) => module.kind == 'model' && module.language == language).firstOrNull;

  bool meaningInstalled(String language) => model(language) != null && isInstalled(model(language)!);

  /// Search by meaning in a language: its model, and the vectors of the works in that language that are installed (or are in `also`)
  List<Listed> meaning(String language, {Iterable<Listed> also = const []}) {
    final model = this.model(language);
    if (model == null) return [];
    final names = {...installed.keys, ...also.map((module) => module.name)};
    return [model, for (final work in works.values) if (work.language == language && work.vectors != null && names.contains(work.text.name)) work.vectors!];
  }

  /// A work's modules, with its vectors if search by meaning is installed in its language
  List<Listed> ofWork(Work work) => [...work.modules, if (work.vectors != null && meaningInstalled(work.language)) work.vectors!];

  int bytes(Iterable<Listed> these) => these.fold(0, (total, module) => total + module.bytes);
  /// How much would be downloaded to have all of these
  int toDownload(Iterable<Listed> these) => bytes(wanted(these));
  bool allInstalled(Iterable<Listed> these) => these.isNotEmpty && these.every(isInstalled);
  bool anyChanged(Iterable<Listed> these) => these.any(changed);
}
