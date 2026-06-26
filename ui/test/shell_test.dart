// REQ-U-04 — Responsive shell: 3-pane desktop / bottom-nav mobile.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/shell/app_shell.dart';
import 'package:nsight_ui/shell/bottom_nav.dart';
import 'package:nsight_ui/shell/icon_rail.dart';

/// Wraps [AppShell] with the providers and material app required for testing.
Widget _harness() {
  return const ProviderScope(
    child: MaterialApp(
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

      // Assert — list placeholder, detail placeholder, and icon rail are present.
      expect(find.text('Cases'), findsOneWidget);
      expect(find.text('Detail'), findsOneWidget);
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
