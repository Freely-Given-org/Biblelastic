// What's known about the installed works (titles, kinds, and disclaimers), and showing a disclaimer.
import 'package:flutter/material.dart';

import 'engine/engine.dart';

/// The installed works, by edition: {'title', 'work', 'disclaimer'} (from the engine's `info`). Kept up to date by [loadWorks].
final Map<String, Map<String, dynamic>> works = {};

/// The editions whose words are linked to the original words that they translate (so a word can be tapped to see what it translates)
final Set<String> aligned = {};

Future<void> loadWorks(Engine engine) async {
  final info = await engine.request({'command': 'info'});
  final modules = (info['modules'] as List<dynamic>).cast<Map<String, dynamic>>();
  works
    ..clear()
    ..addAll({for (final module in modules) if (module['kind'] == 'text') module['edition'] as String: module});
  aligned
    ..clear()
    ..addAll([for (final module in modules) if (module['kind'] == 'alignment') module['from'] as String]);
  meaningAvailable = modules.any((module) => module['kind'] == 'model') && modules.any((module) => module['kind'] == 'vectors');
}

/// Whether meaning-based search can be done: a model and some passages' vectors are installed
bool meaningAvailable = false;

/// The installed Bibles that can be read (translations, not the original-language texts, nor the OET's Literal Version, which goes with the Readers' Version),
/// the OET first, then the Aquifer Spanish text, then the others by title
List<String> readableBibles() {
  const first = ['OET-RV', 'ASBRT'];
  final bibles = [for (final MapEntry(key: edition, value: work) in works.entries)
      if (work['work'] == 'scripture' && edition != 'OET-LV' && !const {'grc', 'hbo', 'arc'}.contains(work['language'])) edition];
  int rank(String edition) => first.contains(edition) ? first.indexOf(edition) : first.length;
  return bibles..sort((a, b) => rank(a) != rank(b) ? rank(a) - rank(b) : titleOf(a).compareTo(titleOf(b)));
}

/// A work's title, or its edition's code if it isn't known
String titleOf(String edition) => (works[edition]?['title'] as String?)?.isNotEmpty == true ? works[edition]!['title'] as String : edition;

/// The disclaimers of these editions, each shown once with the works that it applies to
class Disclaimers extends StatelessWidget {
  const Disclaimers({super.key, required this.editions});
  final Iterable<String> editions;

  @override
  Widget build(BuildContext context) {
    final byText = <String, List<String>>{};
    for (final edition in editions.toSet()) {
      final text = works[edition]?['disclaimer'] as String? ?? '';
      if (text.isNotEmpty) byText.putIfAbsent(text, () => []).add(titleOf(edition));
    }
    final theme = Theme.of(context);
    final style = theme.textTheme.bodySmall!.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final MapEntry(key: text, value: titles) in byText.entries)
        Container(
          margin: const EdgeInsets.only(top: 20),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6), borderRadius: BorderRadius.circular(8)),
          child: Text.rich(TextSpan(style: style, children: [
            TextSpan(text: '${titles.join('; ')}: ', style: const TextStyle(fontWeight: FontWeight.bold)),
            ...htmlSpans(text),
          ])),
        ),
    ]);
  }
}

/// A little HTML (only <em>, <i>, <b>, and <a>) as text spans
List<InlineSpan> htmlSpans(String html) {
  final spans = <InlineSpan>[];
  var italic = 0, bold = 0, link = 0;
  for (final match in RegExp(r'<(/?)(\w+)[^>]*>|([^<]+)').allMatches(html)) {
    if (match.group(3) != null) {
      final text = match.group(3)!.replaceAll('&amp;', '&').replaceAll('&quot;', '"').replaceAll('&#39;', "'").replaceAll('&lt;', '<').replaceAll('&gt;', '>');
      spans.add(TextSpan(text: text, style: TextStyle(fontStyle: italic > 0 ? FontStyle.italic : null, fontWeight: bold > 0 ? FontWeight.bold : null,
          decoration: link > 0 ? TextDecoration.underline : null)));
      continue;
    }
    final step = match.group(1) == '/' ? -1 : 1;
    switch (match.group(2)!.toLowerCase()) {
      case 'em' || 'i': italic += step;
      case 'b' || 'strong': bold += step;
      case 'a': link += step;
    }
  }
  return spans;
}
