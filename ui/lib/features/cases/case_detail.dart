// Detail pane shown when a case is selected. REQ-U-04.
// Renders a case-name header and two fixed tabs: Data (Task 8.5) and Reports (Task 8.6).
//
// Extension point: when the dynamic report-builder is implemented (Tasks 8.6+),
// increase DefaultTabController length and add open-report tabs after "Reports".

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/data_area.dart';
import 'providers/selected_case_provider.dart';

/// Detail pane for the selected case.
///
/// Reads [selectedCaseProvider]; the shell guarantees this is non-null when
/// [CaseDetail] is shown, so the `!` assertion below is safe.
///
/// Tab 0 — "Data"    : placeholder; real Data browser implemented in Task 8.5.
/// Tab 1 — "Reports" : placeholder; real Reports tab implemented in Task 8.6.
// TODO(8.6+): add dynamic open-report tabs after "Reports" by extending
// DefaultTabController.length and appending entries to tabs / children.
class CaseDetail extends ConsumerWidget {
  const CaseDetail({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Safe: AppShell only renders CaseDetail when selectedCaseProvider != null.
    final caseRecord = ref.watch(selectedCaseProvider)!;

    return DefaultTabController(
      length: 2, // fixed tabs: Data + Reports
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Text(
              caseRecord.name,
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(fontWeight: FontWeight.w600),
            ),
          ),
          const TabBar(
            tabs: [
              Tab(text: 'Data'),
              Tab(text: 'Reports'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                DataArea(caseId: caseRecord.id),              // Task 8.5
                const Center(child: Text('Reports area')),    // Task 8.6
              ],
            ),
          ),
        ],
      ),
    );
  }
}
