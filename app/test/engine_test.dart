// The app's native engine binding, against the real library and modules.
// Run app/build-engine.sh linux, the ingest, and `biblelastic compile` first; the tests are skipped if those haven't been done.
import 'dart:io';
import 'dart:ui' show Locale;

import 'package:biblelastic/engine/engine.dart';
import 'package:biblelastic/engine/engine_native.dart';
import 'package:biblelastic/strings.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final library = File('linux/engine/libbiblelastic.so'), modules = Directory('../build/modules');
  final ready = library.existsSync() && File('${modules.path}/OET-RV.text.blm').existsSync();

  test('reads, searches, and finds notes through the native library', () async {
    final engine = NativeEngine(libraryPath: library.absolute.path, modulesFolder: modules.absolute);
    await engine.start();
    expect((await engine.installed()).map((module) => module.name), contains('OET-RV.text'));

    final contents = await engine.request({'command': 'contents', 'edition': 'OET-RV'});
    final john = (contents['documents'] as List<dynamic>).firstWhere((document) => document['name'] == 'JHN');
    expect((john['chapters'], john['introduction']), (21, true));

    final reading = await engine.request({'command': 'read', 'edition': 'OET-RV', 'passage': 'JHN 3'});
    final pieces = [for (final paragraph in reading['paragraphs'] as List<dynamic>) ...paragraph['pieces'] as List<dynamic>];
    expect(pieces.where((piece) => piece['v'] != null).length, 36); // John 3 has 36 verses
    expect(pieces.any((piece) => (piece['s'] as List<dynamic>? ?? []).contains('wj')), isTrue);

    // By section: the one that John 3:16 is in, which starts at its heading
    final section = await engine.request({'command': 'read', 'edition': 'OET-RV', 'unit': 'section', 'passage': 'JHN 3:16'});
    expect((section['document'], section['passage'], (section['previous'] as Map<String, dynamic>)['section']), ('JHN', 'JHN 3:1-21', (section['section'] as int) - 1));
    expect(((section['paragraphs'] as List<dynamic>).first as Map<String, dynamic>)['kind'], 'heading');

    // Several requests at once are each answered (the engine runs in its own isolate)
    final together = await Future.wait([for (final chapter in [1, 2, 3]) engine.request({'command': 'read', 'edition': 'OET-RV', 'passage': 'JHN $chapter'})]);
    expect(together.map((reading) => reading['passage']), ['JHN 1', 'JHN 2', 'JHN 3']);

    final found = await engine.request({'command': 'find', 'edition': 'OET-RV', 'words': 'grace truth'});
    expect(found['total'], 4);
    final notes = await engine.request({'command': 'about', 'passage': 'JHN 3:16', 'limit': '1'});
    expect((notes['comments'] as List<dynamic>).first['locator'], 'JHN 3:16');

    // Errors come back as exceptions, and the engine carries on afterwards
    await expectLater(engine.request({'command': 'read', 'edition': 'OET-RV', 'passage': 'JHN 99'}), throwsA(isA<EngineException>()));
    expect((await engine.request({'command': 'info'}))['modules'], isNotEmpty);
  }, skip: ready ? false : 'the engine library or the modules have not been built');

  test('names books in English and Spanish', () {
    expect(Strings(const Locale('en')).passage('JHN', 3), 'John 3');
    expect(Strings(const Locale('es', 'MX')).passage('JHN', 0), 'Juan: Introducción');
    expect(Strings(const Locale('en')).book('XYZ'), 'XYZ');
    expect(Strings(const Locale('es')).reference('JN1 4:7-21'), '1 Juan 4:7-21');
    expect(Strings(const Locale('en')).reference('Themes Love'), 'Themes Love');
  });
}
