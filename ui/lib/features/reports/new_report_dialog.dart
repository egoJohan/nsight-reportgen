// Dialog for creating a new report: name + render-mode selector.
// REQ-U-06

import 'package:flutter/material.dart';

/// Dialog that collects a report [name] and [renderMode] ('native' or 'image').
///
/// Pops with a `(String name, String renderMode)` record when the user taps
/// Create, or with null when the user cancels.
///
/// The Create button is disabled until the name field is non-empty.
class NewReportDialog extends StatefulWidget {
  const NewReportDialog({super.key});

  @override
  State<NewReportDialog> createState() => _NewReportDialogState();
}

class _NewReportDialogState extends State<NewReportDialog> {
  final _nameController = TextEditingController();
  String _renderMode = 'native';

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canCreate = _nameController.text.trim().isNotEmpty;

    return AlertDialog(
      title: const Text('New report'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _nameController,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Name'),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 16),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'native', label: Text('native')),
              ButtonSegment(value: 'image', label: Text('image')),
            ],
            selected: {_renderMode},
            onSelectionChanged: (sel) =>
                setState(() => _renderMode = sel.first),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: canCreate
              ? () => Navigator.of(context)
                  .pop((_nameController.text.trim(), _renderMode))
              : null,
          child: const Text('Create'),
        ),
      ],
    );
  }
}
