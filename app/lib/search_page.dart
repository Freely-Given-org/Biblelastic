// Searching: words together in a sentence, the original-language terms behind words, and dictionary entries.
import 'package:flutter/material.dart';

import 'engine/engine.dart';
import 'main.dart' show edition;
import 'strings.dart';

enum SearchKind { together, terms, dictionary }

class SearchPage extends StatefulWidget {
  const SearchPage({super.key, required this.engine});
  final Engine engine;
  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final TextEditingController words = TextEditingController();
  SearchKind kind = SearchKind.together;
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
    return Scaffold(
      appBar: AppBar(title: TextField(
        controller: words, autofocus: true, textInputAction: TextInputAction.search, onSubmitted: (_) => run(),
        decoration: InputDecoration(hintText: strings.searchHint, border: InputBorder.none),
      ), actions: [IconButton(tooltip: strings.search, icon: const Icon(Icons.search), onPressed: run)]),
      body: SafeArea(child: Column(children: [
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4), child: SegmentedButton<SearchKind>(
          segments: [
            ButtonSegment(value: SearchKind.together, label: Text(strings.together)),
            ButtonSegment(value: SearchKind.terms, label: Text(strings.originalTerms)),
            ButtonSegment(value: SearchKind.dictionary, label: Text(strings.dictionary)),
          ],
          selected: {kind}, showSelectedIcon: false,
          onSelectionChanged: (chosen) { setState(() { kind = chosen.first; response = null; }); run(); },
        )),
        if (problem != null) Padding(padding: const EdgeInsets.all(16), child: Text(problem!, style: TextStyle(color: theme.colorScheme.error))),
        if (answer != null) Padding(padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4), child: Align(alignment: Alignment.centerLeft,
            child: Text(shown == 0 ? strings.noResults : strings.results(shown, answer['total'] as int), style: theme.textTheme.bodySmall))),
        Expanded(child: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
          for (final example in examples)
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
          for (final entry in entries)
            ListTile(contentPadding: EdgeInsets.zero,
                title: Text('${entry['title']}'),
                subtitle: Text('${entry['edition']} · ${entry['type']}\n${entry['text']}${(entry['see'] as List<dynamic>).isEmpty ? '' : '\n→ ${(entry['see'] as List<dynamic>).join('; ')}'}')),
        ])),
      ])),
    );
  }
}
