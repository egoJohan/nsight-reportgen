// Dialog for creating a new case.
// REQ-C-03

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'providers/cases_provider.dart';

/// Modal dialog with a name text field + Create / Cancel actions.
///
/// On Create: calls [CasesNotifier.create] and closes. The Create button is
/// disabled while the name is empty or a request is in flight.
class NewCaseDialog extends ConsumerStatefulWidget {
  const NewCaseDialog({super.key});

  @override
  ConsumerState<NewCaseDialog> createState() => _NewCaseDialogState();
}

class _NewCaseDialogState extends ConsumerState<NewCaseDialog> {
  final _controller = TextEditingController();
  bool _loading = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canCreate = _controller.text.trim().isNotEmpty && !_loading;

    return AlertDialog(
      title: const Text('New case'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        decoration: const InputDecoration(labelText: 'Case name'),
        onChanged: (_) => setState(() {}),
        onSubmitted: canCreate ? (_) => _create() : null,
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        TextButton(
          onPressed: canCreate ? _create : null,
          child: const Text('Create'),
        ),
      ],
    );
  }

  Future<void> _create() async {
    final name = _controller.text.trim();
    setState(() => _loading = true);
    try {
      await ref.read(casesProvider.notifier).create(name);
      if (mounted) Navigator.of(context).pop();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
}
