/// The Biblelastic engine, as the app sees it. The same Rust engine is behind it everywhere:
/// a native library on phones and desktops, and WebAssembly in a worker in browsers.
library;

import 'engine_stub.dart' if (dart.library.ffi) 'engine_native.dart' if (dart.library.js_interop) 'engine_web.dart';

class ModuleInfo {
  const ModuleInfo(this.name, this.bytes);
  final String name;
  final int bytes;
}

/// The engine answered a request with an error (e.g., a module that's needed isn't installed)
class EngineException implements Exception {
  const EngineException(this.message);
  final String message;
  @override
  String toString() => message;
}

abstract class Engine {
  /// The engine for this platform (not yet started)
  factory Engine() => createEngine();

  Future<void> start();

  /// Ask the engine something, e.g., `{'command': 'read', 'passage': 'JHN 3'}` (see the engine's api.rs).
  /// Gives the response, or throws an [EngineException].
  Future<Map<String, dynamic>> request(Map<String, String> fields);

  Future<List<ModuleInfo>> installed();

  /// Download one module file. [onProgress] is told how many bytes have been stored so far.
  /// It's downloaded into a partial file first, which a later try carries on from if the connection is lost (and it's tried a few times by itself);
  /// if [sha256] is given (the catalogue's), the module is only installed if its SHA-256 is the same.
  Future<void> install(String name, Uri url, void Function(int written)? onProgress, {String sha256 = ''});

  /// Remove these modules (by name)
  Future<void> remove(List<String> names);

  Future<void> removeAll();
}

/// Checks a response from the engine
Map<String, dynamic> checked(Map<String, dynamic> response) {
  if (response['ok'] != true) throw EngineException('${response['error'] ?? 'The engine gave no answer'}');
  return response;
}

/// How many times a download is tried (carrying on from where it stopped) before giving up, and how long to wait before each try after the first
const downloadTries = 6;
Duration retryDelay(int attempt) => Duration(seconds: 1 << (attempt - 1)); // 1, 2, 4, 8, 16 s

/// Whether an HTTP status means that trying again won't help (e.g., 404), as against a server that's busy or a request that timed out
bool hopeless(int status) => status >= 400 && status < 500 && status != 408 && status != 429;
