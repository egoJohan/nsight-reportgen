// Data area: upload a .sav material and browse its questions.
// REQ-U-05 / REQ-C-01 / REQ-C-04 / REQ-C-05 / REQ-C-06 / REQ-C-26.

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/services/nsight_api.dart';
import 'providers/material_provider.dart';
import 'question_browser.dart';

/// The body of the "Data" tab.
///
/// * No active material → shows an "Upload .sav" button. (REQ-C-01)
/// * Active material → shows a sort dropdown and [QuestionBrowser]. (REQ-U-05)
class DataArea extends ConsumerStatefulWidget {
  const DataArea({super.key, required this.caseId});

  /// The case this Data area belongs to (used when uploading a material).
  final String caseId;

  @override
  ConsumerState<DataArea> createState() => _DataAreaState();
}

class _DataAreaState extends ConsumerState<DataArea> {
  QuestionSortMode _sortMode = QuestionSortMode.textAZ;
  bool _uploading = false;

  @override
  Widget build(BuildContext context) {
    final materialId = ref.watch(activeMaterialProvider);

    if (materialId == null) {
      // REQ-C-01 — no active material: prompt the user to upload.
      return Center(
        child: _uploading
            ? const CircularProgressIndicator()
            : ElevatedButton.icon(
                onPressed: _pickAndUpload,
                icon: const Icon(Icons.upload_file),
                label: const Text('Upload .sav'),
              ),
      );
    }

    // Material active: sort dropdown + explainer + question browser.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              const Text('Sort by:'),
              const SizedBox(width: 8),
              DropdownButton<QuestionSortMode>(
                value: _sortMode,
                items: const [
                  DropdownMenuItem(
                    value: QuestionSortMode.textAZ,
                    child: Text('Question text A–Z'),
                  ),
                  DropdownMenuItem(
                    value: QuestionSortMode.byKind,
                    child: Text('Kind'),
                  ),
                ],
                onChanged: (v) {
                  if (v != null) setState(() => _sortMode = v);
                },
              ),
            ],
          ),
        ),
        // W4.2 / D-06 — explainer + "i" tooltip for auto-detected kind.
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  'Questions are auto-detected as Single (one answer) or '
                  'Multi (a tick-box set reported together).',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ),
              const SizedBox(width: 4),
              Tooltip(
                message: 'Single: one survey variable, one response per '
                    'respondent.\n'
                    'Multi: several yes/no tick-boxes treated as one '
                    'question.\n'
                    'Grouping is detected automatically from the SPSS file.',
                child: Icon(
                  Icons.info_outline,
                  size: 16,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
        Expanded(child: QuestionBrowser(sortMode: _sortMode)),
      ],
    );
  }

  Future<void> _pickAndUpload() async {
    FilePickerResult? result;
    try {
      result = await FilePicker.platform.pickFiles(
        withData: true,
        type: FileType.custom,
        allowedExtensions: ['sav', 'zsav'],
      );
    } catch (_) {
      // Picker unavailable (e.g. headless test environment) — bail silently.
      return;
    }

    if (result == null) return;
    final file = result.files.single;
    if (file.bytes == null) return;

    setState(() => _uploading = true);
    try {
      await ref.read(activeMaterialProvider.notifier).upload(
            widget.caseId,
            file.bytes!,
            file.name,
          );
    } on NsightApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Upload failed: ${e.detail}')),
      );
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }
}
