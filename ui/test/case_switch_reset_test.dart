// Tests for FIX-1 (case-switch state reset) and FIX-2 (builder name reset
// when a different report is opened).
//
// FIX-1: selecting a new case must clear selectedReport, builder draft, and
// reports list.
//
// FIX-2: opening report B after report A must show B's name in the name field,
// not A's stale name (the _nameInitialized latch must reset between reports).

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/features/cases/case_detail.dart';
import 'package:nsight_ui/features/cases/providers/selected_case_provider.dart';
import 'package:nsight_ui/features/reports/providers/builder_provider.dart';
import 'package:nsight_ui/features/reports/providers/reports_provider.dart';

// ---------------------------------------------------------------------------
// Fake API
// ---------------------------------------------------------------------------

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  @override
  Future<List<CaseRecord>> listCases() async => [
        const CaseRecord(id: 'c1', name: 'Case One'),
        const CaseRecord(id: 'c2', name: 'Case Two'),
      ];

  @override
  Future<List<QuestionItem>> listQuestions(String materialId) async => [];

  @override
  Future<ReportDef> getReport(String caseId, String reportId) async {
    return switch (reportId) {
      'r1' => const ReportDef(
          name: 'Report Alpha',
          renderMode: 'image',
          templateRef: 'default',
          charts: [],
        ),
      'r2' => const ReportDef(
          name: 'Report Beta',
          renderMode: 'image',
          templateRef: 'default',
          charts: [],
        ),
      _ => const ReportDef(
          name: 'Unknown',
          renderMode: 'native',
          templateRef: 'default',
          charts: [],
        ),
    };
  }

  @override
  Future<void> saveReport(
          String caseId, String reportId, ReportDef def) async {}

  @override
  Future<String> createReport(String caseId, ReportDef def) async => 'new-r';
}

// ---------------------------------------------------------------------------
// Seeded notifiers
// ---------------------------------------------------------------------------

class _SeededCaseNotifier extends SelectedCaseNotifier {
  _SeededCaseNotifier(this._initial);
  final CaseRecord? _initial;

  @override
  CaseRecord? build() => _initial;
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

Widget _harness(_FakeNsightApi fake, {required CaseRecord? selectedCase}) {
  return ProviderScope(
    overrides: [
      nsightApiProvider.overrideWithValue(fake),
      selectedCaseProvider
          .overrideWith(() => _SeededCaseNotifier(selectedCase)),
    ],
    child: const MaterialApp(
      home: Scaffold(body: CaseDetail()),
    ),
  );
}

// ---------------------------------------------------------------------------
// FIX-1 tests
// ---------------------------------------------------------------------------

void main() {
  group('FIX-1: case switch resets dependent providers', () {
    testWidgets(
        'switching to a new case clears selectedReport and builder draft',
        (tester) async {
      final fake = _FakeNsightApi();
      const caseA = CaseRecord(id: 'c1', name: 'Case One');
      const caseB = CaseRecord(id: 'c2', name: 'Case Two');

      await tester.pumpWidget(_harness(fake, selectedCase: caseA));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(CaseDetail)),
      );

      // Simulate state accumulated while using case A.
      // Set a selected report and load the builder directly via provider
      // methods (no UI tap needed for these provider-level assertions).
      container.read(selectedReportProvider.notifier).select('r1');
      await container.read(builderProvider.notifier).load('c1', 'r1');

      expect(container.read(selectedReportProvider), 'r1',
          reason: 'precondition: r1 should be selected');
      expect(container.read(builderProvider)?.name, 'Report Alpha',
          reason: 'precondition: builder should hold Report Alpha');

      // Switch to case B — the CaseDetail listener (FIX-1) should fire.
      container
          .read(selectedCaseProvider.notifier)
          .select(caseB);
      await tester.pumpAndSettle();

      expect(
        container.read(selectedReportProvider),
        isNull,
        reason: 'FIX-1: selectedReport must be cleared on case switch',
      );
      expect(
        container.read(builderProvider),
        isNull,
        reason: 'FIX-1: builder draft must be cleared on case switch',
      );
      expect(
        container.read(reportsProvider),
        isEmpty,
        reason: 'FIX-1: reports list must be cleared on case switch',
      );
    });
  });

  // ---------------------------------------------------------------------------
  // FIX-2 tests
  // ---------------------------------------------------------------------------

  group('FIX-2: builder name field reflects the currently open report', () {
    testWidgets(
        'opening report B after closing report A shows B\'s name in the field',
        (tester) async {
      // The bug (pre-fix): _nameInitialized latch is set from A's stale draft
      // before load(B) runs, so the name field stays on A's name.
      // Fix: back button resets builderProvider; ValueKey creates a fresh
      // widget state for B, so _nameInitialized starts false.

      final fake = _FakeNsightApi();
      const caseA = CaseRecord(id: 'c1', name: 'Case One');

      await tester.pumpWidget(_harness(fake, selectedCase: caseA));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(CaseDetail)),
      );

      // Navigate to the Reports tab so the ConsumerWidget is live.
      await tester.tap(find.text('Reports'));
      await tester.pumpAndSettle();

      // Open report A by setting the provider — CaseDetail's Consumer rebuilds,
      // creates ReportBuilder(key: ValueKey('r1'), ...).
      container.read(selectedReportProvider.notifier).select('r1');
      await tester.pumpAndSettle();

      // Builder should have loaded 'Report Alpha'.
      expect(container.read(builderProvider)?.name, 'Report Alpha');
      expect(
        find.widgetWithText(TextField, 'Report Alpha'),
        findsOneWidget,
        reason: 'name field must show Report Alpha while r1 is open',
      );

      // Tap the back button — resets builder + clears selectedReport (FIX-2).
      await tester.tap(find.byKey(const Key('back_button')));
      await tester.pumpAndSettle();

      expect(container.read(selectedReportProvider), isNull,
          reason: 'back button must clear selectedReport');
      expect(container.read(builderProvider), isNull,
          reason: 'back button must reset builder draft (FIX-2)');

      // Open report B.
      container.read(selectedReportProvider.notifier).select('r2');
      await tester.pumpAndSettle();

      // The name field MUST show B's name, not A's stale name. (FIX-2)
      expect(
        find.widgetWithText(TextField, 'Report Beta'),
        findsOneWidget,
        reason:
            'name field must show Report Beta after switching to r2 (FIX-2)',
      );
      expect(
        find.widgetWithText(TextField, 'Report Alpha'),
        findsNothing,
        reason: 'stale name Report Alpha must not appear when r2 is open',
      );
    });
  });
}
