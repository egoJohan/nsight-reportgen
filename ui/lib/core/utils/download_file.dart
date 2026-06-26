// Conditional export: on web the browser-download implementation is compiled in;
// on other platforms (VM tests, desktop) the no-op stub is used.
// ignore_for_file: uri_does_not_exist
export 'download_file_stub.dart'
    if (dart.library.html) 'download_file_web.dart';
