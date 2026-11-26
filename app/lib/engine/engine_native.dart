/// The engine as a native library (crates/biblelastic-ffi), called directly.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:isolate';

import 'package:crypto/crypto.dart' as crypto;
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
  late final SendPort _worker;
  final Map<int, Completer<String>> _waiting = {};
  int _nextId = 0;

  /// The engine is called from an isolate of its own, so that a slow request never holds the display up
  @override
  Future<void> start() async {
    _folder = modulesFolder ?? Directory('${(await getApplicationSupportDirectory()).path}/modules');
    await _folder.create(recursive: true);
    final library = libraryPath ?? (Platform.isWindows ? 'biblelastic.dll' : Platform.isMacOS ? 'libbiblelastic.dylib' : 'libbiblelastic.so');
    final answers = ReceivePort();
    final ready = Completer<SendPort>();
    answers.listen((message) {
      if (message is SendPort) return ready.complete(message);
      final (id, answer) = message as (int, String);
      _waiting.remove(id)?.complete(answer);
    });
    await Isolate.spawn(_serve, (answers.sendPort, library, _folder.path));
    _worker = await ready.future;
  }

  /// Runs in the engine's isolate: answers each (id, request) that arrives with (id, answer)
  static void _serve((SendPort, String, String) setup) {
    final (answers, libraryName, folderPath) = setup;
    final library = DynamicLibrary.open(libraryName);
    final request = library.lookupFunction<_RequestNative, _RequestDart>('biblelastic_request');
    final free = library.lookupFunction<_FreeNative, _FreeDart>('biblelastic_free');
    final requests = ReceivePort();
    answers.send(requests.sendPort);
    requests.listen((message) {
      final (id, text) = message as (int, String);
      final folder = folderPath.toNativeUtf8(), words = text.toNativeUtf8();
      final answer = request(folder, words, 0);
      try {
        answers.send((id, answer.toDartString()));
      } finally {
        free(answer);
        malloc.free(folder);
        malloc.free(words);
      }
    });
  }

  Future<String> _call(String text) {
    final id = _nextId++;
    final answer = _waiting[id] = Completer<String>();
    _worker.send((id, text));
    return answer.future;
  }

  @override
  Future<Map<String, dynamic>> request(Map<String, String> fields) async {
    final answer = jsonDecode(await _call(fields.entries.map((field) => '${field.key}=${field.value}').join('\n'))) as Map<String, dynamic>;
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
  Future<void> install(String name, Uri url, void Function(int written)? onProgress, {String sha256 = ''}) async {
    // The partial file is named for the version being downloaded, so that a try that carries on never mixes two versions
    final version = sha256.isEmpty ? 'unknown' : sha256.substring(0, 16);
    final partial = File('${_folder.path}/$name.$version.part');
    await for (final file in _folder.list()) { // Partial downloads of other versions
      final fileName = file.uri.pathSegments.last;
      if (file is File && fileName.startsWith('$name.') && fileName.endsWith('.part') && file.path != partial.path) await file.delete();
    }
    for (var attempt = 1;; attempt++) {
      try {
        await _download(name, url, partial, onProgress);
        break;
      } on _Hopeless {
        if (await partial.exists()) await partial.delete();
        rethrow;
      } catch (error) {
        if (attempt >= downloadTries) throw EngineException("$name couldn't be downloaded ($error). Try again to carry on from where it stopped.");
        await Future<void>.delayed(retryDelay(attempt));
      }
    }
    if (sha256.isNotEmpty) {
      final digest = await crypto.sha256.bind(partial.openRead()).first;
      if ('$digest' != sha256) {
        await partial.delete();
        throw EngineException("$name didn't download correctly (its SHA-256 isn't the catalogue's), so it wasn't installed. Try again.");
      }
    }
    await _call('command=forget'); // So that the engine looks at the folder again (and lets go of the old copy)
    await partial.rename('${_folder.path}/$name.blm');
  }

  /// One try at downloading into the partial file: carrying on from its end if the server can send the rest
  Future<void> _download(String name, Uri url, File partial, void Function(int written)? onProgress) async {
    final client = http.Client();
    try {
      final have = await partial.exists() ? await partial.length() : 0;
      final request = http.Request('GET', url);
      if (have > 0) request.headers['Range'] = 'bytes=$have-';
      final response = await client.send(request).timeout(const Duration(seconds: 30));
      if (response.statusCode == 416 && have > 0) return; // It has it all already
      if (response.statusCode != 200 && response.statusCode != 206) {
        final message = "$name couldn't be downloaded (HTTP ${response.statusCode})";
        throw hopeless(response.statusCode) ? _Hopeless(message) : EngineException(message);
      }
      final carryOn = response.statusCode == 206; // Otherwise the server sent it all again
      final sink = partial.openWrite(mode: carryOn ? FileMode.append : FileMode.write);
      var written = carryOn ? have : 0;
      onProgress?.call(written);
      try {
        // (A connection that stops sending is given up on after a while, and tried again)
        await for (final chunk in response.stream.timeout(const Duration(seconds: 30))) {
          sink.add(chunk);
          written += chunk.length;
          onProgress?.call(written);
        }
      } finally {
        await sink.close();
      }
      final expected = response.contentLength;
      if (expected != null && written != (carryOn ? have : 0) + expected) throw EngineException('$name: the connection closed early');
    } finally {
      client.close();
    }
  }

  @override
  Future<void> remove(List<String> names) async {
    await _call('command=forget');
    for (final name in names) {
      final file = File('${_folder.path}/$name.blm');
      if (await file.exists()) await file.delete();
    }
  }

  @override
  Future<void> removeAll() async {
    await _call('command=forget');
    await for (final file in _folder.list()) {
      if (file is File) await file.delete();
    }
  }
}

/// A download that trying again won't help (e.g., the file isn't there)
class _Hopeless extends EngineException {
  const _Hopeless(super.message);
}
