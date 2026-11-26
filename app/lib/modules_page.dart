// Installing and removing modules.
import 'dart:convert';

import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'engine/engine.dart';
import 'strings.dart';

/// Where modules are downloaded from: Freely-Given.org for a release build, and this computer (through `adb reverse tcp:8377 tcp:8377`) for a debug one.
/// In a browser this is relative to the page's own server. Set it when building, e.g., --dart-define=MODULES=https://example.org/modules/
const modulesLocation = String.fromEnvironment('MODULES',
    defaultValue: kReleaseMode ? 'https://freely-given.org/Software/Biblelastic/modules/' : 'http://localhost:8377/build/modules/');

/// A module as the catalogue (`index.json`) lists it: its size, its SHA-256 (which changes when it does), and what may be done with it
class Listed {
  Listed(Map<String, dynamic> entry)
      : name = entry['name'] as String, bytes = entry['bytes'] as int, sha256 = entry['sha256'] as String? ?? '',
        licence = entry['licence'] as String? ?? '', copyright = entry['copyright'] as String? ?? '';
  final String name, sha256, licence, copyright;
  final int bytes;
}

class ModulesPage extends StatefulWidget {
  const ModulesPage({super.key, required this.engine});
  final Engine engine;
  @override
  State<ModulesPage> createState() => _ModulesPageState();
}

class _ModulesPageState extends State<ModulesPage> {
  final Uri location = Uri.base.resolve(modulesLocation);
  List<Listed> catalogue = [];
  Map<String, int> installed = {};
  /// The SHA-256 of each installed module, as the catalogue gave it when it was installed (remembered on the device)
  Map<String, String> hashes = {};
  Map<String, int> progress = {};
  String? problem;
  bool busy = false;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    final found = {for (final module in await widget.engine.installed()) module.name: module.bytes};
    var remembered = <String, String>{};
    try { remembered = (jsonDecode((await SharedPreferences.getInstance()).getString('moduleHashes') ?? '{}') as Map<String, dynamic>).cast<String, String>(); } catch (_) {}
    if (mounted) setState(() { installed = found; hashes = remembered; });
    if (catalogue.isNotEmpty) return;
    try {
      // (Asked for by an address of its own each time, so that no cache gives an old one)
      final response = await http.get(location.resolve('index.json?t=${DateTime.now().millisecondsSinceEpoch}'));
      if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
      final modules = (jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>)['modules'] as List<dynamic>;
      if (mounted) setState(() { catalogue = [for (final module in modules) Listed(module as Map<String, dynamic>)]; problem = null; });
    } catch (error) {
      if (mounted) setState(() => problem = '$error');
    }
  }

  Future<void> install(List<Listed> modules) async {
    setState(() { busy = true; problem = null; });
    try {
      for (final module in modules) {
        // Asked for by its SHA-256 too, so that a changed module has a new address, which no cache (e.g., Cloudflare's) can have an old copy of
        final version = module.sha256.isEmpty ? '' : '?v=${module.sha256.substring(0, 16)}';
        await widget.engine.install(module.name, location.resolve('${module.name}.blm$version'), (written) { if (mounted) setState(() => progress[module.name] = written); });
        progress.remove(module.name);
        if (module.sha256.isNotEmpty) await remember({...hashes, module.name: module.sha256});
        await refresh();
      }
    } catch (error) {
      if (mounted) setState(() => problem = '$error');
    }
    if (mounted) setState(() { busy = false; progress.clear(); });
  }

  Future<void> remember(Map<String, String> newHashes) async {
    hashes = newHashes;
    try { await (await SharedPreferences.getInstance()).setString('moduleHashes', jsonEncode(newHashes)); } catch (_) {}
  }

  /// Whether an installed module differs from the catalogue's: by its SHA-256 if that was remembered when it was installed, or else by its size
  bool changed(Listed module) {
    final known = hashes[module.name];
    return known != null && module.sha256.isNotEmpty ? known != module.sha256 : installed[module.name] != module.bytes;
  }

  Future<void> removeAll() async {
    setState(() => busy = true);
    await widget.engine.removeAll();
    await remember({});
    await refresh();
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final names = {...catalogue.map((module) => module.name), ...installed.keys}.toList();
    final missing = catalogue.where((module) => !installed.containsKey(module.name)).toList();
    final updates = catalogue.where((module) => installed.containsKey(module.name) && changed(module)).toList();
    return Scaffold(
      appBar: AppBar(title: Text(strings.modules)),
      body: SafeArea(child: ListView(padding: const EdgeInsets.all(16), children: [
        Wrap(spacing: 12, runSpacing: 8, children: [
          FilledButton(onPressed: busy || missing.isEmpty && updates.isEmpty ? null : () => install([...updates, ...missing]),
              child: Text(updates.isEmpty ? strings.installAll : strings.updateAll)),
          OutlinedButton(onPressed: busy || installed.isEmpty ? null : removeAll, child: Text(strings.removeAll)),
        ]),
        const SizedBox(height: 8),
        Text('${strings.modulesFrom} $location', style: theme.textTheme.bodySmall),
        if (problem != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(catalogue.isEmpty ? '${strings.noCatalogue} ($problem)' : problem!, style: TextStyle(color: theme.colorScheme.error))),
        const SizedBox(height: 8),
        for (final name in names) () {
          final listed = catalogue.where((module) => module.name == name).firstOrNull;
          final size = installed[name] ?? listed?.bytes ?? 0;
          final written = progress[name];
          final isInstalled = installed.containsKey(name);
          final hasUpdate = isInstalled && listed != null && changed(listed);
          final status = !isInstalled ? strings.notInstalled : hasUpdate ? strings.updateAvailable : strings.installed;
          return ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: Text(name),
            subtitle: written != null && listed != null ? LinearProgressIndicator(value: written / listed.bytes)
                : Text([strings.megabytes(size), if (listed != null && listed.licence.isNotEmpty) listed.licence, status].join(' · ')),
            trailing: isInstalled && !hasUpdate ? Icon(Icons.check, color: theme.colorScheme.primary)
                : IconButton(tooltip: hasUpdate ? strings.update : null, icon: Icon(hasUpdate ? Icons.update : Icons.download), onPressed: busy || listed == null ? null : () => install([listed])),
          );
        }(),
      ])),
    );
  }
}
