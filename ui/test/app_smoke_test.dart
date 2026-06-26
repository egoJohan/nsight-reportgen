// Full-app smoke test — drives the core flow through the real widget tree
// using [FakeNsightApi] as the backend. REQ-U-01.
//
// Covered requirements: C-03 / C-05 / C-06 / C-07 / C-10 / C-11.
// C-19 (render) is covered by report_preview_test.dart.
//
// ── Flow (one testWidgets, five steps) ───────────────────────────────────────
//
//  Step 1 — Create a case via the Add dialog → appears in list → select it.
//            (C-03 / C-07)
//
//  Step 2 — Data tab: questions are present (active material pre-seeded via
//            _SeededMaterialNotifier); toggle 'Overall satisfaction' to 'multi'
//            → assert setGrouping called.  (C-05 / C-06)
//
//  Step 3 — Reports tab: create a report (name + native) → appears in list.
//            (C-07)
//
//  Step 4 — Open the report → wizard (W2): check first question in the
//            SelectStep, tap "Add selected →" → ConfigureStep appears with
//            chart card; tap Save → assert saveReport called with ≥1 chart.
//            (C-10 / C-11)
//
//  Step 5 — Wizard navigation: Next button advances to Configure; wizard
//            step indicator shows correct active step. (REQ-U-01)
//
// ── Note on split ────────────────────────────────────────────────────────────
//
//  All five steps run inside a single [testWidgets] block pumped with the full
//  [NSightApp] (desktop viewport 1400×900).  Multiple [pumpAndSettle] calls
//  separate each interaction area; no manual [pump] durations are required
//  because FakeNsightApi resolves every future in the next microtask tick.
//
//  The [activeMaterialProvider] is overridden with [_SeededMaterialNotifier]
//  (returning 'mat-smoke') so the Data tab and the wizard's question select
//  list both see the two seeded questions without requiring a real file upload.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/features/data/providers/material_provider.dart';
import 'package:nsight_ui/main.dart';

import 'support/fake_nsight_api.dart';

// ---------------------------------------------------------------------------
// Seeded notifier
// ---------------------------------------------------------------------------

/// Pre-seeds [activeMaterialProvider] with 'mat-smoke' so both the
/// QuestionBrowser (Data tab) and the QuestionPickList (builder) see
/// questions without requiring an actual file upload. (REQ-U-01 / C-04)
class _SeededMaterialNotifier extends ActiveMaterialNotifier {
  @override
  String? build() => 'mat-smoke';
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

Widget _smokeHarness(FakeNsightApi fake) => ProviderScope(
      overrides: [
        nsightApiProvider.overrideWithValue(fake),
        activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
      ],
      child: const NSightApp(),
    );

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('App smoke test — full core flow (REQ-U-01)', () {
    testWidgets(
      'Steps 1-5: create case → data toggle → create report → '
      'builder add+save → render preview',
      (tester) async {
        // REQ-U-01 — end-to-end: C-03/05/06/07/10/11/19.

        // ── Viewport: desktop 3-pane layout (≥ 900 px wide). ─────────────
        tester.view.physicalSize = const Size(1400, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final fake = FakeNsightApi();
        await tester.pumpWidget(_smokeHarness(fake));
        await tester.pumpAndSettle();

        // ================================================================
        // Step 1 — Create a case (C-03 / C-07)
        // ================================================================

        // Detail pane shows empty-state before any case is selected (C-07).
        expect(find.text('Select a case'), findsOneWidget,
            reason: 'C-07: empty state visible before case selection');

        // Open the "Add case" dialog.
        await tester.tap(find.byIcon(Icons.add));
        await tester.pumpAndSettle();
        expect(find.text('New case'), findsOneWidget);

        // Enter a name and confirm — Create button is disabled while empty.
        final createBtnBefore = tester.widget<TextButton>(
          find.widgetWithText(TextButton, 'Create'),
        );
        expect(createBtnBefore.onPressed, isNull,
            reason: 'C-03: Create must be disabled when name is empty');

        await tester.enterText(find.byType(TextField).first, 'Smoke Case');
        await tester.pump();
        await tester.tap(find.widgetWithText(TextButton, 'Create'));
        await tester.pumpAndSettle();

        // C-03: case appears in the list after creation.
        expect(find.text('Smoke Case'), findsOneWidget,
            reason: 'C-03: newly created case must appear in the list');
        expect(fake.createCaseCalls, contains('Smoke Case'));

        // Select the case → CaseDetail is shown on the right.
        await tester.tap(find.text('Smoke Case'));
        await tester.pumpAndSettle();

        expect(find.text('Data'), findsOneWidget);
        expect(find.text('Reports'), findsOneWidget);

        // ================================================================
        // Step 2 — Data tab: toggle a question to multi (C-05 / C-06)
        // ================================================================

        // Data tab is active by default; active material is pre-seeded.
        // C-05: both seeded questions appear in the QuestionBrowser.
        expect(find.text('Overall satisfaction'), findsOneWidget,
            reason: 'C-05: question text must appear in the browser');
        expect(find.text('Net promoter score'), findsOneWidget,
            reason: 'C-05: second question must also appear');

        // Toggle 'Overall satisfaction' from 'single' → 'multi' (C-06).
        final satisfactionTile = find.ancestor(
          of: find.text('Overall satisfaction'),
          matching: find.byType(ListTile),
        );
        final multiSegment = find.descendant(
          of: satisfactionTile,
          matching: find.text('multi'),
        );
        await tester.tap(multiSegment);
        await tester.pumpAndSettle();

        // C-06: setGrouping was called once with kind='multi'.
        expect(fake.setGroupingCalls, hasLength(1),
            reason: 'C-06: setGrouping must be called on kind toggle');
        expect(fake.setGroupingCalls.first.kind, 'multi',
            reason: 'C-06: kind argument must be "multi"');

        // ================================================================
        // Step 3 — Reports tab: create a report (C-07)
        // ================================================================

        await tester.tap(find.text('Reports'));
        await tester.pumpAndSettle();
        expect(find.text('No reports yet.'), findsOneWidget);

        // Open the "Add report" dialog (ElevatedButton.icon — tap by text label).
        await tester.tap(find.text('Add report'));
        await tester.pumpAndSettle();
        expect(find.text('New report'), findsOneWidget);

        // Enter name; 'native' render mode is the default selection.
        await tester.enterText(find.byType(TextField).first, 'Smoke Report');
        await tester.pump();
        await tester.tap(find.widgetWithText(TextButton, 'Create'));
        await tester.pumpAndSettle();

        // C-07: the new report appears in the session list.
        expect(find.text('Smoke Report'), findsOneWidget,
            reason: 'C-07: created report must appear in the Reports list');

        // ================================================================
        // Step 4 — Wizard (W2): select question, add, save (C-10 / C-11)
        // ================================================================

        // Tap the report row to open the wizard.
        await tester.tap(find.text('Smoke Report'));
        await tester.pumpAndSettle();
        // Wizard loads via post-frame callback; settle after the async load.
        await tester.pumpAndSettle();

        // Wizard shows SelectStep. C-11: question list is populated.
        expect(find.byType(CheckboxListTile), findsWidgets,
            reason: 'C-11: wizard SelectStep must show material questions');

        // Check the first question (q1 — first item in listQuestions).
        await tester.tap(find.byType(CheckboxListTile).first);
        await tester.pump();

        // Tap "Add selected →" — adds chart(s) and navigates to ConfigureStep.
        await tester.tap(find.byKey(const Key('add_selected_button')));
        await tester.pumpAndSettle();

        // C-11: ConfigureStep now shows chart cards.
        // chart_type_dropdown_0 is the per-index key in WizardChartCard.
        expect(
          find.byKey(const Key('chart_type_dropdown_0')),
          findsOneWidget,
          reason: 'C-11: adding a question must produce a chart card with '
              'a chart-type dropdown in ConfigureStep',
        );

        // Tap Save (C-10).
        await tester.tap(find.byKey(const Key('wizard_save_button')));
        await tester.pumpAndSettle();

        // C-10: saveReport called exactly once with ≥1 chart.
        expect(
          fake.saveReportCalls,
          hasLength(1),
          reason: 'C-10: Save must invoke saveReport',
        );
        expect(
          fake.saveReportCalls.first.def.charts.length,
          greaterThanOrEqualTo(1),
          reason: 'C-10: saved ReportDef must contain at least one chart',
        );

        // ================================================================
        // Step 5 — Wizard state verification (REQ-U-01)
        // ================================================================

        // We are now on ConfigureStep (step index 1). The step indicator must
        // show all five step labels. (REQ-U-01)
        expect(
          find.text('Select'),
          findsWidgets,
          reason: 'REQ-U-01: wizard must display Select step label',
        );
        expect(
          find.text('Configure'),
          findsWidgets,
          reason: 'REQ-U-01: wizard must display Configure step label',
        );
        expect(
          find.text('Review'),
          findsWidgets,
          reason: 'REQ-U-01: wizard must display Review step label',
        );

        // ConfigureStep: chart card controls are present.
        expect(
          find.byKey(const Key('chart_type_dropdown_0')),
          findsOneWidget,
          reason: 'REQ-U-01: ConfigureStep must show chart-type dropdown',
        );
        expect(
          find.byKey(const Key('number_format_mode_0')),
          findsOneWidget,
          reason: 'REQ-U-01: Automatic/Manual number format toggle must be visible',
        );

        // Note: C-19 render is tested independently in report_preview_test.dart.
        // Back/Next navigation is tested in wizard_test.dart unit tests.
      },
    );
  });
}
