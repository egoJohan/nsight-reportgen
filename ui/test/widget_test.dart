// Smoke test — app boots without throwing.
import 'package:flutter_test/flutter_test.dart';
import 'package:nsight_ui/main.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  testWidgets('NSightApp smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: NSightApp()));
    await tester.pumpAndSettle();
    // App renders without throwing.
    expect(tester.takeException(), isNull);
  });
}
