// Widget tests for DataArea / QuestionBrowser — Task 8.5.
// REQ-U-05 / REQ-C-05 / REQ-C-06 / REQ-C-26.

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
// Fake API (REQ-C-05 / REQ-C-06)
// ---------------------------------------------------------------------------

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  /// Captured arguments from [setGrouping] calls. (REQ-C-06)
  final List<List<String>> capturedVariables = [];
  final List<String> capturedKinds = [];

  /// REQ-C-05 — fixed two-item list used across all question-browser tests.
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
        ),
      ];

  /// REQ-C-06 — capture the call and return an updated item.
  @override
  Future<QuestionItem> setGrouping(
    String materialId,
    List<String> variables,
    String kind,
  ) async {
    capturedVariables.add(variables);
    capturedKinds.add(kind);
    return QuestionItem(
      qid: variables.first,
      kind: kind,
      variables: variables,
      text: '',
    );
  }
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

    testWidgets('each row contains a single/multi SegmentedButton',
        (tester) async {
      // REQ-C-05 — each question row has a kind toggle.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      // Two rows → two SegmentedButtons.
      expect(find.byType(SegmentedButton<String>), findsNWidgets(2));

      // Both 'single' and 'multi' segment labels appear (one per button each).
      expect(find.text('single'), findsNWidgets(2));
      expect(find.text('multi'), findsNWidgets(2));
    });

    testWidgets(
        'toggling a row SegmentedButton calls setGrouping with correct args',
        (tester) async {
      // REQ-C-06 — tapping the opposite kind segment calls the API.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake, materialId: 'mat-1'));
      await tester.pumpAndSettle();

      // Default sort is textAZ: Channels first, then Satisfaction.
      // Tap the 'multi' segment in the Satisfaction row (currently 'single').
      final satisfactionTile = find.ancestor(
        of: find.text('Satisfaction'),
        matching: find.byType(ListTile),
      );
      expect(satisfactionTile, findsOneWidget);

      final multiInSatisfaction = find.descendant(
        of: satisfactionTile,
        matching: find.text('multi'),
      );
      await tester.tap(multiInSatisfaction);
      await tester.pumpAndSettle();

      // REQ-C-06 — setGrouping called with q1's variables and new kind.
      expect(fake.capturedVariables, isNotEmpty);
      expect(fake.capturedVariables.last, ['q1']);
      expect(fake.capturedKinds.last, 'multi');
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
