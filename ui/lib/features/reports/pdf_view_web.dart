// This file is only ever compiled into the web build (conditional import).
// Ported from Prima Volta — adapted package name.
// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:html' as html;
import 'dart:typed_data';
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';

/// Renders PDF [pdfBytes] in the context panel via the browser's native PDF
/// viewer, embedded in an <iframe> over a blob: object URL. This is how deck
/// slides are shown faithfully (the backend converts the .pptx into this PDF
/// on demand).
class PdfView extends StatefulWidget {
  final List<int> pdfBytes;
  const PdfView({super.key, required this.pdfBytes});

  @override
  State<PdfView> createState() => _PdfViewState();
}

int _seq = 0;

class _PdfViewState extends State<PdfView> {
  late final String _viewType;
  String? _objectUrl;

  @override
  void initState() {
    super.initState();
    _viewType = 'nsight-pdf-view-${_seq++}';
    final blob = html.Blob(
      <Object>[Uint8List.fromList(widget.pdfBytes)],
      'application/pdf',
    );
    _objectUrl = html.Url.createObjectUrlFromBlob(blob);
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (int viewId) {
      return html.IFrameElement()
        ..src = '$_objectUrl#toolbar=0&navpanes=0'
        ..style.width = '100%'
        ..style.height = '100%'
        ..style.border = 'none';
    });
  }

  @override
  void dispose() {
    final url = _objectUrl;
    if (url != null) html.Url.revokeObjectUrl(url);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => HtmlElementView(viewType: _viewType);
}
