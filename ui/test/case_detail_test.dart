// Widget tests for CaseDetail — Task 8.4.
// REQ-U-04: selecting a case shows a detail pane with Data and Reports tabs.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/features/cases/case_detail.dart';
import 'package:nsight_ui/features/cases/providers/selected_case_provider.dart';

// ---------------------------------------------------------------------------
// Test-only notifier that seeds a fixed initial value
// ---------------------------------------------------------------------------

/// Subclass of [SelectedCaseNotifier] that pre-seeds [build] with [_initial].
/// Used in tests to set an initial selected case without a round-trip mutation.
class _SeededNotifier extends SelectedCaseNotifier {
  _SeededNotifier(this._initial);
  final CaseRecord? _initial;

  @override
  CaseRecord? build() => _initial;
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

/// Wraps [CaseDetail] with [selectedCaseProvider] pre-seeded to [record].
Widget _detailHarness(CaseRecord? record) {
  return ProviderScope(
    overrides: [
      selectedCaseProvider.overrideWith(() => _SeededNotifier(record)),
    ],
    child: const MaterialApp(
      home: Scaffold(body: CaseDetail()),
    ),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('CaseDetail (REQ-U-04)', () {
    testWidgets('shows case name header and Data + Reports tab labels',
        (tester) async {
      // REQ-U-04 — selecting a case renders its name and the fixed tab bar.
      await tester.pumpWidget(
        _detailHarness(const CaseRecord(id: 'c1', name: 'Acme')),
      );
      await tester.pumpAndSettle();

      // Case name appears as the pane header.
      expect(find.text('Acme'), findsOneWidget);

      // Both fixed tab labels are present.
      expect(find.text('Data'), findsOneWidget);
      expect(find.text('Reports'), findsOneWidget);
    });

    testWidgets('Data tab body is visible by default', (tester) async {
      await tester.pumpWidget(
        _detailHarness(const CaseRecord(id: 'c2', name: 'Beta')),
      );
      await tester.pumpAndSettle();

      // First tab (Data) is active by default.
      expect(find.text('Data area'), findsOneWidget);
    });

    testWidgets('tapping Reports tab shows Reports area', (tester) async {
      await tester.pumpWidget(
        _detailHarness(const CaseRecord(id: 'c3', name: 'Gamma')),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Reports'));
      await tester.pumpAndSettle();

      expect(find.text('Reports area'), findsOneWidget);
    });

    testWidgets('renders without errors for a valid CaseRecord', (tester) async {
      // REQ-U-04 — no exception or assertion error for a normal CaseRecord.
      await tester.pumpWidget(
        _detailHarness(const CaseRecord(id: 'x', name: 'Test Co')),
      );
      await tester.pumpAndSettle();

      expect(find.text('Test Co'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
