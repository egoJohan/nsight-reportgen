// Keyboard focus-traversal tests — REQ-U-10.
//
// Verifies that the Tab key moves focus sequentially through focusable
// controls, using a lightweight widget scaffold (no provider setup needed).

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Keyboard focus traversal (REQ-U-10)', () {
    testWidgets(
      'Tab moves focus from the first TextField to the next control',
      (tester) async {
        // Arrange: three focusable controls with explicit FocusNodes so we can
        // assert focus state precisely.
        final node1 = FocusNode(debugLabel: 'field1');
        final node2 = FocusNode(debugLabel: 'field2');
        final node3 = FocusNode(debugLabel: 'submitBtn');
        addTearDown(node1.dispose);
        addTearDown(node2.dispose);
        addTearDown(node3.dispose);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  TextField(
                    key: const Key('field1'),
                    focusNode: node1,
                    autofocus: true,
                    decoration: const InputDecoration(labelText: 'Case name'),
                  ),
                  TextField(
                    key: const Key('field2'),
                    focusNode: node2,
                    decoration:
                        const InputDecoration(labelText: 'Description'),
                  ),
                  ElevatedButton(
                    key: const Key('submitBtn'),
                    focusNode: node3,
                    onPressed: () {},
                    child: const Text('Create'),
                  ),
                ],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // The first field must have focus from autofocus.
        expect(node1.hasFocus, isTrue,
            reason: 'field1 should receive initial focus via autofocus');

        // Act: one Tab press.
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();

        // Assert: focus moved to field2; field1 lost focus.
        expect(node2.hasFocus, isTrue,
            reason: 'first Tab should move focus to field2');
        expect(node1.hasFocus, isFalse,
            reason: 'field1 should have lost focus after Tab');

        // Act: second Tab press.
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();

        // Assert: focus moved to the button; field2 lost focus.
        expect(node3.hasFocus, isTrue,
            reason: 'second Tab should move focus to the Submit button');
        expect(node2.hasFocus, isFalse,
            reason: 'field2 should have lost focus after second Tab');
      },
    );
  });
}
