// The Biblelastic app: so far a minimal reader, with search, notes on a verse, and module installing.
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'engine/engine.dart';
import 'modules_page.dart';
import 'search_page.dart';
import 'strings.dart';

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

class ReaderPage extends StatefulWidget {
  const ReaderPage({super.key});
  @override
  State<ReaderPage> createState() => _ReaderPageState();
}

class _ReaderPageState extends State<ReaderPage> {
  final Engine engine = Engine();
  final ScrollController scroller = ScrollController();
  bool started = false;
  String? problem;
  List<Book> books = [];
  String book = 'JHN';
  int chapter = 1;
  List<dynamic> paragraphs = [];
  final List<TapGestureRecognizer> recognisers = [];

  @override
  void initState() {
    super.initState();
    start();
  }

  @override
  void dispose() {
    for (final recogniser in recognisers) { recogniser.dispose(); }
    scroller.dispose();
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

  /// Find out which books are installed, then show a chapter
  Future<void> loadContents() async {
    try {
      final response = await engine.request({'command': 'contents', 'edition': edition});
      books = [for (final document in response['documents'] as List<dynamic>) Book(document['name'] as String, document['chapters'] as int, document['introduction'] as bool)];
      if (!books.any((candidate) => candidate.code == book)) { book = books.first.code; chapter = books.first.firstChapter; }
      await show(book, chapter);
    } on EngineException {
      setState(() { books = []; paragraphs = []; problem = null; }); // Nothing installed yet
    }
  }

  Future<void> show(String newBook, int newChapter) async {
    try {
      final response = await engine.request({'command': 'read', 'edition': edition, 'passage': '$newBook $newChapter'});
      setState(() { book = newBook; chapter = newChapter; paragraphs = response['paragraphs'] as List<dynamic>; problem = null; });
      if (scroller.hasClients) scroller.jumpTo(0);
    } catch (error) {
      setState(() => problem = '$error');
    }
  }

  /// The chapter before (-1) or after (+1) this one, going on into the next book, or null at either end
  (String, int)? neighbour(int step) {
    final index = books.indexWhere((candidate) => candidate.code == book);
    if (index < 0) return null;
    final next = chapter + step;
    if (next >= books[index].firstChapter && next <= books[index].chapters) return (book, next);
    final other = index + step;
    if (other < 0 || other >= books.length) return null;
    return (books[other].code, step > 0 ? books[other].firstChapter : books[other].chapters);
  }

  Future<void> chooseBook() async {
    final strings = Strings(Localizations.localeOf(context));
    final chosen = await showModalBottomSheet<(String, int)>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true,
        builder: (context) => BookPicker(books: books, strings: strings, current: book));
    if (chosen != null) await show(chosen.$1, chosen.$2);
  }

  Future<void> openModules() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (context) => ModulesPage(engine: engine)));
    await loadContents();
  }

  Future<void> openSearch() async {
    final chosen = await Navigator.of(context).push(MaterialPageRoute<(String, int)>(builder: (context) => SearchPage(engine: engine)));
    if (chosen != null) await show(chosen.$1, chosen.$2);
  }

  void showNotes(String verse) {
    final passage = '$book $chapter:$verse';
    showModalBottomSheet<void>(context: context, isScrollControlled: true, showDragHandle: true, useSafeArea: true, builder: (context) => NotesSheet(engine: engine, passage: passage));
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings(Localizations.localeOf(context));
    final previous = neighbour(-1), next = neighbour(1);
    return Scaffold(
      appBar: AppBar(
        title: books.isEmpty ? Text(strings.appName) : TextButton(onPressed: chooseBook, child: Text(strings.passage(book, chapter), style: Theme.of(context).textTheme.titleLarge)),
        actions: [
          if (books.isNotEmpty) IconButton(tooltip: strings.previousChapter, icon: const Icon(Icons.chevron_left), onPressed: previous == null ? null : () => show(previous.$1, previous.$2)),
          if (books.isNotEmpty) IconButton(tooltip: strings.nextChapter, icon: const Icon(Icons.chevron_right), onPressed: next == null ? null : () => show(next.$1, next.$2)),
          if (books.isNotEmpty) IconButton(tooltip: strings.search, icon: const Icon(Icons.search), onPressed: openSearch),
          if (started) IconButton(tooltip: strings.modules, icon: const Icon(Icons.download), onPressed: openModules),
        ],
      ),
      body: SafeArea(child: body(context, strings)),
    );
  }

  Widget body(BuildContext context, Strings strings) {
    if (problem != null) return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(problem!, style: TextStyle(color: Theme.of(context).colorScheme.error))));
    if (!started) return Center(child: Text(strings.starting));
    if (books.isEmpty) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(strings.noBible),
        const SizedBox(height: 16),
        FilledButton(onPressed: openModules, child: Text(strings.getModules)),
      ]));
    }
    for (final recogniser in recognisers) { recogniser.dispose(); }
    recognisers.clear();
    return SelectionArea(child: ListView.builder(
      controller: scroller,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      itemCount: paragraphs.length + 1,
      itemBuilder: (context, index) => index == paragraphs.length
          ? Padding(padding: const EdgeInsets.only(top: 24), child: Text(strings.tapVerse, style: Theme.of(context).textTheme.bodySmall))
          : Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 640), child: SizedBox(width: double.infinity, child: paragraph(context, paragraphs[index] as Map<String, dynamic>)))),
    ));
  }

  /// One paragraph, laid out by its style and kind
  Widget paragraph(BuildContext context, Map<String, dynamic> data) {
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
    final spans = <InlineSpan>[];
    for (final piece in data['pieces'] as List<dynamic>) {
      if (piece['v'] != null) {
        final verse = piece['v'] as String;
        final recogniser = TapGestureRecognizer()..onTap = () => showNotes(verse);
        recognisers.add(recogniser);
        spans.add(TextSpan(text: '$verse ', recognizer: recogniser,
            style: TextStyle(fontSize: base.fontSize! * 0.72, color: theme.colorScheme.primary, fontWeight: FontWeight.bold)));
      } else {
        final marks = (piece['s'] as List<dynamic>? ?? const []).cast<String>();
        var text = base;
        if (marks.contains('wj')) text = text.copyWith(color: theme.brightness == Brightness.dark ? const Color(0xFFFF9E9E) : const Color(0xFF9B1C1C)); // Words of Jesus
        if (marks.contains('add')) text = text.copyWith(color: text.color?.withValues(alpha: 0.72)); // Words added by the translators
        if (marks.contains('em') || marks.contains('it')) text = text.copyWith(fontStyle: FontStyle.italic);
        if (marks.contains('bd')) text = text.copyWith(fontWeight: FontWeight.bold);
        spans.add(TextSpan(text: piece['t'] as String, style: text));
      }
    }
    return Padding(padding: padding, child: Text.rich(TextSpan(children: spans, style: base), textAlign: align));
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
