// Whole articles (of a dictionary, a handbook, etc.), and the words that share a meaning.
import 'package:flutter/material.dart';

import 'engine/engine.dart';
import 'strings.dart';
import 'works.dart';
import 'word_sheet.dart' show LemmaPage;

/// One whole entry of a commentary, dictionary, or handbook, e.g., `Fauna 2.10`. It can lead on to the entries it links to.
class ArticlePage extends StatelessWidget {
  const ArticlePage({super.key, required this.engine, required this.locator, this.edition});
  final Engine engine;
  final String locator;
  /// The work that it's in (any installed one has it, if this isn't given)
  final String? edition;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: FutureBuilder<Map<String, dynamic>>(future: _article, builder: (context, snapshot) => Text(snapshot.data?['title'] as String? ?? ''))),
      body: SafeArea(child: FutureBuilder<Map<String, dynamic>>(
        future: _article,
        builder: (context, snapshot) {
          if (snapshot.hasError) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text('${snapshot.error}')));
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final article = snapshot.data!;
          final see = article['see'] as List<dynamic>;
          return SelectionArea(child: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
            Text('${titleOf(article['edition'] as String)} · ${article['locator']}', style: theme.textTheme.labelMedium!.copyWith(color: theme.colorScheme.primary)),
            for (final paragraph in article['paragraphs'] as List<dynamic>)
              if ((paragraph['text'] as String).isNotEmpty) switch (paragraph['style'] as String) {
                'h1' => Padding(padding: const EdgeInsets.only(top: 8), child: Text(paragraph['text'] as String, style: theme.textTheme.titleLarge)),
                'h2' || 'h3' => Padding(padding: const EdgeInsets.only(top: 16), child: Text(paragraph['text'] as String, style: theme.textTheme.titleSmall!.copyWith(fontWeight: FontWeight.bold))),
                'caption' || 'lemma' || 'note' => Padding(padding: const EdgeInsets.only(top: 4), child: Text(paragraph['text'] as String, style: theme.textTheme.bodySmall)),
                'li' => Padding(padding: const EdgeInsets.only(top: 4, left: 12), child: Text('•  ${paragraph['text']}', style: theme.textTheme.bodyLarge!.copyWith(height: 1.45))),
                _ => Padding(padding: const EdgeInsets.only(top: 8), child: Text(paragraph['text'] as String, style: theme.textTheme.bodyLarge!.copyWith(height: 1.45))),
              },
            if (see.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 20), child: Text(strings.seeAlso, style: theme.textTheme.titleSmall)),
            Disclaimers(editions: [article['edition'] as String]),
            // On through the work, e.g., to the next chapter of a book
            Padding(padding: const EdgeInsets.only(top: 16), child: Row(children: [
              if (article['previous'] case final String previous) TextButton.icon(icon: const Icon(Icons.chevron_left), label: Text(strings.previous),
                  onPressed: () => Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (context) => ArticlePage(engine: engine, locator: previous, edition: article['edition'] as String)))),
              const Spacer(),
              if (article['next'] case final String next) TextButton.icon(icon: const Icon(Icons.chevron_right), label: Text(strings.next),
                  onPressed: () => Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (context) => ArticlePage(engine: engine, locator: next, edition: article['edition'] as String)))),
            ])),
            for (final link in see)
              ListTile(contentPadding: EdgeInsets.zero, dense: true, leading: const Icon(Icons.arrow_forward, size: 18), title: Text(link['title'] as String),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => ArticlePage(engine: engine, locator: link['locator'] as String, edition: article['edition'] as String)))),
          ]));
        },
      )),
    );
  }

  Future<Map<String, dynamic>> get _article => _cache[(edition, locator)] ??= engine.request({'command': 'article', 'locator': locator, 'edition': ?edition});
  static final Map<(String?, String), Future<Map<String, dynamic>>> _cache = {};
}

/// The words of an original-language edition that have a meaning in a semantic domain. It closes with a reference, if one was chosen.
class DomainPage extends StatelessWidget {
  const DomainPage({super.key, required this.engine, required this.translation, required this.original, required this.domain});
  final Engine engine;
  /// The translation to list verses of, when a word is chosen
  final String translation;
  final String original, domain;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(domain.split(' > ').last, maxLines: 2, style: theme.textTheme.titleMedium)),
      body: SafeArea(child: FutureBuilder<Map<String, dynamic>>(
        future: engine.request({'command': 'domain', 'original': original, 'domain': domain, 'limit': '200'}),
        builder: (context, snapshot) {
          if (snapshot.hasError) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text('${snapshot.error}')));
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final words = snapshot.data!['words'] as List<dynamic>;
          return ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
            Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Text('${strings.domainWords(snapshot.data!['total'] as int)}\n$domain', style: theme.textTheme.bodySmall)),
            for (final word in words)
              ListTile(contentPadding: EdgeInsets.zero,
                  title: Text('${word['lemma']}  ${word['transliteration']}'),
                  subtitle: Text('‘${word['gloss']}’ · ${strings.timesHere(word['count'] as int)}'),
                  onTap: () async {
                    final reference = await Navigator.of(context).push(MaterialPageRoute<String>(builder: (context) =>
                        LemmaPage(engine: engine, edition: translation, original: original, lemma: word['lemma'] as String, transliteration: word['transliteration'] as String)));
                    if (reference != null && context.mounted) Navigator.of(context).pop(reference);
                  }),
          ]);
        },
      )),
    );
  }
}
