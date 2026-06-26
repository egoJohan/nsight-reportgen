// Widget tests for ReportsList — Task 8.6.
// REQ-U-06 / REQ-C-07 / REQ-C-09.

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/features/reports/providers/reports_provider.dart';
import 'package:nsight_ui/features/reports/reports_list.dart';

// ---------------------------------------------------------------------------
// Fake API (REQ-U-06, REQ-C-07, REQ-C-09)
// ---------------------------------------------------------------------------

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  /// Calls captured by [createReport]. (REQ-U-06, REQ-C-07)
  final List<({String caseId, ReportDef def})> createCalls = [];

  /// Calls captured by [duplicateReport]. (REQ-C-09)
  final List<({String caseId, String reportId, String name})> duplicateCalls =
      [];

  int _counter = 0;

  @override
  Future<String> createReport(String caseId, ReportDef def) async {
    createCalls.add((caseId: caseId, def: def));
    return 'report-${++_counter}';
  }

  @override
  Future<String> duplicateReport(
    String caseId,
    String reportId,
    String name,
  ) async {
    duplicateCalls.add((caseId: caseId, reportId: reportId, name: name));
    return 'report-${++_counter}';
  }

  @override
  Future<void> deleteReport(String caseId, String reportId) async {}
}

// ---------------------------------------------------------------------------
// Seeded ReportsNotifier (lets duplicate test skip the create flow)
// ---------------------------------------------------------------------------

class _SeededReportsNotifier extends ReportsNotifier {
  _SeededReportsNotifier(this._initial);
  final List<ReportSummary> _initial;

  @override
  List<ReportSummary> build() => List.of(_initial);
}

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

Widget _harness(
  _FakeNsightApi fake, {
  List<ReportSummary>? initialReports,
}) {
  return ProviderScope(
    overrides: [
      nsightApiProvider.overrideWithValue(fake),
      if (initialReports != null)
        reportsProvider.overrideWith(
          () => _SeededReportsNotifier(initialReports),
        ),
    ],
    child: const MaterialApp(
      home: Scaffold(body: ReportsList(caseId: 'c1')),
    ),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('ReportsList — add report (REQ-U-06, REQ-C-07)', () {
    testWidgets(
        'tapping Add opens dialog; entering name + native mode calls '
        'createReport and shows the new row', (tester) async {
      // REQ-U-06 — the user can create a report from the Reports tab.
      // REQ-C-07 — createReport is called on the API.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // Initially empty.
      expect(find.text('No reports yet.'), findsOneWidget);

      // Open the new-report dialog.
      await tester.tap(find.text('Add report'));
      await tester.pumpAndSettle();

      expect(find.text('New report'), findsOneWidget);

      // Verify both render-mode segments are shown.
      expect(find.text('native'), findsOneWidget);
      expect(find.text('image'), findsOneWidget);

      // Enter a name; Create is disabled while the field is empty (pre-existing
      // behaviour verified by the dialog's own state — we test it implicitly
      // here by only tapping Create after entering text).
      await tester.enterText(find.byType(TextField), 'Q4 Insights');
      await tester.pump();

      // Tap Create (native is already the default selection).
      await tester.tap(find.widgetWithText(TextButton, 'Create'));
      await tester.pumpAndSettle();

      // Dialog dismissed.
      expect(find.text('New report'), findsNothing);

      // API was called with the correct arguments. (REQ-C-07)
      expect(fake.createCalls, hasLength(1));
      expect(fake.createCalls.first.caseId, 'c1');
      expect(fake.createCalls.first.def.name, 'Q4 Insights');
      expect(fake.createCalls.first.def.renderMode, 'native');

      // The new row appears in the list. (REQ-U-06)
      expect(find.text('Q4 Insights'), findsOneWidget);
    });
  });

  group('ReportsList — duplicate report (REQ-C-09)', () {
    testWidgets(
        'tapping Duplicate on a row opens name dialog; confirming calls '
        'duplicateReport with the new name and adds a new row', (tester) async {
      // REQ-C-09 — duplicating a report creates a copy under a new name.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(
        fake,
        initialReports: [
          const ReportSummary(
            id: 'r1',
            name: 'Original',
            renderMode: 'native',
          ),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Original'), findsOneWidget);

      // Tap the duplicate icon on the row.
      await tester.tap(find.byIcon(Icons.copy));
      await tester.pumpAndSettle();

      expect(find.text('Duplicate report'), findsOneWidget);

      // Clear the pre-filled text and enter a new name.
      await tester.enterText(find.byType(TextField), 'Copy of Original');
      await tester.pump();

      // Confirm duplication.
      await tester.tap(find.widgetWithText(TextButton, 'Duplicate'));
      await tester.pumpAndSettle();

      // API called with the correct arguments. (REQ-C-09)
      expect(fake.duplicateCalls, hasLength(1));
      expect(fake.duplicateCalls.first.caseId, 'c1');
      expect(fake.duplicateCalls.first.reportId, 'r1');
      expect(fake.duplicateCalls.first.name, 'Copy of Original');

      // The duplicated row appears in the list.
      expect(find.text('Copy of Original'), findsOneWidget);

      // The original row is still present.
      expect(find.text('Original'), findsOneWidget);
    });
  });
}
