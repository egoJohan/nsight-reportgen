// Report preview panel: Render button + Slides/Pages toggle + PdfView.
// REQ-C-19a / REQ-C-19b / REQ-C-21 / REQ-C-22.

// Conditional import: on web the full iframe-based PdfView is compiled in;
// on other platforms (VM, desktop) the non-web stub is used — which is why
// widget tests work without a browser.
import 'pdf_view.dart' if (dart.library.html) 'pdf_view_web.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers/api_provider.dart';
import '../../core/services/nsight_api.dart';
import '../data/providers/material_provider.dart';

/// Preview panel for a rendered report.
///
/// Displays a [SegmentedButton] toggling between 'Slides (PPT)' and
/// 'Pages (PDF)' views (REQ-C-19a/b), a Render button (REQ-C-21), and —
/// once bytes are available — a [PdfView] of the PDF artifact (REQ-C-22).
class ReportPreview extends ConsumerStatefulWidget {
  const ReportPreview({
    super.key,
    required this.caseId,
    required this.reportId,
  });

  final String caseId;
  final String reportId;

  @override
  ConsumerState<ReportPreview> createState() => _ReportPreviewState();
}

class _ReportPreviewState extends ConsumerState<ReportPreview> {
  /// Current view mode — 'slides' or 'pages'. (REQ-C-19a/b)
  String _view = 'slides';

  /// PDF bytes from the last successful render. (REQ-C-22)
  List<int>? _pdfBytes;

  /// True while a render is in progress. (REQ-C-21)
  bool _rendering = false;

  // ── Render ────────────────────────────────────────────────────────────────

  Future<void> _render() async {
    final messenger = ScaffoldMessenger.of(context);
    final materialId = ref.read(activeMaterialProvider);
    if (materialId == null) {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Select a material in Data first.'),
        ),
      );
      return;
    }

    setState(() {
      _rendering = true;
      _pdfBytes = null;
    });

    try {
      final api = ref.read(nsightApiProvider);
      // REQ-C-21 — POST /render to produce the deck.
      await api.render(
        widget.caseId,
        widget.reportId,
        materialId,
        view: _view,
      );
      // REQ-C-22 — fetch the resulting PDF.
      final bytes = await api.getPreviewPdf(widget.caseId, widget.reportId);
      if (!mounted) return;
      setState(() => _pdfBytes = bytes);
    } on NsightApiException catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(
        SnackBar(content: Text('Render failed: ${e.detail}')),
      );
    } finally {
      if (mounted) setState(() => _rendering = false);
    }
  }

  // ── View-toggle ───────────────────────────────────────────────────────────

  void _onViewChanged(String newView) {
    setState(() {
      _view = newView;
      _pdfBytes = null; // clear stale bytes; re-render with new view
    });
    _render();
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── Controls bar ──────────────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Wrap(
            alignment: WrapAlignment.start,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              // Slides / Pages toggle (REQ-C-19a/b)
              SegmentedButton<String>(
                key: const Key('view_toggle'),
                segments: const [
                  ButtonSegment(
                    value: 'slides',
                    label: Text('Slides (PPT)'),
                  ),
                  ButtonSegment(
                    value: 'pages',
                    label: Text('Pages (PDF)'),
                  ),
                ],
                selected: {_view},
                onSelectionChanged: (sel) => _onViewChanged(sel.first),
              ),

              // Render button (REQ-C-21)
              ElevatedButton.icon(
                key: const Key('render_preview_button'),
                onPressed: _rendering ? null : _render,
                icon: _rendering
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.play_arrow),
                label: const Text('Render'),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        // ── Content area ──────────────────────────────────────────────────
        Expanded(
          child: _rendering
              ? const Center(child: CircularProgressIndicator())
              : _pdfBytes != null
                  ? PdfView(
                      key: const Key('pdf_view'),
                      pdfBytes: _pdfBytes!,
                    )
                  : const Center(
                      key: Key('render_to_preview_placeholder'),
                      child: Text('Render to preview'),
                    ),
        ),
      ],
    );
  }
}
