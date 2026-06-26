// Non-web stub: the in-panel PDF viewer is web-only (uses an <iframe>).
// Ported from Prima Volta — adapted package name.
import 'package:flutter/material.dart';

/// Renders PDF bytes. On the VM test platform (non-web) this is a
/// placeholder; on the web build [pdf_view_web.dart] is compiled instead
/// via the conditional-import pattern.
class PdfView extends StatelessWidget {
  final List<int> pdfBytes;
  const PdfView({super.key, required this.pdfBytes});

  @override
  Widget build(BuildContext context) => const Center(
        key: Key('pdf_view_stub'),
        child: Text('PDF viewer (web only)'),
      );
}
