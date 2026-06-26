// Widget tests for DataArea / QuestionBrowser — W4 update.
// REQ-U-05 / REQ-C-05 / REQ-C-26 / D-06.
//
// The single/multi SegmentedButton toggle has been removed (D-06 / W4.2):
// replaced by a read-only auto-detected kind badge ("Single" / "Multi · N opts").
// W4.3: missing-value mappings appear as "Special values → Not answered: …".

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/features/data/data_area.dart';
import 'package:nsight_ui/features/data/providers/material_provider.dart';
import 'package:nsight_ui/features/data/question_browser.dart';

// ---------------------------------------------------------------------------
// Fake API (REQ-C-05)
// ---------------------------------------------------------------------------

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  /// REQ-C-05 — two questions: one single (no missing values), one multi
  /// (with missing values) to exercise W4.2 + W4.3.
  @override
  Future<List<QuestionItem>> listQuestions(String materialId) async => [
        const QuestionItem(
          qid: 'q1',
          kind: 'single',
          variables: ['q1'],
          text: 'Satisfaction',
        ),
        const QuestionItem(
          qid: 'm',
          kind: 'multi',
          variables: ['m1', 'm2'],
          text: 'Channels',
          missingValues: [
            MissingValue(code: '99', label: 'En tiedä'),
          ],
        ),
      ];
}

// ---------------------------------------------------------------------------
// Seeded ActiveMaterialNotifier
// ---------------------------------------------------------------------------

/// Subclass that pre-seeds build() with a fixed materialId (or null).
class _SeededMaterialNotifier extends ActiveMaterialNotifier {
  _SeededMaterialNotifier(this._initial);
  final String? _initial;

  @override
  String? build() => _initial;
}

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

Widget _harness(
  _FakeNsightApi fake, {
  String? materialId,
}) {
  return ProviderScope(
    overrides: [
      nsightApiProvider.overrideWithValue(fake),
      activeMaterialProvider.overrideWith(
        () => _SeededMaterialNotifier(materialId),
      ),
    ],
    child: const MaterialApp(
      home: Scaffold(body: DataArea(caseId: 'c1')),
    ),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('DataArea — no active material (REQ-U-05)', () {
    testWidgets('shows "Upload .sav" button when no material is active',
        (tester) async {
      // REQ-U-05 — upload entry point is visible before a material is chosen.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: null));
      await tester.pumpAndSettle();

      expect(find.text('Upload .sav'), findsOneWidget);
      // Question browser must NOT appear.
      expect(find.byType(QuestionBrowser), findsNothing);
    });
  });

  group('QuestionBrowser — active material (REQ-U-05 / REQ-C-05)', () {
    testWidgets('renders both question texts', (tester) async {
      // REQ-C-05 — all questions from listQuestions are displayed.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      expect(find.text('Satisfaction'), findsOneWidget);
      expect(find.text('Channels'), findsOneWidget);
    });

    testWidgets(
        'each row shows a read-only kind badge; no SegmentedButton present '
        '(D-06 / W4.2)', (tester) async {
      // D-06 — the broken single/multi toggle must be gone; kind badge shown.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      // No SegmentedButton present (the old toggle is removed).
      expect(find.byType(SegmentedButton<String>), findsNothing);

      // "Single" badge appears for q1.
      expect(find.text('Single'), findsOneWidget);

      // "Multi · 2 opts" badge appears for the multi question.
      expect(find.text('Multi · 2 opts'), findsOneWidget);
    });

    testWidgets('multi badge text includes variable count (W4.2)',
        (tester) async {
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      // The multi question has 2 variables → badge shows "Multi · 2 opts".
      expect(find.text('Multi · 2 opts'), findsOneWidget);
    });

    testWidgets(
        'missing-value chip appears for questions with missingValues (W4.3)',
        (tester) async {
      // W4.3 — "Special values → Not answered: …" line must be visible.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      // The multi question has missingValues: [{code:'99', label:'En tiedä'}].
      expect(
        find.textContaining('Special values'),
        findsOneWidget,
        reason: 'W4.3: missing-value info must be visible for the multi row',
      );
      expect(
        find.textContaining('99 = En tiedä'),
        findsOneWidget,
        reason: 'W4.3: code and label must appear in the missing-value line',
      );

      // The single question (no missing values) has no such line.
      expect(find.textContaining('Not answered'), findsOneWidget,
          reason: 'only one question has missing values');
    });

    testWidgets('auto-detected kind explainer is visible (W4.2)',
        (tester) async {
      // W4.2 — one-line explainer at the top of the Data area.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('auto-detected as Single'),
        findsOneWidget,
        reason: 'W4.2: explainer text must appear above the question list',
      );
    });

    testWidgets('sort dropdown is visible when material is active',
        (tester) async {
      // REQ-C-26 — client-side sort control is present.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      expect(find.text('Sort by:'), findsOneWidget);
      expect(find.byType(DropdownButton<QuestionSortMode>), findsOneWidget);
    });
  });
}
