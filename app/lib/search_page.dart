// Searching: a subject (what the Scriptures and the commentators say about it), words together in a sentence,
// the original-language terms behind words, and dictionary entries.
import 'package:flutter/material.dart';

import 'article_page.dart';
import 'engine/engine.dart';
import 'main.dart' show edition;
import 'strings.dart';

enum SearchKind { topic, together, terms, dictionary }

class SearchPage extends StatefulWidget {
  const SearchPage({super.key, required this.engine});
  final Engine engine;
  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final TextEditingController words = TextEditingController();
  SearchKind kind = SearchKind.topic;
  Map<String, dynamic>? response;
  String? problem;

  @override
  void dispose() {
    words.dispose();
    super.dispose();
  }

  Future<void> run() async {
    final text = words.text.trim();
    if (text.isEmpty) return;
    final fields = switch (kind) {
      SearchKind.topic => {'command': 'topic', 'edition': edition, 'words': text, 'limit': '8', 'length': '360'},
      SearchKind.together => {'command': 'find', 'edition': edition, 'words': text, 'within': 'sentence', 'limit': '50'},
      SearchKind.terms => {'command': 'terms', 'edition': edition, 'words': text, 'limit': '30'},
      SearchKind.dictionary => {'command': 'entry', 'words': text, 'limit': '20', 'length': '600'},
    };
    try {
      final answer = await widget.engine.request(fields);
      setState(() { response = answer; problem = null; });
    } catch (error) {
      setState(() { response = null; problem = '$error'; });
    }
  }

  /// Go back to the reader, to show a reference like `JHN 3:16` in its section
  void open(String reference) {
    if (RegExp(r'^\w{3} \d+:\d+').hasMatch(reference)) Navigator.of(context).pop(reference);
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final answer = response;
    final examples = (answer?['examples'] as List<dynamic>?) ?? const [];
    final terms = (answer?['terms'] as List<dynamic>?) ?? const [];
    final entries = (answer?['entries'] as List<dynamic>?) ?? const [];
    final shown = examples.length + terms.length + entries.length;
    final isTopic = answer != null && answer['passages'] != null;
    List<dynamic> list(String name) => (answer?[name] as List<dynamic>?) ?? const [];
    Widget heading(String text) => Padding(padding: const EdgeInsets.only(top: 20, bottom: 4), child: Text(text, style: theme.textTheme.titleSmall!.copyWith(color: theme.colorScheme.primary)));
    void openArticle(dynamic entry) => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) =>
        ArticlePage(engine: widget.engine, locator: entry['locator'] as String, edition: entry['edition'] as String)));
    Widget article(dynamic entry) => ListTile(contentPadding: EdgeInsets.zero, title: Text('${entry['title']}'), subtitle: Text('${entry['edition']} · ${entry['type']}\n${entry['text']}'), onTap: () => openArticle(entry));
    Widget passage(dynamic found) => ListTile(contentPadding: EdgeInsets.zero,
        title: Text(strings.reference(found['passage'] as String), style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
        subtitle: Text('${found['text']}\n${strings.citedIn((found['sources'] as List<dynamic>).join('; '))}'), onTap: () => open(found['passage'] as String));
    Widget example(dynamic found) => ListTile(contentPadding: EdgeInsets.zero,
        title: Text(strings.reference(found['reference'] as String), style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
        subtitle: Text(found['text'] as String), onTap: () => open(found['reference'] as String));
    final topic = !isTopic ? const <Widget>[] : [
      if ([for (final name in ['entries', 'passages', 'otherEntries', 'otherPassages', 'scripture', 'mentions']) ...list(name)].isEmpty)
        Padding(padding: const EdgeInsets.only(top: 12), child: Text(strings.noResults, style: theme.textTheme.bodySmall)),
      if (list('entries').isNotEmpty) heading(strings.articles),
      ...list('entries').map(article),
      if (list('passages').isNotEmpty) heading(strings.keyPassages),
      ...list('passages').map(passage),
      if (list('otherEntries').isNotEmpty || list('otherPassages').isNotEmpty) heading('${strings.otherSide}: ${list('contrast').join('; ')}'),
      ...list('otherEntries').map(article),
      ...list('otherPassages').map(passage),
      if (list('scripture').isNotEmpty) heading(strings.inTheBible),
      ...list('scripture').map(example),
      if (list('mentions').isNotEmpty) heading(strings.inTheNotes),
      ...list('mentions').map(example),
    ];
    return Scaffold(
      appBar: AppBar(title: TextField(
        controller: words, autofocus: true, textInputAction: TextInputAction.search, onSubmitted: (_) => run(),
        decoration: InputDecoration(hintText: kind == SearchKind.topic ? strings.topicHint : strings.searchHint, border: InputBorder.none),
      ), actions: [IconButton(tooltip: strings.search, icon: const Icon(Icons.search), onPressed: run)]),
      body: SafeArea(child: Column(children: [
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4), child: SegmentedButton<SearchKind>(
          segments: [
            ButtonSegment(value: SearchKind.topic, label: FittedBox(fit: BoxFit.scaleDown, child: Text(strings.topic, softWrap: false))),
            ButtonSegment(value: SearchKind.together, label: FittedBox(fit: BoxFit.scaleDown, child: Text(strings.together, softWrap: false))),
            ButtonSegment(value: SearchKind.terms, label: FittedBox(fit: BoxFit.scaleDown, child: Text(strings.originalTerms, softWrap: false))),
            ButtonSegment(value: SearchKind.dictionary, label: FittedBox(fit: BoxFit.scaleDown, child: Text(strings.dictionary, softWrap: false))),
          ],
          selected: {kind}, showSelectedIcon: false,
          onSelectionChanged: (chosen) { setState(() { kind = chosen.first; response = null; }); run(); },
        )),
        if (problem != null) Padding(padding: const EdgeInsets.all(16), child: Text(problem!, style: TextStyle(color: theme.colorScheme.error))),
        if (answer != null && !isTopic) Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4), child: Align(alignment: Alignment.centerLeft,
            child: Text(shown == 0 ? strings.noResults : strings.results(shown, answer['total'] as int), style: theme.textTheme.bodySmall))),
        Expanded(child: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
          ...topic,
          for (final example in isTopic ? const [] : examples)
            ListTile(contentPadding: EdgeInsets.zero, title: Text(strings.reference(example['reference'] as String), style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
                subtitle: Text(example['text'] as String), onTap: () => open(example['reference'] as String)),
          for (final term in terms)
            ListTile(contentPadding: EdgeInsets.zero,
                title: Text('${term['count']}× ${term['lemma']}  ${term['transliteration']}  ‘${term['gloss']}’'),
                subtitle: Text([
                  '${term['strong']} · ${strings.verses(term['verses'] as int)}',
                  for (final example in term['examples'] as List<dynamic>) '${strings.reference(example['reference'] as String)}: ${example['text']}',
                ].join('\n')),
                onTap: (term['examples'] as List<dynamic>).isEmpty ? null : () => open((term['examples'] as List<dynamic>).first['reference'] as String)),
          for (final entry in isTopic ? const [] : entries)
            ListTile(contentPadding: EdgeInsets.zero,
                title: Text('${entry['title']}'),
                subtitle: Text('${entry['edition']} · ${entry['type']}\n${entry['text']}${(entry['see'] as List<dynamic>).isEmpty ? '' : '\n→ ${(entry['see'] as List<dynamic>).join('; ')}'}'),
                onTap: () => openArticle(entry)),
        ])),
      ])),
    );
  }
}
