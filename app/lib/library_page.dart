// The installed commentaries, books, and dictionaries, and the contents of each.
import 'package:flutter/material.dart';

import 'article_page.dart';
import 'catalogue.dart';
import 'engine/engine.dart';
import 'strings.dart';
import 'works.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key, required this.engine});
  final Engine engine;
  @override
  State<LibraryPage> createState() => _LibraryPageState();

  // By title, as a library shelves them: ‘The Pilgrim’s Progress’ under P
  static String _sortKey(Map work) => _shelved(work['title'] as String);
  static String _shelved(String title) => title.toLowerCase().replaceFirst(RegExp(r'^(the|an?) '), '');
}

class _LibraryPageState extends State<LibraryPage> {
  late final Catalogue catalogue = Catalogue.of(widget.engine);

  @override
  void initState() {
    super.initState();
    catalogue.refresh(); // For the works that can be downloaded, if it can be fetched
  }

  Future<void> download(Work work) async {
    await catalogue.install(catalogue.ofWork(work));
    await loadWorks(widget.engine);
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(listenable: catalogue, builder: (context, _) => page(context));

  Widget page(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final kinds = {'book': strings.books, 'commentary': strings.commentaries, 'dictionary': strings.dictionaries};
    // The works that aren't installed (in the languages of the installed Bibles first), to download one by one
    final mine = {for (final bible in readableBibles()) works[bible]?['language'] as String? ?? ''}..add(strings.languageCode);
    final more = catalogue.works.values.where((work) => kinds.containsKey(work.kind) && !works.containsKey(work.edition)).toList()
      ..sort((a, b) => mine.contains(a.language) != mine.contains(b.language) ? (mine.contains(a.language) ? -1 : 1)
          : a.kind != b.kind ? a.kind.compareTo(b.kind) : LibraryPage._shelved(a.title).compareTo(LibraryPage._shelved(b.title)));
    Widget heading(String text) => Padding(padding: const EdgeInsets.only(top: 16, bottom: 4), child: Text(text, style: theme.textTheme.titleSmall!.copyWith(color: theme.colorScheme.primary)));
    return Scaffold(
      appBar: AppBar(title: Text(strings.library), bottom: catalogue.busy
          ? PreferredSize(preferredSize: const Size.fromHeight(4), child: LinearProgressIndicator(value: catalogue.fraction)) : null),
      body: SafeArea(child: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
        ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.copyright_outlined), title: Text(strings.aboutWorks),
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => const AboutWorksPage()))),
        for (final MapEntry(key: kind, value: title) in kinds.entries) ...[
          if (works.values.any((work) => work['work'] == kind)) heading(title),
          for (final work in works.values.where((work) => work['work'] == kind).toList()..sort((a, b) => LibraryPage._sortKey(a).compareTo(LibraryPage._sortKey(b))))
            ListTile(contentPadding: EdgeInsets.zero, title: Text(work['title'] as String), subtitle: Text(work['edition'] as String),
                onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => ContentsPage(engine: widget.engine, edition: work['edition'] as String)))),
        ],
        if (more.isNotEmpty) heading(strings.toDownload),
        for (final work in more)
          ListTile(contentPadding: EdgeInsets.zero, title: Text(work.title),
              subtitle: Text([strings.languageName(work.language), strings.megabytes(catalogue.bytes(catalogue.ofWork(work))), if (work.licence.isNotEmpty) work.licence].join(' · ')),
              trailing: IconButton(tooltip: strings.install, icon: const Icon(Icons.download), onPressed: catalogue.busy ? null : () => download(work))),
      ])),
    );
  }
}

/// Every installed work (Bibles, books, commentaries, and dictionaries) and model, with its copyright, licence, and attribution
class AboutWorksPage extends StatelessWidget {
  const AboutWorksPage({super.key});

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final all = [...works.values.toList()..sort((a, b) => LibraryPage._sortKey(a).compareTo(LibraryPage._sortKey(b))), ...models];
    return Scaffold(
      appBar: AppBar(title: Text(strings.aboutWorks)),
      body: SafeArea(child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
        itemCount: all.length + 1,
        itemBuilder: (context, index) => index == 0
            // The app itself: its version, and its licence and source code
            ? Padding(padding: const EdgeInsets.only(top: 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${strings.appName} $appVersion', style: theme.textTheme.titleSmall),
                const SizedBox(height: 4),
                SelectableText(strings.aboutApp, style: theme.textTheme.bodySmall),
              ]))
            : Padding(padding: const EdgeInsets.only(top: 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(all[index - 1]['title'] as String? ?? all[index - 1]['edition'] as String, style: theme.textTheme.titleSmall),
          Text(all[index - 1]['edition'] as String, style: theme.textTheme.labelSmall!.copyWith(color: theme.colorScheme.outline)),
          const SizedBox(height: 4),
          Rights(module: all[index - 1]),
        ])),
      )),
    );
  }
}

/// The entries of one work, e.g., a book's chapters
class ContentsPage extends StatelessWidget {
  const ContentsPage({super.key, required this.engine, required this.edition});
  final Engine engine;
  final String edition;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(titleOf(edition))),
      body: SafeArea(child: FutureBuilder<Map<String, dynamic>>(
        future: engine.request({'command': 'toc', 'edition': edition}),
        builder: (context, snapshot) {
          if (snapshot.hasError) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text('${snapshot.error}')));
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final entries = snapshot.data!['entries'] as List<dynamic>;
          // A dictionary can have thousands of entries: they're laid out only as they're scrolled to
          return ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
            itemCount: entries.length + 1,
            itemBuilder: (context, index) => index == entries.length
                ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    Disclaimers(editions: [edition]),
                    if (works[edition] != null) Padding(padding: const EdgeInsets.only(top: 16), child: Rights(module: works[edition]!)),
                  ])
                : ListTile(contentPadding: EdgeInsets.zero, dense: true, title: Text(entries[index]['title'] as String? ?? ''),
                    subtitle: Text(entries[index]['locator'] as String),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) =>
                        ArticlePage(engine: engine, locator: entries[index]['locator'] as String, edition: edition)))),
          );
        },
      )),
    );
  }
}
