// Installing and removing modules.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'engine/engine.dart';
import 'strings.dart';

/// Where modules are downloaded from. In a browser this is relative to the page's own server.
/// Set it when building, e.g., --dart-define=MODULES=https://example.org/modules/
const modulesLocation = String.fromEnvironment('MODULES', defaultValue: 'http://localhost:8377/build/modules/');

class ModulesPage extends StatefulWidget {
  const ModulesPage({super.key, required this.engine});
  final Engine engine;
  @override
  State<ModulesPage> createState() => _ModulesPageState();
}

class _ModulesPageState extends State<ModulesPage> {
  final Uri location = Uri.base.resolve(modulesLocation);
  List<ModuleInfo> catalogue = [];
  Map<String, int> installed = {};
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
    if (mounted) setState(() => installed = found);
    if (catalogue.isNotEmpty) return;
    try {
      final response = await http.get(location.resolve('index.json'));
      if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
      final modules = (jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>)['modules'] as List<dynamic>;
      if (mounted) setState(() { catalogue = [for (final module in modules) ModuleInfo(module['name'] as String, module['bytes'] as int)]; problem = null; });
    } catch (error) {
      if (mounted) setState(() => problem = '$error');
    }
  }

  Future<void> install(List<ModuleInfo> modules) async {
    setState(() { busy = true; problem = null; });
    try {
      for (final module in modules) {
        await widget.engine.install(module.name, location.resolve('${module.name}.blm'), (written) { if (mounted) setState(() => progress[module.name] = written); });
        progress.remove(module.name);
        await refresh();
      }
    } catch (error) {
      if (mounted) setState(() => problem = '$error');
    }
    if (mounted) setState(() { busy = false; progress.clear(); });
  }

  Future<void> removeAll() async {
    setState(() => busy = true);
    await widget.engine.removeAll();
    await refresh();
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final names = {...catalogue.map((module) => module.name), ...installed.keys}.toList();
    final missing = catalogue.where((module) => installed[module.name] != module.bytes).toList();
    return Scaffold(
      appBar: AppBar(title: Text(strings.modules)),
      body: SafeArea(child: ListView(padding: const EdgeInsets.all(16), children: [
        Wrap(spacing: 12, runSpacing: 8, children: [
          FilledButton(onPressed: busy || missing.isEmpty ? null : () => install(missing), child: Text(strings.installAll)),
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
          final isInstalled = installed.containsKey(name) && (listed == null || installed[name] == listed.bytes);
          return ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: Text(name),
            subtitle: written != null && listed != null ? LinearProgressIndicator(value: written / listed.bytes) : Text('${strings.megabytes(size)} · ${isInstalled ? strings.installed : strings.notInstalled}'),
            trailing: isInstalled ? Icon(Icons.check, color: theme.colorScheme.primary)
                : IconButton(icon: const Icon(Icons.download), onPressed: busy || listed == null ? null : () => install([listed])),
          );
        }(),
      ])),
    );
  }
}
