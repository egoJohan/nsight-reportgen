// Widget that lists cases and provides a button to create new ones.
// REQ-U-04 / REQ-C-07

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import 'new_case_dialog.dart';
import 'providers/cases_provider.dart';
import 'providers/selected_case_provider.dart';

/// Displays the list of cases from [casesProvider].
///
/// Loading → [CircularProgressIndicator].
/// Error   → inline error message.
/// Data    → [ListView] of tappable case-name rows.
///
/// The "Add case" [IconButton] in the header opens [NewCaseDialog].
/// [onSelect] is an optional callback for when the user taps a case row;
/// the detail pane (Task 8.4) will wire this up.
class CasesList extends ConsumerWidget {
  const CasesList({super.key, this.onSelect});

  final void Function(CaseRecord)? onSelect;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final casesAsync = ref.watch(casesProvider);

    return casesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (err, _) => Center(child: Text('Error: $err')),
      data: (cases) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _CasesHeader(
            onAdd: () => showDialog<void>(
              context: context,
              builder: (_) => const NewCaseDialog(),
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: cases.length,
              itemBuilder: (ctx, i) {
                final selected = ref.watch(selectedCaseProvider);
                final isSelected = selected?.id == cases[i].id;
                return ListTile(
                  title: Text(cases[i].name),
                  selected: isSelected,
                  onTap: () {
                    ref.read(selectedCaseProvider.notifier).select(cases[i]);
                    onSelect?.call(cases[i]);
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _CasesHeader extends StatelessWidget {
  const _CasesHeader({required this.onAdd});

  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          const Expanded(
            child: Text(
              'Cases',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'Add case',
            onPressed: onAdd,
          ),
        ],
      ),
    );
  }
}
