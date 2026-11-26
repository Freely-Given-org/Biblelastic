// The Biblelastic app: so far a minimal reader, with search, notes on a verse, and module installing.
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'engine/engine.dart';
import 'library_page.dart';
import 'modules_page.dart';
import 'search_page.dart';
import 'strings.dart';
import 'word_sheet.dart';
import 'works.dart';

/// The Bible that's read: one of the installed ones (see [readableBibles]), which is remembered
String edition = 'OET-RV';
/// The edition that can be shown with the OET-RV, for the same verses
const literal = 'OET-LV';

void main() => runApp(const BiblelasticApp());

class BiblelasticApp extends StatelessWidget {
  const BiblelasticApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Biblelastic',
      theme: ThemeData(colorSchemeSeed: const Color(0xFF2E5E4E), brightness: Brightness.light),
      darkTheme: ThemeData(colorSchemeSeed: const Color(0xFF2E5E4E), brightness: Brightness.dark),
      home: const ReaderPage(),
    );
  }
}

/// One book of the edition, from the engine's `contents`
class Book {
  const Book(this.code, this.chapters, this.introduction);
  final String code;
  final int chapters;
  final bool introduction;
  int get firstChapter => chapters == 0 || introduction ? 0 : 1;
}

/// The reader shows one section at a time: from one section heading to the next, whichever chapters that covers.
class ReaderPage extends StatefulWidget {
  const ReaderPage({super.key});
  @override
  State<ReaderPage> createState() => _ReaderPageState();
}

class _ReaderPageState extends State<ReaderPage> {
  final Engine engine = Engine();
  bool started = false;
  String? problem;
  List<Book> books = [];
  /// The section that's showing, as the engine gave it (see `read` with `unit=section` in the engine's api.rs)
  Map<String, dynamic>? section;
  /// A verse to bring into view and mark, e.g., `3:16` (after a search, or after choosing a chapter)
  String? focus;
  final GlobalKey focusKey = GlobalKey();
  final List<TapGestureRecognizer> recognisers = [];
  /// What's shown: `rv` (the Readers' Version), `lv` (the Literal Version), or `both`. It's remembered.
  String view = 'rv';
  bool literalAvailable = false;
  /// The Literal Version of the section's verses: each verse's pieces, by the verse's name (e.g., `3:16`)
  Map<String, List<dynamic>> literalVerses = {};
  /// The words to mark, by edition: the ones that translate the same original word as the word that was tapped
  Map<String, Set<int>> linked = {};
  /// The verses of the section that have a note of their own, e.g., `3:16`
  Set<String> get noted => {...(section?['noted'] as List<dynamic>? ?? const []).cast<String>()};

  @override
  void initState() {
    super.initState();
    start();
  }

  Future<void> setView(String newView) async {
    setState(() => view = newView);
    try { await (await SharedPreferences.getInstance()).setString('view', newView); } catch (_) {} // Not being able to remember it doesn't matter much
    if (newView != 'rv' && literalVerses.isEmpty) {
      await loadLiteral();
      if (mounted) setState(() {});
    }
  }

  /// The Literal Version for the verses of the section that's showing (nothing, if there are none, or if it isn't installed)
  Future<void> loadLiteral() async {
    literalVerses = {};
    final passage = section?['passage'] as String? ?? '';
    if (view == 'rv' || !literalAvailable || !passage.contains(':')) return;
    try {
      final reading = await engine.request({'command': 'read', 'edition': literal, 'detail': 'words', 'passage': passage});
      String? verse;
      for (final paragraph in reading['paragraphs'] as List<dynamic>) {
        for (final piece in paragraph['pieces'] as List<dynamic>) {
          if (piece['c'] != null) continue; // (Chapters are marked in the Readers' Version)
          if (piece['r'] != null) verse = piece['r'] as String;
          if (verse != null) literalVerses.putIfAbsent(verse, () => []).add(piece);
        }
      }
    } on EngineException {
      // e.g., a book that the Literal Version doesn't have
    }
  }

  @override
  void dispose() {
    for (final recogniser in recognisers) { recogniser.dispose(); }
    super.dispose();
  }

  Future<void> start() async {
    try {
      if (!started) await engine.start();
      try { view = (await SharedPreferences.getInstance()).getString('view') ?? view; } catch (_) {}
      try { chosenBible = (await SharedPreferences.getInstance()).getString('bible'); } catch (_) {}
      started = true;
      await loadContents();
    } catch (error) {
      setState(() => problem = '$error');
    }
  }

  /// The Bible that was chosen (if one was), which is read if it's installed
  String? chosenBible;

  /// Which Bible to read: the one chosen, or else one in the language of the phone, or else the first
  String whichBible(List<String> bibles) {
    if (chosenBible != null && bibles.contains(chosenBible)) return chosenBible!;
    final language = Localizations.localeOf(context).languageCode == 'es' ? 'spa' : 'eng';
    return bibles.firstWhere((bible) => works[bible]?['language'] == language, orElse: () => bibles.first);
  }

  /// Find out which books are installed, then show a section (or the section that a passage starts in, e.g., after choosing another Bible)
  Future<void> loadContents({String? passage}) async {
    try {
      await loadWorks(engine);
      final bibles = readableBibles();
      if (bibles.isNotEmpty) edition = whichBible(bibles);
      final response = await engine.request({'command': 'contents', 'edition': edition});
      books = [for (final document in response['documents'] as List<dynamic>) Book(document['name'] as String, document['chapters'] as int, document['introduction'] as bool)];
      try {
        if (edition != 'OET-RV') throw const EngineException('The Literal Version goes with the Readers’ Version');
        await engine.request({'command': 'contents', 'edition': literal});
        literalAvailable = true;
      } on EngineException {
        literalAvailable = false;
        literalVerses = {};
      }
      final current = section;
      if (passage != null && books.any((book) => passage.startsWith('${book.code} '))) {
        await showPassage(passage, mark: false);
      } else if (current != null && books.any((book) => book.code == current['document'])) {
        await showSection(current['document'] as String, current['section'] as int);
      } else {
        await showPassage(books.any((book) => book.code == 'JHN') ? 'JHN 1:1' : '${books.first.code} 1:1', mark: false);
      }
    } on EngineException {
      setState(() { books = []; section = null; problem = null; }); // Nothing installed yet
    }
  }

  Future<void> show(Map<String, String> which, String? verse) async {
    try {
      section = await engine.request({'command': 'read', 'edition': edition, 'detail': 'words', ...which});
      await loadLiteral();
      setState(() { focus = verse; linked = {}; problem = null; });
      // Once it's laid out, bring the wanted verse into view (or go back to the top)
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final target = focusKey.currentContext;
        if (verse != null && target != null && target.mounted) Scrollable.ensureVisible(target, alignment: 0.15);
      });
    } catch (error) {
      setState(() => problem = '$error');
    }
  }

  /// The section that a passage like `JHN 3:16` starts in, with that verse in view
  Future<void> showPassage(String passage, {bool mark = true}) {
    final verse = RegExp(r' (\d+:\d+)').firstMatch(passage)?.group(1);
    return show({'unit': 'section', 'passage': passage}, mark ? verse : null);
  }

  /// A section by its number in a book (0 is whatever comes before the first section)
  Future<void> showSection(String document, int number) => show({'document': document, 'section': '$number'}, null);

  Future<void> chooseBook() async {
    final strings = Strings(Localizations.localeOf(context));
    final chosen = await showModalBottomSheet<(String, int)>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true,
        builder: (context) => BookPicker(books: books, strings: strings, current: section?['document'] as String? ?? ''));
    if (chosen == null) return;
    final (book, chapter) = chosen;
    if (chapter > 0) return showPassage('$book $chapter:1', mark: chapter > 1); // A chapter needn't start where a section does
    await showSection(book, 0);
    if (problem != null) await showSection(book, 1); // Nothing comes before this book's first section
  }

  Future<void> openModules() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => ModulesPage(engine: engine)));
    await loadContents();
  }

  /// Read another of the installed Bibles, at the same place
  Future<void> chooseBible() async {
    final strings = Strings(Localizations.localeOf(context));
    final chosen = await showModalBottomSheet<String>(context: context, showDragHandle: true, useSafeArea: true, builder: (context) => ListView(shrinkWrap: true, children: [
      ListTile(title: Text(strings.chooseBible, style: Theme.of(context).textTheme.titleMedium)),
      for (final bible in readableBibles())
        ListTile(title: Text(titleOf(bible)), subtitle: Text(bible), selected: bible == edition, trailing: bible == edition ? const Icon(Icons.check) : null,
            onTap: () => Navigator.of(context).pop(bible)),
    ]));
    if (chosen == null || chosen == edition) return;
    chosenBible = chosen;
    try { await (await SharedPreferences.getInstance()).setString('bible', chosen); } catch (_) {}
    final passage = section?['passage'] as String?;
    await loadContents(passage: passage?.replaceFirst(RegExp(r'-.*'), '')); // Where the section that's showing starts
  }

  // The app's version and licence, then each installed work's
  Future<void> openAbout() => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => const AboutWorksPage()));
  Future<void> openLibrary() => Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => LibraryPage(engine: engine)));

  Future<void> openSearch() async {
    final reference = await Navigator.of(context).push(MaterialPageRoute<String>(builder: (context) => SearchPage(engine: engine)));
    if (reference != null) await showPassage(reference);
  }

  /// What a word translates (which can lead to another passage)
  /// and marks the words of each version that translate the same original word
  Future<void> showWord(int slot, String ofEdition) async {
    final word = engine.request({'command': 'word', 'edition': ofEdition, 'slot': '$slot'});
    word.then((answer) {
      if (mounted) setState(() => linked = {for (final link in answer['linked'] as List<dynamic>? ?? const []) link['edition'] as String: {...(link['slots'] as List<dynamic>).cast<int>()}});
    }, onError: (_) {});
    final reference = await showModalBottomSheet<String>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true,
        builder: (context) => WordSheet(engine: engine, edition: ofEdition, word: word));
    if (reference != null) await showPassage(reference);
  }

  /// The notes on a verse (which can be on the passage around it). If there are none at all, a brief message says so, so that it's clear the tap worked.
  Future<void> showNotes(String verse) async {
    final strings = Strings(Localizations.localeOf(context));
    final messenger = ScaffoldMessenger.of(context);
    final passage = '${section!['document']} $verse';
    void say(String message) => messenger..hideCurrentSnackBar()..showSnackBar(SnackBar(content: Text(message), duration: const Duration(milliseconds: 1800), behavior: SnackBarBehavior.floating));
    try {
      final notes = await engine.request({'command': 'about', 'passage': passage, 'limit': '30', 'length': '1200'});
      if (!mounted) return;
      final comments = notes['comments'] as List<dynamic>;
      if (comments.isEmpty) return say(strings.noNotesFor(verse.split(':').last));
      // The notes in the language of the Bible that's being read come first (e.g., the Spanish ones, while reading a Spanish Bible)
      final language = works[edition]?['language'];
      bool inLanguage(dynamic comment) => works[comment['edition']]?['language'] == language;
      notes['comments'] = [...comments.where(inLanguage), ...comments.where((comment) => !inLanguage(comment))];
      await showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true, builder: (context) => NotesSheet(passage: passage, notes: notes));
    } catch (error) {
      say('$error');
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final current = section;
    final previous = current?['previous'] as Map<String, dynamic>?, next = current?['next'] as Map<String, dynamic>?;
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 4,
        title: current == null ? Padding(padding: const EdgeInsets.only(left: 12), child: Text(strings.appName))
            : TextButton(onPressed: chooseBook, child: Text(strings.reference(current['passage'] as String), style: Theme.of(context).textTheme.titleLarge, overflow: TextOverflow.ellipsis)),
        actions: [
          if (current != null) IconButton(tooltip: strings.previousSection, icon: const Icon(Icons.chevron_left),
              onPressed: previous == null ? null : () => showSection(previous['document'] as String, previous['section'] as int)),
          if (current != null) IconButton(tooltip: strings.nextSection, icon: const Icon(Icons.chevron_right),
              onPressed: next == null ? null : () => showSection(next['document'] as String, next['section'] as int)),
          if (current != null) IconButton(tooltip: strings.search, icon: const Icon(Icons.search), onPressed: openSearch),
          if (started) PopupMenuButton<String>(tooltip: strings.more, onSelected: (choice) => switch (choice) { 'bible' => chooseBible(), 'library' => openLibrary(), 'about' => openAbout(), _ => openModules() }, itemBuilder: (context) => [
            if (current != null && readableBibles().length > 1) PopupMenuItem(value: 'bible', child: ListTile(leading: const Icon(Icons.menu_book_outlined), title: Text(strings.bible), subtitle: Text(edition))),
            if (current != null) PopupMenuItem(value: 'library', child: ListTile(leading: const Icon(Icons.local_library_outlined), title: Text(strings.library))),
            PopupMenuItem(value: 'modules', child: ListTile(leading: const Icon(Icons.download), title: Text(strings.modules))),
            PopupMenuItem(value: 'about', child: ListTile(leading: const Icon(Icons.info_outline), title: Text(strings.about))),
          ]),
        ],
      ),
      body: SafeArea(child: body(context, strings)),
    );
  }

  Widget body(BuildContext context, Strings strings) {
    if (problem != null) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(problem!, style: TextStyle(color: Theme.of(context).colorScheme.error))));
    if (!started) return Center(child: Text(strings.starting));
    final current = section;
    if (current == null) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(strings.noBible),
        const SizedBox(height: 16),
        FilledButton(onPressed: openModules, child: Text(strings.getModules)),
      ]));
    }
    for (final recogniser in recognisers) { recogniser.dispose(); }
    recognisers.clear();
    final theme = Theme.of(context);
    final showLiteral = view != 'rv' && literalVerses.isNotEmpty;
    final wide = view == 'both' && MediaQuery.sizeOf(context).width >= 840;
    // The Readers' Version is laid out in runs of paragraphs that end where a verse ends, so that the Literal Version
    // of the same verses can go beside each run (on a wide screen) or after it
    final paragraphs = (current['paragraphs'] as List<dynamic>).cast<Map<String, dynamic>>();
    final runs = <Widget>[];
    var readers = <Widget>[];
    var verses = <String>[];
    var inFocus = false, runHasFocus = false, keyUsed = false;
    void finishRun() {
      final literalText = showLiteral && verses.isNotEmpty ? literalBlock(context, verses) : null;
      if (readers.isNotEmpty || literalText != null) {
        final Widget run = literalText == null ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: readers)
            : view == 'lv' ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [...readers, literalText])
            : wide ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: readers)),
                const SizedBox(width: 32),
                Expanded(child: literalText),
              ])
            : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [...readers, literalText]);
        runs.add(runHasFocus && !keyUsed ? KeyedSubtree(key: focusKey, child: run) : run);
        keyUsed = keyUsed || runHasFocus;
      }
      readers = []; verses = []; runHasFocus = false;
    }
    for (var index = 0; index < paragraphs.length; index++) {
      final data = paragraphs[index];
      final pieces = data['pieces'] as List<dynamic>;
      final names = [for (final piece in pieces) if (piece['r'] != null) piece['r'] as String];
      verses.addAll(names);
      runHasFocus = runHasFocus || names.contains(focus) || (inFocus && pieces.isNotEmpty && pieces.first['r'] == null);
      // With only the Literal Version, the Readers' Version's headings are still shown, to find the way by
      if (view != 'lv' || data['kind'] != 'body' || !showLiteral) {
        final (widget, stillInFocus) = paragraph(context, data, inFocus);
        inFocus = stillInFocus;
        readers.add(widget);
      }
      final next = index + 1 < paragraphs.length ? paragraphs[index + 1] : null;
      final nextPieces = next?['pieces'] as List<dynamic>? ?? const [];
      if (next == null || next['kind'] != 'body' || nextPieces.isEmpty || nextPieces.first['r'] != null || nextPieces.first['c'] != null) finishRun();
    }
    finishRun();
    // A section is short enough to lay out whole, which lets a verse anywhere in it be scrolled to.
    // The key makes each section start again from the top.
    return SelectionArea(child: SingleChildScrollView(
      key: ValueKey('${current['document']} ${current['section']} $view'),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      child: Center(child: ConstrainedBox(constraints: BoxConstraints(maxWidth: wide ? 1100 : 640), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (literalAvailable) Center(child: SegmentedButton<String>(
          segments: [
            ButtonSegment(value: 'rv', label: Text(strings.readersVersion)),
            ButtonSegment(value: 'both', label: Text(strings.bothVersions)),
            ButtonSegment(value: 'lv', label: Text(strings.literalVersion)),
          ],
          selected: {view}, showSelectedIcon: false, style: const ButtonStyle(visualDensity: VisualDensity.compact),
          onSelectionChanged: (chosen) => setView(chosen.first),
        )),
        ...runs,
        Padding(padding: const EdgeInsets.only(top: 24), child: Text(strings.tapVerse, style: theme.textTheme.bodySmall)),
      ]))),
    ));
  }

  /// One paragraph of the Readers' Version, laid out by its style and kind. Also says whether the verse to mark is still going at its end.
  (Widget, bool) paragraph(BuildContext context, Map<String, dynamic> data, bool inFocus) {
    final theme = Theme.of(context);
    final style = data['style'] as String, kind = data['kind'] as String;
    var base = theme.textTheme.bodyLarge!.copyWith(height: 1.5);
    var padding = const EdgeInsets.only(top: 8);
    var align = TextAlign.start;
    if (kind == 'title') {
      base = (style == 'mt1' ? theme.textTheme.headlineMedium! : theme.textTheme.titleLarge!);
      align = TextAlign.center;
      padding = const EdgeInsets.only(top: 12);
    } else if (kind == 'heading') {
      base = (style == 'r' ? theme.textTheme.bodySmall! : theme.textTheme.titleMedium!.copyWith(fontWeight: FontWeight.bold));
      padding = EdgeInsets.only(top: style == 'r' ? 0 : 20);
    } else if (style.startsWith('q') || style.startsWith('li') || style.startsWith('io')) { // Poetry and lists: indented by level
      final level = int.tryParse(style.replaceAll(RegExp('[a-z]'), '')) ?? 1;
      padding = EdgeInsets.only(left: 16.0 * level, top: 2);
    } else if (style == 'd') {
      base = base.copyWith(fontStyle: FontStyle.italic);
    }
    final (spans, stillInFocus) = pieceSpans(context, data['pieces'] as List<dynamic>, base, edition, inFocus, markFocus: kind != 'heading');
    return (Padding(padding: padding, child: Text.rich(TextSpan(children: spans, style: base), textAlign: align)), stillInFocus);
  }

  /// The Literal Version of some verses, as one block
  Widget literalBlock(BuildContext context, List<String> verses) {
    final theme = Theme.of(context);
    final base = theme.textTheme.bodyLarge!.copyWith(height: 1.5, color: theme.colorScheme.onSurfaceVariant);
    final (spans, _) = pieceSpans(context, [for (final verse in verses) ...?literalVerses[verse]], base, literal, false);
    if (view == 'both') spans.insert(0, TextSpan(text: 'LV  ', style: theme.textTheme.labelSmall!.copyWith(color: theme.colorScheme.outline, fontWeight: FontWeight.bold)));
    final text = Text.rich(TextSpan(children: spans, style: base));
    return view == 'lv' ? Padding(padding: const EdgeInsets.only(top: 8), child: text)
        : Container(margin: const EdgeInsets.only(top: 8), padding: const EdgeInsets.only(left: 12),
            decoration: BoxDecoration(border: Border(left: BorderSide(color: theme.colorScheme.outlineVariant, width: 3))), child: text);
  }

  /// Text spans for a paragraph's pieces (chapter and verse numbers, and words). Also says whether the verse to mark is still going at the end.
  (List<InlineSpan>, bool) pieceSpans(BuildContext context, List<dynamic> pieces, TextStyle base, String ofEdition, bool inFocus, {bool markFocus = true}) {
    final theme = Theme.of(context);
    final focusColour = theme.colorScheme.tertiaryContainer, linkedColour = theme.colorScheme.secondaryContainer;
    final linkedHere = linked[ofEdition] ?? const <int>{};
    final spans = <InlineSpan>[];
    for (final piece in pieces) {
      if (piece['c'] != null) { // A chapter starts with the next verse
        spans.add(TextSpan(text: '${piece['c']} ', style: TextStyle(fontSize: base.fontSize! * 1.5, fontWeight: FontWeight.bold, color: theme.colorScheme.primary, height: 1)));
      } else if (piece['v'] != null) {
        final name = piece['r'] as String;
        inFocus = name == focus;
        final hasOwnNote = noted.contains(name);
        // A widget rather than plain text, so that the area that can be tapped is wider than the number itself
        spans.add(WidgetSpan(alignment: PlaceholderAlignment.baseline, baseline: TextBaseline.alphabetic, child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => showNotes(name),
          child: Padding(padding: const EdgeInsets.only(left: 6, right: 7), child: Text('${piece['v']}', style: TextStyle(
            fontSize: base.fontSize! * 0.75, height: base.height, color: theme.colorScheme.primary, fontWeight: FontWeight.bold,
            backgroundColor: inFocus && markFocus ? focusColour : null,
            decoration: hasOwnNote ? TextDecoration.underline : null, decorationColor: theme.colorScheme.primary, decorationThickness: 2))),
        )));
      } else {
        final marks = (piece['s'] as List<dynamic>? ?? const []).cast<String>();
        var text = base;
        if (marks.contains('wj')) text = text.copyWith(color: theme.brightness == Brightness.dark ? const Color(0xFFFF9E9E) : const Color(0xFF9B1C1C)); // Words of Jesus
        if (marks.contains('add')) text = text.copyWith(color: text.color?.withValues(alpha: 0.72)); // Words added by the translators
        if (marks.contains('untr')) text = text.copyWith(color: text.color?.withValues(alpha: 0.5)); // Words of the original that aren't normally translated
        if (marks.contains('em') || marks.contains('it')) text = text.copyWith(fontStyle: FontStyle.italic);
        if (marks.contains('bd')) text = text.copyWith(fontWeight: FontWeight.bold);
        if (inFocus && markFocus) text = text.copyWith(backgroundColor: focusColour);
        TapGestureRecognizer? recogniser;
        final slot = piece['w'] as int?;
        if (slot != null && aligned.contains(ofEdition)) { // Each word can be asked about (what it translates)
          if (linkedHere.contains(slot)) text = text.copyWith(backgroundColor: linkedColour);
          recogniser = TapGestureRecognizer()..onTap = () => showWord(slot, ofEdition);
          recognisers.add(recogniser);
        }
        spans.add(TextSpan(text: piece['t'] as String, style: text, recognizer: recogniser));
      }
    }
    return (spans, inFocus);
  }
}

/// Choose a book, then one of its chapters
class BookPicker extends StatefulWidget {
  const BookPicker({super.key, required this.books, required this.strings, required this.current});
  final List<Book> books;
  final Strings strings;
  final String current;
  @override
  State<BookPicker> createState() => _BookPickerState();
}

class _BookPickerState extends State<BookPicker> {
  Book? chosen;

  @override
  Widget build(BuildContext context) {
    final strings = widget.strings, book = chosen;
    return SizedBox(height: MediaQuery.of(context).size.height * 0.75, child: Column(children: [
      ListTile(
        leading: book == null ? null : IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => setState(() => chosen = null)),
        title: Text(book == null ? strings.chooseBook : '${strings.book(book.code)}: ${strings.chooseChapter}', style: Theme.of(context).textTheme.titleMedium),
      ),
      Expanded(child: book == null
          ? GridView.extent(maxCrossAxisExtent: 180, childAspectRatio: 3.2, padding: const EdgeInsets.all(8), children: [
              for (final candidate in widget.books)
                TextButton(
                  style: candidate.code == widget.current ? TextButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.secondaryContainer) : null,
                  onPressed: () => candidate.chapters == 0 ? Navigator.of(context).pop((candidate.code, 0)) : setState(() => chosen = candidate),
                  child: Text(strings.book(candidate.code), textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis),
                ),
            ])
          : GridView.extent(maxCrossAxisExtent: 72, padding: const EdgeInsets.all(8), children: [
              for (var number = book.firstChapter; number <= book.chapters; number++)
                TextButton(onPressed: () => Navigator.of(context).pop((book.code, number)), child: Text(number == 0 ? '✎' : '$number', semanticsLabel: number == 0 ? strings.introduction : null)),
            ])),
    ]));
  }
}

/// What the installed commentaries and dictionaries say about one verse
class NotesSheet extends StatelessWidget {
  const NotesSheet({super.key, required this.passage, required this.notes});
  final String passage;
  /// The engine's answer to `about` for the passage
  final Map<String, dynamic> notes;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    final comments = notes['comments'] as List<dynamic>;
    return SizedBox(height: MediaQuery.of(context).size.height * 0.7, child: ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
          Text('${strings.notes}: ${strings.reference(passage)}', style: theme.textTheme.titleMedium),
          for (final comment in comments)
            Padding(padding: const EdgeInsets.only(top: 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${titleOf(comment['edition'] as String)} · ${comment['title'] == '' ? strings.reference(comment['locator'] as String) : '${comment['title']} (${strings.reference(comment['passage'] as String)})'}',
                  style: theme.textTheme.labelMedium!.copyWith(color: comment['kind'] == 'about' ? theme.colorScheme.primary : theme.colorScheme.outline)),
              SelectableText(comment['text'] as String, style: theme.textTheme.bodyMedium),
            ])),
          Disclaimers(editions: [for (final comment in comments) comment['edition'] as String]),
    ]));
  }
}
