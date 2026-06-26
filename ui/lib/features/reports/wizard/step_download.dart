// Wizard Step 5 — Download: Generate → render → PDF preview + downloads.
// REQ-C-19 / REQ-C-21 / REQ-C-22

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers/api_provider.dart';
import '../../../core/services/nsight_api.dart';
import '../../../core/utils/download_file.dart';
import '../../data/providers/material_provider.dart';
import '../pdf_view.dart' if (dart.library.html) '../pdf_view_web.dart';
import '../providers/builder_provider.dart';

// ---------------------------------------------------------------------------
// DownloadStep
// ---------------------------------------------------------------------------

/// Step 5 of the wizard: Generate → render → PDF preview + download buttons.
///
/// Flow:
/// 1. "Generate" button → [saveReport] then [render].
/// 2. On success: fetches the PDF bytes via [getPreviewPdf] and shows [PdfView].
/// 3. "Download PDF" button: hands bytes to the browser save-as dialog.
/// 4. "Download PowerPoint" button: fetches [getPreviewPptx] bytes and hands
///    them to the browser save-as dialog via [downloadFile].
/// 5. Errors are shown as a banner; spinner while rendering. (REQ-C-19)
class DownloadStep extends ConsumerStatefulWidget {
  const DownloadStep({
    super.key,
    required this.caseId,
    required this.reportId,
  });

  final String caseId;
  final String reportId;

  @override
  ConsumerState<DownloadStep> createState() => _DownloadStepState();
}

class _DownloadStepState extends ConsumerState<DownloadStep> {
  bool _generating = false;
  bool _downloadingPptx = false;
  String? _error;
  List<int>? _pdfBytes;

  Future<void> _generate() async {
    setState(() {
      _generating = true;
      _error = null;
      _pdfBytes = null;
    });
    try {
      final api = ref.read(nsightApiProvider);
      final materialId = ref.read(activeMaterialProvider);

      // 1. Save the report first so the backend has the latest draft.
      await ref
          .read(builderProvider.notifier)
          .save(widget.caseId, widget.reportId);

      // 2. Render (PPTX → PDF → rasterise).
      if (materialId == null) {
        throw const NsightApiException(
            400, 'No material selected. Upload a data file first.');
      }
      await api.render(widget.caseId, widget.reportId, materialId);

      // 3. Fetch the rendered PDF.
      final pdf = await api.getPreviewPdf(widget.caseId, widget.reportId);
      if (mounted) setState(() { _pdfBytes = pdf; _generating = false; });
    } on NsightApiException catch (e) {
      if (mounted) setState(() { _error = e.detail; _generating = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _generating = false; });
    }
  }

  void _downloadPdf() {
    final bytes = _pdfBytes;
    if (bytes == null) return;
    downloadFile(Uint8List.fromList(bytes), 'report.pdf');
  }

  Future<void> _downloadPptx() async {
    setState(() => _downloadingPptx = true);
    try {
      final bytes = await ref
          .read(nsightApiProvider)
          .getPreviewPptx(widget.caseId, widget.reportId);
      downloadFile(bytes, 'report.pptx');
    } on NsightApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PPTX download failed: ${e.detail}')),
        );
      }
    } finally {
      if (mounted) setState(() => _downloadingPptx = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasPdf = _pdfBytes != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── Header / action bar ──────────────────────────────────────────────
        Container(
          color: theme.colorScheme.surfaceContainerHighest,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.download_rounded, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Generate & Download',
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                ],
              ),
              // Generate button
              FilledButton.icon(
                key: const Key('generate_button'),
                onPressed: _generating ? null : _generate,
                icon: _generating
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.play_arrow),
                label: Text(_generating ? 'Generating…' : 'Generate'),
              ),
              if (hasPdf) ...[
                OutlinedButton.icon(
                  key: const Key('download_pdf_button'),
                  onPressed: _downloadPdf,
                  icon: const Icon(Icons.picture_as_pdf),
                  label: const Text('Download PDF'),
                ),
                OutlinedButton.icon(
                  key: const Key('download_pptx_button'),
                  onPressed: _downloadingPptx ? null : _downloadPptx,
                  icon: _downloadingPptx
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.slideshow),
                  label: const Text('Download PowerPoint'),
                ),
              ],
            ],
          ),
        ),
        const Divider(height: 1),

        // ── Error banner ─────────────────────────────────────────────────────
        if (_error != null)
          MaterialBanner(
            key: const Key('download_error_banner'),
            content: Text(_error!),
            backgroundColor: theme.colorScheme.errorContainer,
            leading: Icon(Icons.error_outline,
                color: theme.colorScheme.onErrorContainer),
            actions: [
              TextButton(
                onPressed: () => setState(() => _error = null),
                child: const Text('Dismiss'),
              ),
            ],
          ),

        // ── PDF view / placeholder ────────────────────────────────────────────
        Expanded(
          child: _generating
              ? const Center(
                  key: Key('generating_indicator'),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 16),
                      Text('Rendering…'),
                    ],
                  ),
                )
              : hasPdf
                  ? PdfView(
                      key: const Key('download_pdf_view'),
                      pdfBytes: _pdfBytes!,
                    )
                  : Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.picture_as_pdf_outlined,
                            size: 56,
                            color: theme.colorScheme.onSurface
                                .withValues(alpha: 0.2),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            'Press Generate to build your report.',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.onSurface
                                  .withValues(alpha: 0.55),
                            ),
                          ),
                        ],
                      ),
                    ),
        ),
      ],
    );
  }
}
