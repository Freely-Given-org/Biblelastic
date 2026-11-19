// What a word translates: the original-language word behind it, and how else that word is translated.
import 'package:flutter/material.dart';

import 'article_page.dart';
import 'engine/engine.dart';
import 'strings.dart';

/// A sheet about one word of the text. It closes with a reference (e.g., `JHN 3:16`) if the reader should go there.
class WordSheet extends StatelessWidget {
  const WordSheet({super.key, required this.engine, required this.edition, required this.word});
  final Engine engine;
  /// The edition that the word is in
  final String edition;
  /// The engine's answer to `word` for it
  final Future<Map<String, dynamic>> word;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    return SizedBox(height: MediaQuery.of(context).size.height * 0.6, child: FutureBuilder<Map<String, dynamic>>(
      future: word,
      builder: (context, snapshot) {
        if (snapshot.hasError) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text('${snapshot.error}')));
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final word = snapshot.data!;
        final originals = (word['originals'] as List<dynamic>).cast<Map<String, dynamic>>();
        return ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
          Text('‘${word['text']}’ · ${strings.reference(word['reference'] as String)}', style: theme.textTheme.titleMedium),
          if (originals.isEmpty) Padding(padding: const EdgeInsets.only(top: 16), child: Text(strings.noOriginal)),
          for (final original in originals) ...[
            const SizedBox(height: 16),
            // The word as it's written here, then its dictionary form
            Text.rich(TextSpan(children: [
              TextSpan(text: '${original['text']}', style: theme.textTheme.headlineSmall),
              TextSpan(text: '   ${original['transliteration']}', style: theme.textTheme.titleMedium!.copyWith(fontStyle: FontStyle.italic)),
            ])),
            if (original['gloss'] != '') Text('‘${original['gloss']}’', style: theme.textTheme.bodyLarge),
            const SizedBox(height: 8),
            Text('${strings.lemma}: ${original['lemma']}  ${original['lemmaTransliteration']}'),
            Text([original['strong'], original['morphology'], original['edition']].where((part) => part != '').join(' · '), style: theme.textTheme.bodySmall),
            // Its meaning here, from a dictionary that gives meanings place by place, and the other words that mean something similar
            if (original['meaning'] case final Map<String, dynamic> meaning) ...[
              const SizedBox(height: 12),
              Text(strings.meaningHere, style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
              Text.rich(TextSpan(children: [
                TextSpan(text: meaning['gloss'] as String, style: const TextStyle(fontWeight: FontWeight.bold)),
                if (meaning['definition'] != '') TextSpan(text: ': ${meaning['definition']}'),
                if (meaning['code'] != '') TextSpan(text: '  (${meaning['code']})', style: theme.textTheme.bodySmall),
              ])),
              if (meaning['note'] != '') Padding(padding: const EdgeInsets.only(top: 4), child: Text(meaning['note'] as String, style: theme.textTheme.bodySmall)),
              if ((meaning['domains'] as List<dynamic>).isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(strings.similarMeaning, style: theme.textTheme.bodySmall),
                Wrap(spacing: 8, runSpacing: 4, children: [
                  for (final domain in meaning['domains'] as List<dynamic>) ActionChip(label: Text((domain as String).split(' > ').last), visualDensity: VisualDensity.compact,
                      onPressed: () async {
                        final reference = await Navigator.of(context).push(MaterialPageRoute<String>(builder: (context) =>
                            DomainPage(engine: engine, translation: edition, original: original['edition'] as String, domain: domain)));
                        if (reference != null && context.mounted) Navigator.of(context).pop(reference);
                      }),
                ]),
              ],
            ],
            // Articles about the thing that the word refers to (e.g., an animal)
            if ((original['articles'] as List<dynamic>? ?? const []).isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(strings.aboutThis, style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
              for (final article in original['articles'] as List<dynamic>)
                ListTile(contentPadding: EdgeInsets.zero, dense: true, leading: const Icon(Icons.menu_book_outlined, size: 20),
                    title: Text(article['title'] as String), subtitle: Text('${article['edition']} · ${article['locator']}'),
                    onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) =>
                        ArticlePage(engine: engine, locator: article['locator'] as String, edition: article['edition'] as String)))),
            ],
            if ((original['renderings'] as List<dynamic>).isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(strings.translatedAs(original['counted'] as int, original['occurrences'] as int), style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
              const SizedBox(height: 4),
              Wrap(spacing: 8, runSpacing: 4, children: [
                for (final rendering in original['renderings'] as List<dynamic>) Chip(label: Text('${rendering[0]}  ${rendering[1]}'), visualDensity: VisualDensity.compact),
              ]),
            ],
            if (original['lemma'] != '') Align(alignment: Alignment.centerLeft, child: TextButton(
              onPressed: () async {
                final reference = await Navigator.of(context).push(MaterialPageRoute<String>(builder: (context) =>
                    LemmaPage(engine: engine, edition: edition, original: original['edition'] as String, lemma: original['lemma'] as String, transliteration: original['lemmaTransliteration'] as String)));
                if (reference != null && context.mounted) Navigator.of(context).pop(reference);
              },
              child: Text(strings.everyPlace),
            )),
          ],
        ]);
      },
    ));
  }
}

/// Every verse where an original-language word is translated. It closes with the reference that was chosen.
class LemmaPage extends StatelessWidget {
  const LemmaPage({super.key, required this.engine, required this.edition, required this.original, required this.lemma, required this.transliteration});
  final Engine engine;
  /// The translation to list the verses of, and the original-language edition and dictionary form to find in it
  final String edition, original, lemma, transliteration;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text('$lemma  $transliteration')),
      body: SafeArea(child: FutureBuilder<Map<String, dynamic>>(
        future: engine.request({'command': 'lemma', 'edition': edition, 'original': original, 'lemma': lemma, 'limit': '400'}),
        builder: (context, snapshot) {
          if (snapshot.hasError) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text('${snapshot.error}')));
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final examples = snapshot.data!['examples'] as List<dynamic>;
          return ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
            itemCount: examples.length + 1,
            itemBuilder: (context, index) => index == 0
                ? Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Text(strings.results(examples.length, snapshot.data!['total'] as int), style: theme.textTheme.bodySmall))
                : ListTile(contentPadding: EdgeInsets.zero,
                    title: Text(strings.reference(examples[index - 1]['reference'] as String), style: theme.textTheme.labelLarge!.copyWith(color: theme.colorScheme.primary)),
                    subtitle: Text(examples[index - 1]['text'] as String),
                    onTap: () => Navigator.of(context).pop(examples[index - 1]['reference'] as String)),
          );
        },
      )),
    );
  }
}
