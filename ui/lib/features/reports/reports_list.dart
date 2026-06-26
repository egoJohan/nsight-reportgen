// Reports tab body: session-scoped list with add / duplicate / delete.
// REQ-U-06 / REQ-C-07 / REQ-C-09.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'new_report_dialog.dart';
import 'providers/reports_provider.dart';

/// The body of the "Reports" tab.
///
/// Lists the session-scoped [ReportSummary] items. An "Add report" button
/// opens [NewReportDialog] → [ReportsNotifier.create]. Each row exposes:
///   • duplicate — prompts for a new name → [ReportsNotifier.duplicate]
///   • delete    — [ReportsNotifier.remove]
///
/// Tapping a row sets [selectedReportProvider] so the report builder
/// (Task 8.7) can open the selected report.
class ReportsList extends ConsumerWidget {
  const ReportsList({super.key, required this.caseId});

  /// The case this Reports list belongs to.
  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reports = ref.watch(reportsProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Align(
            alignment: Alignment.centerRight,
            child: ElevatedButton.icon(
              onPressed: () => _addReport(context, ref),
              icon: const Icon(Icons.add),
              label: const Text('Add report'),
            ),
          ),
        ),
        Expanded(
          child: reports.isEmpty
              ? const Center(child: Text('No reports yet.'))
              : ListView.builder(
                  itemCount: reports.length,
                  itemBuilder: (context, i) {
                    final r = reports[i];
                    return ListTile(
                      key: ValueKey(r.id),
                      title: Text(r.name),
                      subtitle: Text(r.renderMode),
                      onTap: () => ref
                          .read(selectedReportProvider.notifier)
                          .select(r.id),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            icon: const Icon(Icons.copy),
                            tooltip: 'Duplicate',
                            onPressed: () =>
                                _duplicateReport(context, ref, r.id, r.name),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete),
                            tooltip: 'Delete',
                            onPressed: () => ref
                                .read(reportsProvider.notifier)
                                .remove(caseId, r.id),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Future<void> _addReport(BuildContext context, WidgetRef ref) async {
    final result = await showDialog<(String, String)>(
      context: context,
      builder: (_) => const NewReportDialog(),
    );
    if (result == null) return;
    final (name, renderMode) = result;
    if (!context.mounted) return;
    await ref.read(reportsProvider.notifier).create(caseId, name, renderMode);
  }

  Future<void> _duplicateReport(
    BuildContext context,
    WidgetRef ref,
    String reportId,
    String originalName,
  ) async {
    final newName = await showDialog<String>(
      context: context,
      builder: (_) => _DuplicateDialog(initialName: '$originalName copy'),
    );
    if (newName == null || newName.isEmpty) return;
    if (!context.mounted) return;
    await ref
        .read(reportsProvider.notifier)
        .duplicate(caseId, reportId, newName);
  }
}

// ---------------------------------------------------------------------------
// Private duplicate-name dialog
// ---------------------------------------------------------------------------

/// Simple dialog that prompts for a name when duplicating a report.
///
/// Uses a [StatefulWidget] so the [TextEditingController] is disposed cleanly
/// in [State.dispose] — avoiding "dirty widget in wrong scope" errors that
/// occur when the controller is disposed externally during the close animation.
class _DuplicateDialog extends StatefulWidget {
  const _DuplicateDialog({required this.initialName});

  final String initialName;

  @override
  State<_DuplicateDialog> createState() => _DuplicateDialogState();
}

class _DuplicateDialogState extends State<_DuplicateDialog> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialName);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Duplicate report'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        decoration: const InputDecoration(labelText: 'New name'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: () =>
              Navigator.of(context).pop(_controller.text.trim()),
          child: const Text('Duplicate'),
        ),
      ],
    );
  }
}
