// Widget tests for the Cases screen.
// REQ-U-04 / REQ-C-03 / REQ-C-07

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/features/cases/cases_list.dart';

// ---------------------------------------------------------------------------
// Fake API (REQ-C-03 / REQ-C-07)
// ---------------------------------------------------------------------------

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  /// Names passed to [createCase] — inspected by tests. (REQ-C-03)
  final List<String> createdCases = <String>[];

  /// REQ-C-07 — listCases returns two known records.
  @override
  Future<List<CaseRecord>> listCases() async => [
        const CaseRecord(id: 'c1', name: 'Acme'),
        const CaseRecord(id: 'c2', name: 'Beta'),
      ];

  @override
  Future<String> createCase(String name) async {
    createdCases.add(name);
    return 'new-id';
  }
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

Widget _harness(_FakeNsightApi fake) {
  return ProviderScope(
    overrides: [
      nsightApiProvider.overrideWithValue(fake),
    ],
    child: const MaterialApp(home: Scaffold(body: CasesList())),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('CasesList (REQ-U-04 / REQ-C-07)', () {
    testWidgets('renders both case names and the Add button', (tester) async {
      // REQ-C-07 — list view shows all cases returned by the API.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      expect(find.text('Acme'), findsOneWidget);
      expect(find.text('Beta'), findsOneWidget);
      expect(find.byIcon(Icons.add), findsOneWidget);
    });
  });

  group('NewCaseDialog (REQ-C-03)', () {
    testWidgets(
        'tapping Add opens dialog; entering name and tapping Create calls createCase',
        (tester) async {
      // REQ-C-03 — creating a case via the dialog calls the API.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // Open dialog.
      await tester.tap(find.byIcon(Icons.add));
      await tester.pumpAndSettle();

      expect(find.text('New case'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);

      // Create button is disabled while name is empty.
      final createBtn =
          tester.widget<TextButton>(find.widgetWithText(TextButton, 'Create'));
      expect(createBtn.onPressed, isNull);

      // Enter a name.
      await tester.enterText(find.byType(TextField), 'My New Case');
      await tester.pump();

      // Create button is now enabled.
      final createBtnEnabled =
          tester.widget<TextButton>(find.widgetWithText(TextButton, 'Create'));
      expect(createBtnEnabled.onPressed, isNotNull);

      // Tap Create.
      await tester.tap(find.widgetWithText(TextButton, 'Create'));
      await tester.pumpAndSettle();

      // createCase was called with the entered name.
      expect(fake.createdCases, contains('My New Case'));

      // Dialog is dismissed.
      expect(find.text('New case'), findsNothing);
    });

    testWidgets('Cancel button closes the dialog without calling createCase',
        (tester) async {
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.add));
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
      await tester.pumpAndSettle();

      expect(find.text('New case'), findsNothing);
      expect(fake.createdCases, isEmpty);
    });
  });
}
