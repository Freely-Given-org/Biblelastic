// The Biblelastic app: so far a minimal reader, with search, notes on a verse, and module installing.
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'engine/engine.dart';
import 'modules_page.dart';
import 'search_page.dart';
import 'strings.dart';
import 'word_sheet.dart';

/// The edition that's read (the only Bible that the reader offers so far)
const edition = 'OET-RV';

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

  @override
  void initState() {
    super.initState();
    start();
  }

  @override
  void dispose() {
    for (final recogniser in recognisers) { recogniser.dispose(); }
    super.dispose();
  }

  Future<void> start() async {
    try {
      if (!started) await engine.start();
      started = true;
      await loadContents();
    } catch (error) {
      setState(() => problem = '$error');
    }
  }

  /// Find out which books are installed, then show a section
  Future<void> loadContents() async {
    try {
      final response = await engine.request({'command': 'contents', 'edition': edition});
      books = [for (final document in response['documents'] as List<dynamic>) Book(document['name'] as String, document['chapters'] as int, document['introduction'] as bool)];
      final current = section;
      if (current != null && books.any((book) => book.code == current['document'])) {
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
      final response = await engine.request({'command': 'read', 'edition': edition, 'detail': 'words', ...which});
      setState(() { section = response; focus = verse; problem = null; });
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

  Future<void> openSearch() async {
    final reference = await Navigator.of(context).push(MaterialPageRoute<String>(builder: (context) => SearchPage(engine: engine)));
    if (reference != null) await showPassage(reference);
  }

  /// What a word translates (which can lead to another passage)
  Future<void> showWord(int slot) async {
    final reference = await showModalBottomSheet<String>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true,
        builder: (context) => WordSheet(engine: engine, slot: slot));
    if (reference != null) await showPassage(reference);
  }

  void showNotes(String verse) {
    final passage = '${section!['document']} $verse';
    showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true, builder: (context) => NotesSheet(engine: engine, passage: passage));
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
          if (started) IconButton(tooltip: strings.modules, icon: const Icon(Icons.download), onPressed: openModules),
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
    var inFocus = false, keyUsed = false; // Whether the verse being laid out is the one to mark (a verse can run on into the next paragraph)
    final paragraphs = <Widget>[];
    for (final data in (current['paragraphs'] as List<dynamic>).cast<Map<String, dynamic>>()) {
      final (widget, hasFocus, stillInFocus) = paragraph(context, data, inFocus);
      inFocus = stillInFocus;
      paragraphs.add(hasFocus && !keyUsed ? KeyedSubtree(key: focusKey, child: widget) : widget);
      keyUsed = keyUsed || hasFocus;
    }
    // A section is short enough to lay out whole, which lets a verse anywhere in it be scrolled to.
    // The key makes each section start again from the top.
    return SelectionArea(child: SingleChildScrollView(
      key: ValueKey('${current['document']} ${current['section']}'),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      child: Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 640), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        ...paragraphs,
        Padding(padding: const EdgeInsets.only(top: 24), child: Text(strings.tapVerse, style: Theme.of(context).textTheme.bodySmall)),
      ]))),
    ));
  }

  /// One paragraph, laid out by its style and kind. Also says whether the verse to mark starts in it, and whether that verse is still going at its end.
  (Widget, bool, bool) paragraph(BuildContext context, Map<String, dynamic> data, bool inFocus) {
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
    final marked = theme.colorScheme.tertiaryContainer;
    var hasFocus = false;
    final spans = <InlineSpan>[];
    for (final piece in data['pieces'] as List<dynamic>) {
      if (piece['c'] != null) { // A chapter starts with the next verse
        spans.add(TextSpan(text: '${piece['c']} ', style: TextStyle(fontSize: base.fontSize! * 1.5, fontWeight: FontWeight.bold, color: theme.colorScheme.primary, height: 1)));
      } else if (piece['v'] != null) {
        final name = piece['r'] as String;
        inFocus = name == focus;
        hasFocus = hasFocus || inFocus;
        final recogniser = TapGestureRecognizer()..onTap = () => showNotes(name);
        recognisers.add(recogniser);
        spans.add(TextSpan(text: '${piece['v']} ', recognizer: recogniser,
            style: TextStyle(fontSize: base.fontSize! * 0.72, color: theme.colorScheme.primary, fontWeight: FontWeight.bold, backgroundColor: inFocus ? marked : null)));
      } else {
        final marks = (piece['s'] as List<dynamic>? ?? const []).cast<String>();
        var text = base;
        if (marks.contains('wj')) text = text.copyWith(color: theme.brightness == Brightness.dark ? const Color(0xFFFF9E9E) : const Color(0xFF9B1C1C)); // Words of Jesus
        if (marks.contains('add')) text = text.copyWith(color: text.color?.withValues(alpha: 0.72)); // Words added by the translators
        if (marks.contains('em') || marks.contains('it')) text = text.copyWith(fontStyle: FontStyle.italic);
        if (marks.contains('bd')) text = text.copyWith(fontWeight: FontWeight.bold);
        if (inFocus && kind != 'heading') text = text.copyWith(backgroundColor: marked);
        TapGestureRecognizer? recogniser;
        final slot = piece['w'] as int?;
        if (slot != null) { // Each word can be asked about
          recogniser = TapGestureRecognizer()..onTap = () => showWord(slot);
          recognisers.add(recogniser);
        }
        spans.add(TextSpan(text: piece['t'] as String, style: text, recognizer: recogniser));
      }
    }
    return (Padding(padding: padding, child: Text.rich(TextSpan(children: spans, style: base), textAlign: align)), hasFocus, inFocus);
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
  const NotesSheet({super.key, required this.engine, required this.passage});
  final Engine engine;
  final String passage;

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final theme = Theme.of(context);
    return SizedBox(height: MediaQuery.of(context).size.height * 0.7, child: FutureBuilder<Map<String, dynamic>>(
      future: engine.request({'command': 'about', 'passage': passage, 'limit': '30', 'length': '1200'}),
      builder: (context, snapshot) {
        if (snapshot.hasError) return Center(child: Text('${snapshot.error}'));
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final comments = snapshot.data!['comments'] as List<dynamic>;
        return ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
          Text('${strings.notes}: ${strings.reference(passage)}', style: theme.textTheme.titleMedium),
          if (comments.isEmpty) Padding(padding: const EdgeInsets.only(top: 16), child: Text(strings.noNotes)),
          for (final comment in comments)
            Padding(padding: const EdgeInsets.only(top: 16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${comment['edition']} · ${comment['title'] == '' ? strings.reference(comment['locator'] as String) : '${comment['title']} (${strings.reference(comment['passage'] as String)})'}',
                  style: theme.textTheme.labelMedium!.copyWith(color: comment['kind'] == 'about' ? theme.colorScheme.primary : theme.colorScheme.outline)),
              SelectableText(comment['text'] as String, style: theme.textTheme.bodyMedium),
            ])),
        ]);
      },
    ));
  }
}
