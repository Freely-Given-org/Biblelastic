/// The engine in a browser: WebAssembly in a worker, with the modules in the browser's own storage (see web/biblelastic.js).
library;

import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

import 'engine.dart';

@JS('JSON.stringify')
external JSString _stringify(JSAny? value);

Engine createEngine() => WebEngine();

class WebEngine implements Engine {
  late final JSObject _engine;

  dynamic _toDart(JSAny? value) => jsonDecode(_stringify(value).toDart);

  @override
  Future<void> start() async {
    final module = await importModule(Uri.base.resolve('engine/biblelastic.js').toString().toJS).toDart;
    _engine = await module.getProperty<JSObject>('Biblelastic'.toJS).callMethod<JSPromise<JSObject>>('start'.toJS).toDart;
  }

  @override
  Future<Map<String, dynamic>> request(Map<String, String> fields) async {
    final answer = _toDart(await _engine.callMethod<JSPromise<JSAny?>>('request'.toJS, fields.jsify()).toDart) as Map<String, dynamic>;
    return checked(answer['response'] as Map<String, dynamic>);
  }

  @override
  Future<List<ModuleInfo>> installed() async {
    final modules = _toDart(await _engine.callMethod<JSPromise<JSAny?>>('list'.toJS).toDart) as List<dynamic>;
    return [for (final module in modules) ModuleInfo(module['name'] as String, (module['bytes'] as num).toInt())];
  }

  @override
  Future<void> install(String name, Uri url, void Function(int written)? onProgress) async {
    final progress = ((JSObject progress) => onProgress?.call(progress.getProperty<JSNumber>('written'.toJS).toDartInt)).toJS;
    await _engine.callMethod<JSPromise<JSAny?>>('install'.toJS, name.toJS, url.toString().toJS, progress).toDart;
  }

  @override
  Future<void> remove(List<String> names) async {
    await _engine.callMethod<JSPromise<JSAny?>>('remove'.toJS, names.jsify()).toDart;
  }

  @override
  Future<void> removeAll() async {
    await _engine.callMethod<JSPromise<JSAny?>>('remove'.toJS).toDart;
  }
}
