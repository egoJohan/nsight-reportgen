// Widget tests for the report window-controls scaffold — Task 8.12.
// REQ-U-07 / REQ-U-08 / REQ-U-09.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/features/reports/report_window.dart';

void main() {
  group('ReportWindow (REQ-U-07/08/09)', () {
    testWidgets(
      'Close icon calls onClose callback when tapped',
      (tester) async {
        // Arrange: track whether close was called.
        bool closed = false;

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ReportWindow(
                onClose: () => closed = true,
                child: const Text('x'),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Act: tap the close icon.
        await tester.tap(find.byIcon(Icons.close));
        await tester.pumpAndSettle();

        // Assert: onClose was called.
        expect(closed, isTrue, reason: 'Close icon should trigger onClose');
      },
    );

    testWidgets(
      'Resize handle accepts drag gestures',
      (tester) async {
        // Arrange: track resize callbacks.
        final resizeSizes = <Size>[];

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ReportWindow(
                onClose: () {},
                onResize: (size) => resizeSizes.add(size),
                child: const Text('resizable'),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Act: drag from the resize handle.
        final dragHandle = find.byIcon(Icons.drag_handle);
        expect(dragHandle, findsOneWidget,
            reason: 'Resize handle should be present');

        // Perform a simple drag.
        await tester.drag(dragHandle, const Offset(20, 20));
        await tester.pumpAndSettle();

        // Assert: onResize was called with a size delta.
        // REQ-U-08 — resize gesture wired.
        expect(resizeSizes.isNotEmpty, isTrue,
            reason: 'Drag should invoke onResize callback');
      },
    );
  });
}
