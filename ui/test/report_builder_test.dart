// Widget tests for the two-panel report builder — Task 8.7.
// REQ-C-10 / REQ-C-11 / REQ-C-13 / REQ-C-14 / REQ-C-15 / REQ-U-06 / REQ-U-11.

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/features/data/providers/material_provider.dart';
import 'package:nsight_ui/features/reports/providers/reports_provider.dart';
import 'package:nsight_ui/features/reports/report_builder.dart';

// ---------------------------------------------------------------------------
// Fake API
// ---------------------------------------------------------------------------

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  /// Calls captured by [saveReport]. (REQ-C-10)
  final List<({String caseId, String reportId, ReportDef def})> saveCalls = [];

  /// Fixed empty report returned by [getReport].
  @override
  Future<ReportDef> getReport(String caseId, String reportId) async =>
      const ReportDef(
        name: 'Test Report',
        renderMode: 'image',
        templateRef: 'default',
        charts: [],
      );

  /// Three questions for the pick-list. (REQ-C-11)
  @override
  Future<List<QuestionItem>> listQuestions(String materialId) async => const [
        QuestionItem(
          qid: 'q1',
          kind: 'single',
          variables: ['q1'],
          text: 'Overall satisfaction',
        ),
        QuestionItem(
          qid: 'q2',
          kind: 'single',
          variables: ['q2'],
          text: 'Net promoter score',
        ),
        QuestionItem(
          qid: 'q3',
          kind: 'multi',
          variables: ['q3a', 'q3b'],
          text: 'Which channels did you use?',
        ),
      ];

  /// Captures save calls. (REQ-C-10)
  @override
  Future<void> saveReport(
    String caseId,
    String reportId,
    ReportDef def,
  ) async {
    saveCalls.add((caseId: caseId, reportId: reportId, def: def));
  }
}

// ---------------------------------------------------------------------------
// Seeded notifiers for provider overrides
// ---------------------------------------------------------------------------

class _SeededMaterialNotifier extends ActiveMaterialNotifier {
  @override
  String? build() => 'mat-1';
}

class _SeededSelectedReportNotifier extends SelectedReportNotifier {
  @override
  String? build() => 'r1';
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

Widget _harness(_FakeNsightApi fake) => ProviderScope(
      overrides: [
        nsightApiProvider.overrideWithValue(fake),
        activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
        selectedReportProvider.overrideWith(_SeededSelectedReportNotifier.new),
      ],
      child: const MaterialApp(
        home: Scaffold(
          body: ReportBuilder(caseId: 'c1', reportId: 'r1'),
        ),
      ),
    );

// ---------------------------------------------------------------------------
// Helper: inspect the inner DropdownButton<String> embedded by
// DropdownButtonFormField (which doesn't expose items directly).
// ---------------------------------------------------------------------------

/// Returns the inner [DropdownButton<String>] inside the
/// [DropdownButtonFormField] identified by [dropdownKey].
DropdownButton<String> _innerDropdown(
  WidgetTester tester,
  Key dropdownKey,
) =>
    tester.widget<DropdownButton<String>>(
      find.descendant(
        of: find.byKey(dropdownKey),
        matching: find.byType(DropdownButton<String>),
      ),
    );

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  // REQ-C-11 / REQ-U-11 — pick-list → add checked → chart card appears.
  group('ReportBuilder — pick-list and chart card (REQ-C-11 / REQ-U-11)', () {
    testWidgets(
        'checking a question and tapping "Add checked" renders one chart card '
        'with chart-type (11 entries), statistic, and classifying-var dropdowns',
        (tester) async {
      // REQ-C-11 — addQuestions appends a default card for the selected qid.
      // REQ-U-11 — the user can pick questions from the material's list.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // The pick-list should show all three questions.
      expect(find.text('Overall satisfaction'), findsOneWidget);
      expect(find.text('Net promoter score'), findsOneWidget);
      expect(find.text('Which channels did you use?'), findsOneWidget);

      // Initially no chart-type dropdown.
      expect(find.byKey(const Key('chart_type_dropdown')), findsNothing);

      // Check the first question.
      await tester.tap(find.byType(CheckboxListTile).first);
      await tester.pump();

      // Tap "Add checked →".
      await tester.tap(find.byKey(const Key('add_checked_button')));
      await tester.pumpAndSettle();

      // REQ-C-11 — exactly one chart card appeared.
      expect(
        find.byKey(const Key('chart_type_dropdown')),
        findsOneWidget,
        reason: 'one chart-type dropdown should be present after adding a question',
      );

      // REQ-C-13 — chart-type dropdown has exactly 11 entries in image mode.
      // Inspect the DropdownButton<String> embedded inside DropdownButtonFormField.
      final chartTypeInner =
          _innerDropdown(tester, const Key('chart_type_dropdown'));
      expect(
        chartTypeInner.items!.length,
        11,
        reason: 'there are 11 chart types in image mode (combo included)',
      );

      // Statistic dropdown present. (REQ-C-14)
      expect(
        find.byKey(const Key('statistic_dropdown')),
        findsOneWidget,
        reason: 'statistic dropdown should be present',
      );

      // Classifying-var dropdown present. (REQ-C-14)
      expect(
        find.byKey(const Key('classifying_var_dropdown')),
        findsOneWidget,
        reason: 'classifying-var dropdown should be present',
      );
    });
  });

  // REQ-C-10 — Save calls saveReport with correct ChartSpecDef JSON.
  group('ReportBuilder — save (REQ-C-10)', () {
    testWidgets(
        'tapping Save after adding a question calls saveReport with 1 chart '
        'whose JSON contains question_ref, chart_type, statistic, '
        'and template_slot=="s1"', (tester) async {
      // REQ-C-10 — saveReport is called; the chart JSON has the right keys
      // including template_slot auto-assigned by position.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // Add first question.
      await tester.tap(find.byType(CheckboxListTile).first);
      await tester.pump();
      await tester.tap(find.byKey(const Key('add_checked_button')));
      await tester.pumpAndSettle();

      // Tap Save.
      await tester.tap(find.byKey(const Key('save_button')));
      await tester.pumpAndSettle();

      // REQ-C-10 — saveReport was called exactly once.
      expect(fake.saveCalls, hasLength(1));
      expect(fake.saveCalls.first.caseId, 'c1');
      expect(fake.saveCalls.first.reportId, 'r1');

      final savedDef = fake.saveCalls.first.def;
      expect(savedDef.charts, hasLength(1));

      // Verify the chart JSON keys (REQ-C-10).
      final chartJson = savedDef.toJson()['charts'][0] as Map<String, dynamic>;
      expect(chartJson['question_ref'], isNotNull,
          reason: 'chart JSON must have question_ref');
      expect(chartJson['chart_type'], isNotNull,
          reason: 'chart JSON must have chart_type');
      expect(chartJson['statistic'], isNotNull,
          reason: 'chart JSON must have statistic');
      expect(chartJson['template_slot'], 's1',
          reason: 'first chart template_slot must be s1 (REQ-C-10)');
    });
  });

  // REQ-C-13 — combo disabled when render mode is native.
  group('ReportBuilder — combo disabled in native mode (REQ-C-13)', () {
    testWidgets(
        'switching to native render mode removes the combo option from the '
        'chart-type dropdown', (tester) async {
      // REQ-C-13 — combo chart type must not be available in native mode.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // Add a question so the chart-type dropdown appears.
      await tester.tap(find.byType(CheckboxListTile).first);
      await tester.pump();
      await tester.tap(find.byKey(const Key('add_checked_button')));
      await tester.pumpAndSettle();

      // In image mode: 11 items (combo included). (REQ-C-13)
      final beforeSwitch =
          _innerDropdown(tester, const Key('chart_type_dropdown'));
      expect(beforeSwitch.items!.length, 11,
          reason: '11 types in image mode (combo included)');
      expect(
        beforeSwitch.items!.any((i) => i.value == 'combo'),
        isTrue,
        reason: 'combo is present in image mode',
      );

      // Switch to native mode.
      await tester.tap(find.text('native'));
      await tester.pumpAndSettle();

      // In native mode: 10 items (combo absent). (REQ-C-13)
      final afterSwitch =
          _innerDropdown(tester, const Key('chart_type_dropdown'));
      expect(afterSwitch.items!.length, 10,
          reason: '10 types in native mode (combo removed)');
      expect(
        afterSwitch.items!.any((i) => i.value == 'combo'),
        isFalse,
        reason: 'combo must be absent when renderMode is native (REQ-C-13)',
      );
    });
  });
}
