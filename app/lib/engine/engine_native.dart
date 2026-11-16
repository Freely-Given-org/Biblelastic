/// The engine as a native library (crates/biblelastic-ffi), called directly.
library;

import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'engine.dart';

typedef _RequestNative = Pointer<Utf8> Function(Pointer<Utf8> folder, Pointer<Utf8> request, IntPtr cacheBytes);
typedef _RequestDart = Pointer<Utf8> Function(Pointer<Utf8> folder, Pointer<Utf8> request, int cacheBytes);
typedef _FreeNative = Void Function(Pointer<Utf8> text);
typedef _FreeDart = void Function(Pointer<Utf8> text);

Engine createEngine() => NativeEngine();

class NativeEngine implements Engine {
  /// For tests: a particular copy of the library, and a particular folder of modules
  NativeEngine({this.libraryPath, this.modulesFolder});
  final String? libraryPath;
  final Directory? modulesFolder;

  late final Directory _folder;
  late final _RequestDart _request;
  late final _FreeDart _free;

  @override
  Future<void> start() async {
    final library = DynamicLibrary.open(libraryPath ?? (Platform.isWindows ? 'biblelastic.dll' : Platform.isMacOS ? 'libbiblelastic.dylib' : 'libbiblelastic.so'));
    _request = library.lookupFunction<_RequestNative, _RequestDart>('biblelastic_request');
    _free = library.lookupFunction<_FreeNative, _FreeDart>('biblelastic_free');
    _folder = modulesFolder ?? Directory('${(await getApplicationSupportDirectory()).path}/modules');
    await _folder.create(recursive: true);
  }

  // The engine is called on the app's own thread for now. Requests take milliseconds,
  // but a slow one would hold the display up: it should move to its own isolate.
  String _call(String text) {
    final folder = _folder.path.toNativeUtf8();
    final request = text.toNativeUtf8();
    final answer = _request(folder, request, 0);
    try {
      return answer.toDartString();
    } finally {
      _free(answer);
      malloc.free(folder);
      malloc.free(request);
    }
  }

  @override
  Future<Map<String, dynamic>> request(Map<String, String> fields) async {
    final answer = jsonDecode(_call(fields.entries.map((field) => '${field.key}=${field.value}').join('\n'))) as Map<String, dynamic>;
    return checked(answer['response'] as Map<String, dynamic>);
  }

  @override
  Future<List<ModuleInfo>> installed() async {
    final modules = <ModuleInfo>[];
    await for (final file in _folder.list()) {
      final name = file.uri.pathSegments.last;
      if (file is File && name.endsWith('.blm')) modules.add(ModuleInfo(name.substring(0, name.length - 4), await file.length()));
    }
    modules.sort((a, b) => a.name.compareTo(b.name));
    return modules;
  }

  @override
  Future<void> install(String name, Uri url, void Function(int written)? onProgress) async {
    final client = http.Client();
    final partial = File('${_folder.path}/$name.part'); // Only given its real name once it's complete
    try {
      final response = await client.send(http.Request('GET', url));
      if (response.statusCode != 200) throw EngineException("$name couldn't be downloaded (HTTP ${response.statusCode})");
      final sink = partial.openWrite();
      var written = 0;
      await for (final chunk in response.stream) {
        sink.add(chunk);
        written += chunk.length;
        onProgress?.call(written);
      }
      await sink.close();
      await partial.rename('${_folder.path}/$name.blm');
    } finally {
      client.close();
      if (await partial.exists()) await partial.delete();
    }
    _call('command=forget'); // So that the engine looks at the folder again
  }

  @override
  Future<void> removeAll() async {
    _call('command=forget');
    await for (final file in _folder.list()) {
      if (file is File) await file.delete();
    }
  }
}
