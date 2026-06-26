// Screenshot tests: renders QuestionBrowser and ReportBuilder to PNG files
// for the Claude-as-judge UI quality gate (Task 8.11).
//
// Writes to build/screenshots/ (gitignored).  The Python test
// tests/rb/test_ui_judge.py reads those PNGs and calls judge_image.
//
// REQ-C-05 — question browser organises survey questions clearly.
// REQ-U-11 — report builder usability for non-technical users.

import 'dart:io';
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:golden_toolkit/golden_toolkit.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/features/data/data_area.dart';
import 'package:nsight_ui/features/data/providers/material_provider.dart';
import 'package:nsight_ui/features/reports/providers/reports_provider.dart';
import 'package:nsight_ui/features/reports/report_builder.dart';

import '../support/fake_nsight_api.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Seeded providers
// ─────────────────────────────────────────────────────────────────────────────

class _SeededMaterialNotifier extends ActiveMaterialNotifier {
  @override
  String? build() => 'mat-smoke';
}

class _SeededSelectedReportNotifier extends SelectedReportNotifier {
  @override
  String? build() => 'r1';
}

// ─────────────────────────────────────────────────────────────────────────────
// Extended fake API: richer questions + pre-configured report for screenshots
// ─────────────────────────────────────────────────────────────────────────────

class _ScreenshotFakeApi extends FakeNsightApi {
  _ScreenshotFakeApi() {
    // Override the default two-item seed with a richer 7-question set so the
    // browser looks realistic. (REQ-C-05)
    seedMaterial('mat-smoke', const [
      QuestionItem(
        qid: 'q1',
        kind: 'single',
        variables: ['q1'],
        text: 'Overall satisfaction with the service',
      ),
      QuestionItem(
        qid: 'q2',
        kind: 'single',
        variables: ['q2'],
        text: 'Net promoter score (0–10)',
      ),
      QuestionItem(
        qid: 'q3',
        kind: 'multi',
        variables: ['q3a', 'q3b', 'q3c'],
        text: 'Which channels did you use?',
      ),
      QuestionItem(
        qid: 'q4',
        kind: 'single',
        variables: ['q4'],
        text: 'Likelihood to recommend to a colleague',
      ),
      QuestionItem(
        qid: 'q5',
        kind: 'single',
        variables: ['q5'],
        text: 'Brand awareness (aided)',
      ),
      QuestionItem(
        qid: 'q6',
        kind: 'multi',
        variables: ['q6a', 'q6b'],
        text: 'Top reasons for satisfaction',
      ),
      QuestionItem(
        qid: 'q7',
        kind: 'single',
        variables: ['q7'],
        text: 'Purchase intent in next 12 months',
      ),
    ]);
  }

  /// Returns a pre-configured report with two chart cards so the builder
  /// screenshot shows the two-panel layout with real content. (REQ-U-11)
  @override
  Future<ReportDef> getReport(String caseId, String reportId) async =>
      const ReportDef(
        name: 'Q3 Customer Survey',
        renderMode: 'image',
        templateRef: 'default',
        charts: [
          ChartSpecDef(
            questionRef: 'q1',
            chartType: 'vertical_bar',
            statistic: 'pct',
          ),
          ChartSpecDef(
            questionRef: 'q3',
            chartType: 'horizontal_bar',
            statistic: 'pct',
          ),
        ],
      );
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: capture a RepaintBoundary → PNG → build/screenshots/<filename>
//
// Both toImage() and toByteData() are engine-level calls that must run inside
// tester.runAsync() (real async zone), mirroring how golden_toolkit itself
// handles rendering.  File writes are done synchronously to avoid leaving
// pending IO callbacks between tests.
// ─────────────────────────────────────────────────────────────────────────────

Future<void> _captureScreenshot(
  WidgetTester tester,
  GlobalKey boundaryKey,
  String filename,
) async {
  final boundary =
      boundaryKey.currentContext!.findRenderObject() as RenderRepaintBoundary;

  // Engine calls must run in the real async zone.
  final pngBytes = await tester.runAsync<Uint8List>(() async {
    final image = await boundary.toImage(pixelRatio: 2.0);
    final byteData = await image.toByteData(format: ImageByteFormat.png);
    image.dispose(); // release GPU resources
    return byteData!.buffer.asUint8List();
  });

  // Synchronous IO to stay inside the fake-async zone after runAsync returns.
  Directory('build/screenshots').createSync(recursive: true);
  File('build/screenshots/$filename').writeAsBytesSync(pngBytes!);
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

void main() {
  // loadAppFonts() from golden_toolkit ensures Material/Roboto glyphs render
  // as real characters rather than placeholder boxes in the headless engine.
  setUpAll(() async {
    await loadAppFonts();
  });

  // Both screenshots are captured in a single testWidgets block.
  //
  // Background: toImage() + toByteData() use engine threads.  Running them
  // in tester.runAsync() (as golden_toolkit does) is correct.  However, the
  // subsequent testWidgets() teardown/setup can race with lingering native
  // callbacks from a previous test's engine work.  Combining both captures
  // in one block avoids any cross-test teardown interaction entirely.
  testWidgets(
    'Screenshots: QuestionBrowser (REQ-C-05) and ReportBuilder (REQ-U-11)',
    (tester) async {
      // Desktop viewport — 1200×900 logical pixels.
      tester.view.physicalSize = const Size(1200, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // ── Part 1: QuestionBrowser ──────────────────────────────────────────

      final qbKey = GlobalKey();
      final qbFake = _ScreenshotFakeApi();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(qbFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: qbKey,
                child: const DataArea(caseId: 'c1'),
              ),
            ),
          ),
        ),
      );
      // Do NOT use pumpAndSettle() — SegmentedButton selection animations run
      // indefinitely in a large 1200×900 viewport with many rows.  Two pumps
      // are enough: the first flushes the async listQuestions future; the
      // second advances the clock past the SegmentedButton animation (200ms).
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Verify at least one question row is visible before capturing.
      expect(
        find.text('Overall satisfaction with the service'),
        findsOneWidget,
        reason: 'REQ-C-05: question text must be visible in the browser',
      );

      await _captureScreenshot(tester, qbKey, 'question_browser.png');

      // Unmount the QB widget tree fully before mounting the RB tree.
      // ProviderScope does not allow changing the number of overrides between
      // pumpWidget calls on the same tree; a blank intermediate pump clears it.
      await tester.pumpWidget(const SizedBox.shrink());

      // ── Part 2: ReportBuilder ────────────────────────────────────────────

      final rbKey = GlobalKey();
      final rbFake = _ScreenshotFakeApi();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(rbFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
            selectedReportProvider
                .overrideWith(_SeededSelectedReportNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: rbKey,
                child: const ReportBuilder(caseId: 'c1', reportId: 'r1'),
              ),
            ),
          ),
        ),
      );
      // Three pumps: (1) initial render, (2) fire addPostFrameCallback +
      // let getReport resolve, (3) rebuild with chart cards; then advance
      // clock past Material animations.
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Verify that chart cards are visible before capturing.
      expect(
        find.byKey(const Key('chart_type_dropdown')),
        findsWidgets,
        reason: 'REQ-U-11: chart-type dropdowns must be visible in the builder',
      );

      await _captureScreenshot(tester, rbKey, 'report_builder.png');
    },
  );
}
