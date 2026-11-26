// The installed commentaries, books, and dictionaries, and the contents of each.
import 'package:flutter/material.dart';

import 'article_page.dart';
import 'engine/engine.dart';
import 'strings.dart';
import 'works.dart';

class LibraryPage extends StatelessWidget {
  const LibraryPage({super.key, required this.engine});
  final Engine engine;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final kinds = {'book': strings.books, 'commentary': strings.commentaries, 'dictionary': strings.dictionaries};
    return Scaffold(
      appBar: AppBar(title: Text(strings.library)),
      body: SafeArea(child: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
        ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.copyright_outlined), title: Text(strings.aboutWorks),
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => const AboutWorksPage()))),
        for (final MapEntry(key: kind, value: heading) in kinds.entries) ...[
          if (works.values.any((work) => work['work'] == kind)) Padding(padding: const EdgeInsets.only(top: 16, bottom: 4), child: Text(heading, style: theme.textTheme.titleSmall!.copyWith(color: theme.colorScheme.primary))),
          for (final work in works.values.where((work) => work['work'] == kind).toList()..sort((a, b) => _sortKey(a).compareTo(_sortKey(b))))
            ListTile(contentPadding: EdgeInsets.zero, title: Text(work['title'] as String), subtitle: Text(work['edition'] as String),
                onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => ContentsPage(engine: engine, edition: work['edition'] as String)))),
        ],
      ])),
    );
  }

  // By title, as a library shelves them: ‘The Pilgrim’s Progress’ under P
  static String _sortKey(Map work) => (work['title'] as String).toLowerCase().replaceFirst(RegExp(r'^(the|an?) '), '');
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
        itemCount: all.length,
        itemBuilder: (context, index) => Padding(padding: const EdgeInsets.only(top: 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(all[index]['title'] as String? ?? all[index]['edition'] as String, style: theme.textTheme.titleSmall),
          Text(all[index]['edition'] as String, style: theme.textTheme.labelSmall!.copyWith(color: theme.colorScheme.outline)),
          const SizedBox(height: 4),
          Rights(module: all[index]),
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
