// Dialog for creating a new report: name only (image mode is always used).
// REQ-U-06 / D-06

import 'package:flutter/material.dart';

/// Dialog that collects a report [name].
///
/// Always uses [renderMode] = 'image' (native rendering is dropped in W4 / D-06).
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
      content: TextField(
        controller: _nameController,
        autofocus: true,
        decoration: const InputDecoration(labelText: 'Name'),
        onChanged: (_) => setState(() {}),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: canCreate
              ? () => Navigator.of(context)
                  .pop((_nameController.text.trim(), 'image'))
              : null,
          child: const Text('Create'),
        ),
      ],
    );
  }
}
