// REQ-U-04 — Responsive shell: 3-pane desktop / bottom-nav mobile.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/shell/app_shell.dart';
import 'package:nsight_ui/shell/bottom_nav.dart';
import 'package:nsight_ui/shell/icon_rail.dart';

/// Minimal fake that returns an empty cases list — keeps shell tests fast and
/// network-free. The shell tests exercise layout only, not case content.
class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  @override
  Future<List<CaseRecord>> listCases() async => [];
}

/// Wraps [AppShell] with a faked [nsightApiProvider] and material app.
Widget _harness() {
  return ProviderScope(
    overrides: [
      nsightApiProvider.overrideWithValue(_FakeNsightApi()),
    ],
    child: const MaterialApp(
      home: AppShell(),
    ),
  );
}

void main() {
  group('AppShell responsive layout (REQ-U-04)', () {
    testWidgets('desktop (1200×900): shows icon rail, list pane, detail pane',
        (WidgetTester tester) async {
      // Arrange — set physical size to 1200×900 at 1:1 pixel ratio.
      tester.view.physicalSize = const Size(1200, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // Act
      await tester.pumpWidget(_harness());
      await tester.pumpAndSettle();

      // Assert — list pane, empty-state detail pane, and icon rail are present.
      expect(find.text('Cases'), findsOneWidget);
      // No case selected yet → empty state (REQ-U-04).
      expect(find.text('Select a case'), findsOneWidget);
      expect(find.byType(IconRail), findsOneWidget);

      // Bottom nav must NOT be visible in desktop mode.
      expect(find.byType(BottomNav), findsNothing);
    });

    testWidgets('mobile (400×800): shows bottom nav, no icon rail',
        (WidgetTester tester) async {
      // Arrange — set physical size to 400×800 at 1:1 pixel ratio.
      tester.view.physicalSize = const Size(400, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // Act
      await tester.pumpWidget(_harness());
      await tester.pumpAndSettle();

      // Assert — bottom nav is present, icon rail is absent.
      expect(find.byType(BottomNav), findsOneWidget);
      expect(find.byType(IconRail), findsNothing);

      // Verify nav icons are present in the bottom bar.
      expect(find.byIcon(Icons.folder_outlined), findsOneWidget);
      expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    });
  });
}
