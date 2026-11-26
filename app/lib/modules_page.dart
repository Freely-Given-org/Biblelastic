// Installing and removing modules: a language's starter set, search by meaning, and each work, as they're chosen
// (with every module listed one by one at the end, for anyone who wants that).
import 'package:flutter/material.dart';

import 'catalogue.dart';
import 'engine/engine.dart';
import 'strings.dart';

class ModulesPage extends StatefulWidget {
  const ModulesPage({super.key, required this.engine});
  final Engine engine;
  @override
  State<ModulesPage> createState() => _ModulesPageState();
}

class _ModulesPageState extends State<ModulesPage> {
  late final Catalogue catalogue = Catalogue.of(widget.engine);

  @override
  void initState() {
    super.initState();
    catalogue.refresh(fetch: true);
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(listenable: catalogue, builder: (context, _) => page(context));

  Widget page(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final busy = catalogue.busy;
    // The phone's language first
    final mine = strings.languageCode;
    final languages = catalogue.languages..sort((a, b) => (a == mine ? 0 : 1) - (b == mine ? 0 : 1));
    final works = catalogue.works.values.toList()
      ..sort((a, b) => a.language == b.language ? a.title.compareTo(b.title) : a.language == mine ? -1 : b.language == mine ? 1 : a.language.compareTo(b.language));
    Widget heading(String text) => Padding(padding: const EdgeInsets.only(top: 24, bottom: 4), child: Text(text, style: theme.textTheme.titleSmall!.copyWith(color: theme.colorScheme.primary)));

    /// A set of modules that's installed together: its button says how much it would download
    Widget set(String title, String description, List<Listed> modules, {List<Listed> remove = const []}) {
      final complete = catalogue.allInstalled(modules) && !catalogue.anyChanged(modules);
      final size = catalogue.toDownload(modules);
      return Card(margin: const EdgeInsets.only(top: 8), child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: theme.textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(description, style: theme.textTheme.bodySmall),
        const SizedBox(height: 12),
        Wrap(spacing: 12, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          if (complete) ...[Icon(Icons.check, color: theme.colorScheme.primary), Text(strings.installed)]
          else FilledButton(onPressed: busy ? null : () => catalogue.install(modules),
              child: Text('${catalogue.anyChanged(modules) ? strings.update : strings.install} (${strings.megabytes(size)})')),
          if (remove.any(catalogue.isInstalled)) TextButton(onPressed: busy ? null : () => catalogue.remove(remove.map((module) => module.name)), child: Text(strings.remove)),
        ]),
      ])));
    }

    Widget work(Work work) {
      final modules = catalogue.ofWork(work);
      final isInstalled = catalogue.isInstalled(work.text);
      final hasUpdate = catalogue.anyChanged(modules) || isInstalled && catalogue.wanted(modules).isNotEmpty;
      final downloading = modules.any((module) => catalogue.progress.containsKey(module.name));
      return ListTile(
        contentPadding: EdgeInsets.zero,
        dense: true,
        title: Text(work.title),
        subtitle: Text([strings.languageName(work.language), strings.megabytes(catalogue.bytes(modules)), if (work.licence.isNotEmpty) work.licence,
                        if (downloading) strings.downloading else if (hasUpdate) strings.updateAvailable else if (isInstalled) strings.installed].join(' · ')),
        trailing: !isInstalled || hasUpdate
            ? IconButton(tooltip: hasUpdate ? strings.update : strings.install, icon: Icon(hasUpdate ? Icons.update : Icons.download),
                onPressed: busy ? null : () => catalogue.install(modules))
            : IconButton(tooltip: strings.remove, icon: const Icon(Icons.delete_outline),
                onPressed: busy ? null : () => catalogue.remove([...work.modules, if (work.vectors != null) work.vectors!].map((module) => module.name))),
      );
    }

    final kinds = {'scripture': strings.bibles, 'commentary': strings.commentaries, 'dictionary': strings.dictionaries, 'book': strings.books};
    return Scaffold(
      appBar: AppBar(title: Text(strings.modules), bottom: catalogue.busy
          ? PreferredSize(preferredSize: const Size.fromHeight(4), child: LinearProgressIndicator(value: catalogue.fraction)) : null),
      body: SafeArea(child: RefreshIndicator(onRefresh: () => catalogue.refresh(fetch: true), child: ListView(padding: const EdgeInsets.all(16), children: [
        if (catalogue.problem != null) Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(catalogue.modules.isEmpty ? '${strings.noCatalogue} (${catalogue.problem})' : catalogue.problem!, style: TextStyle(color: theme.colorScheme.error))),
        if (catalogue.modules.isEmpty && catalogue.problem == null) const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator())),
        if (languages.isNotEmpty) Text(strings.startWith, style: theme.textTheme.titleSmall!.copyWith(color: theme.colorScheme.primary)),
        for (final language in languages)
          set(strings.languageName(language), strings.starterDescription,
              [...catalogue.starter(language), if (catalogue.meaningInstalled(language)) ...catalogue.meaning(language, also: catalogue.starter(language))]),
        // (Only once there's something in that language to search)
        for (final language in languages)
          if (catalogue.model(language) != null && works.any((work) => work.language == language && catalogue.isInstalled(work.text)))
            set('${strings.searchByMeaning}: ${strings.languageName(language)}', strings.meaningDescription,
                catalogue.meaning(language), remove: [catalogue.model(language)!, for (final work in works) if (work.language == language && work.vectors != null) work.vectors!]),
        for (final MapEntry(key: kind, value: title) in kinds.entries)
          if (works.any((work) => work.kind == kind)) ...[heading(title), for (final each in works.where((work) => work.kind == kind)) work(each)],
        const SizedBox(height: 16),
        ExpansionTile(tilePadding: EdgeInsets.zero, title: Text(strings.eachModule), children: [
          Align(alignment: Alignment.centerLeft, child: Wrap(spacing: 12, runSpacing: 8, children: [
            FilledButton(onPressed: busy || catalogue.wanted(catalogue.modules).isEmpty ? null : () => catalogue.install(catalogue.modules),
                child: Text(catalogue.anyChanged(catalogue.modules) ? strings.updateAll : strings.installAll)),
            OutlinedButton(onPressed: busy || catalogue.installed.isEmpty ? null : catalogue.removeAll, child: Text(strings.removeAll)),
          ])),
          for (final name in {...catalogue.modules.map((module) => module.name), ...catalogue.installed.keys}) () {
            final listed = catalogue.modules.where((module) => module.name == name).firstOrNull;
            final isInstalled = catalogue.installed.containsKey(name);
            final hasUpdate = listed != null && catalogue.changed(listed);
            final written = catalogue.progress[name];
            return ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(name),
              subtitle: written != null && listed != null ? LinearProgressIndicator(value: written / listed.bytes)
                  : Text([strings.megabytes(catalogue.installed[name] ?? listed?.bytes ?? 0), if (listed != null && listed.licence.isNotEmpty) listed.licence,
                          !isInstalled ? strings.notInstalled : hasUpdate ? strings.updateAvailable : strings.installed].join(' · ')),
              trailing: isInstalled && !hasUpdate ? Icon(Icons.check, color: theme.colorScheme.primary)
                  : IconButton(tooltip: hasUpdate ? strings.update : null, icon: Icon(hasUpdate ? Icons.update : Icons.download),
                      onPressed: busy || listed == null ? null : () => catalogue.install([listed])),
            );
          }(),
        ]),
        // As it's written (Freely-Given.org), not as parsed (which lowercases the host), unless it's relative to the page
        Text('${strings.modulesFrom} ${Uri.parse(modulesLocation).hasScheme ? modulesLocation : catalogue.location}', style: theme.textTheme.bodySmall),
      ]))),
    );
  }
}
