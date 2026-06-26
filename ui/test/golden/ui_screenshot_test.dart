// Screenshot tests: renders QuestionBrowser, ReportBuilder, and the W2
// ReportWizard steps to PNG files for the Claude-as-judge UI quality gate.
//
// Writes to build/screenshots/ (gitignored).  The Python test
// tests/rb/test_ui_judge.py reads those PNGs and calls judge_image.
//
// REQ-C-05 — question browser organises survey questions clearly.
// REQ-U-11 — report builder / wizard usability for non-technical users.
// W2      — wizard_select.png (step 1) + wizard_configure.png (step 2).

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
import 'package:nsight_ui/features/reports/providers/builder_provider.dart';
import 'package:nsight_ui/features/reports/providers/reports_provider.dart';
import 'package:nsight_ui/features/reports/report_builder.dart';
import 'package:nsight_ui/features/reports/wizard/report_wizard.dart';
import 'package:nsight_ui/features/reports/wizard/step_configure.dart';
import 'package:nsight_ui/features/reports/wizard/step_review.dart';
import 'package:nsight_ui/features/reports/wizard/step_slides.dart';
import 'package:nsight_ui/features/reports/wizard/step_download.dart';

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
        suggestedChartType: 'horizontal_bar',
      ),
      QuestionItem(
        qid: 'q2',
        kind: 'single',
        variables: ['q2'],
        text: 'Net promoter score (0–10)',
        suggestedChartType: 'vertical_bar',
      ),
      QuestionItem(
        qid: 'q3',
        kind: 'multi',
        variables: ['q3a', 'q3b', 'q3c'],
        text: 'Which channels did you use?',
        suggestedChartType: 'stacked_horizontal_bar',
      ),
      QuestionItem(
        qid: 'q4',
        kind: 'single',
        variables: ['q4'],
        text: 'Likelihood to recommend to a colleague',
        suggestedChartType: 'vertical_bar',
      ),
      QuestionItem(
        qid: 'q5',
        kind: 'single',
        variables: ['q5'],
        text: 'Brand awareness (aided)',
        suggestedChartType: 'horizontal_bar',
      ),
      QuestionItem(
        qid: 'q6',
        kind: 'multi',
        variables: ['q6a', 'q6b'],
        text: 'Top reasons for satisfaction',
        suggestedChartType: 'stacked_horizontal_bar',
      ),
      QuestionItem(
        qid: 'q7',
        kind: 'single',
        variables: ['q7'],
        text: 'Purchase intent in next 12 months',
        suggestedChartType: 'vertical_bar',
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

  /// Returns a minimal 1×1 PNG placeholder for live chart thumbnails. (W2)
  @override
  Future<Uint8List> previewChart(
    String materialId,
    Map<String, dynamic> chartSpecJson,
  ) async {
    // Minimal valid 1×1 grey RGBA PNG (same bytes as FakeNsightApi._kMinimalPng).
    return Uint8List.fromList(const [
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
      0x00, 0x00, 0x00, 0x0D,
      0x49, 0x48, 0x44, 0x52,
      0x00, 0x00, 0x00, 0x01,
      0x00, 0x00, 0x00, 0x01,
      0x08, 0x06,
      0x00, 0x00, 0x00,
      0x1F, 0x15, 0xC4, 0x89,
      0x00, 0x00, 0x00, 0x0B,
      0x49, 0x44, 0x41, 0x54,
      0x08, 0xD7,
      0x63, 0x60, 0x60, 0x60, 0x60, 0x00, 0x00, 0x00, 0x05, 0x00, 0x01,
      0xA5, 0xF6, 0x45, 0x40,
      0x00, 0x00, 0x00, 0x00,
      0x49, 0x45, 0x4E, 0x44,
      0xAE, 0x42, 0x60, 0x82,
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Seeded builder notifier (for wizard screenshots with pre-loaded charts)
// ─────────────────────────────────────────────────────────────────────────────

/// Pre-seeds the builder draft with three chart cards so the wizard
/// ConfigureStep screenshot shows realistic content. (W2)
class _WizardSeededBuilderNotifier extends ReportBuilderNotifier {
  @override
  ReportDraft? build() => const ReportDraft(
        name: 'Q3 Customer Survey',
        renderMode: 'image',
        charts: [
          ChartSpecDef(
            questionRef: 'q1',
            chartType: 'horizontal_bar',
            statistic: 'pct',
          ),
          ChartSpecDef(
            questionRef: 'q3',
            chartType: 'stacked_horizontal_bar',
            statistic: 'pct',
          ),
          ChartSpecDef(
            questionRef: 'q4',
            chartType: 'vertical_bar',
            statistic: 'pct',
          ),
        ],
      );
}

// ─────────────────────────────────────────────────────────────────────────────
// Thin wrapper: renders ConfigureStep inside a minimal wizard-style frame.
//
// The builderProvider is seeded externally via the ProviderScope override, so
// the ConfigureStep finds a non-null draft immediately. (W2)
// ─────────────────────────────────────────────────────────────────────────────

/// Shows ConfigureStep with a minimal header bar inside a Column, for use
/// in the wizard_configure.png screenshot. (W2)
class _WizardOnConfigureStep extends ConsumerWidget {
  const _WizardOnConfigureStep({
    required this.caseId,
    required this.reportId,
  });

  final String caseId;
  final String reportId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final materialId = ref.watch(activeMaterialProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Minimal header bar for visual context.
        Container(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Row(
            children: [
              const Icon(Icons.settings, size: 18),
              const SizedBox(width: 8),
              Text(
                'Configure — Chart Cards',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
              ),
              const Spacer(),
              Text(
                'Step 2 of 5',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withValues(alpha: 0.6),
                    ),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ConfigureStep(
            key: const Key('configure_step'),
            materialId: materialId,
            caseId: caseId,
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Thin wrapper: renders ReviewStep inside a minimal wizard-style frame. (W3)
// ─────────────────────────────────────────────────────────────────────────────

class _WizardOnReviewStep extends ConsumerWidget {
  const _WizardOnReviewStep({required this.caseId, required this.reportId});
  final String caseId;
  final String reportId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final materialId = ref.watch(activeMaterialProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Row(
            children: [
              const Icon(Icons.preview, size: 18),
              const SizedBox(width: 8),
              Text('Review — Chart Thumbnails',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('Step 3 of 5',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withValues(alpha: 0.6))),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ReviewStep(
            key: const Key('review_step'),
            materialId: materialId,
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Thin wrapper: renders SlidesStep inside a minimal wizard-style frame. (W3)
// ─────────────────────────────────────────────────────────────────────────────

class _WizardOnSlidesStep extends ConsumerWidget {
  const _WizardOnSlidesStep({required this.caseId, required this.reportId});
  final String caseId;
  final String reportId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final materialId = ref.watch(activeMaterialProvider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          child: Row(
            children: [
              const Icon(Icons.slideshow, size: 18),
              const SizedBox(width: 8),
              Text('Slides — Edit Titles',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('Step 4 of 5',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withValues(alpha: 0.6))),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: SlidesStep(
            key: const Key('slides_step'),
            materialId: materialId,
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Thin wrapper: renders DownloadStep inside a minimal wizard-style frame. (W3)
// ─────────────────────────────────────────────────────────────────────────────

class _WizardOnDownloadStep extends StatelessWidget {
  const _WizardOnDownloadStep({required this.caseId, required this.reportId});
  final String caseId;
  final String reportId;

  @override
  Widget build(BuildContext context) {
    return DownloadStep(
      key: const Key('download_step'),
      caseId: caseId,
      reportId: reportId,
    );
  }
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

  // Both QuestionBrowser + ReportBuilder screenshots are captured in one block.
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

  // ── Wizard screenshots (W2) ────────────────────────────────────────────────
  //
  // Produces wizard_select.png (Step 1 — Select) and wizard_configure.png
  // (Step 2 — Configure with 3 pre-seeded chart cards).  Both are at
  // 1300×900 logical pixels to match the W2 brief requirement.
  //
  // wizard_configure.png uses _WizardSeededBuilderNotifier to pre-seed the
  // draft with 3 chart cards so we show ConfigureStep without needing to drive
  // the UI through SelectStep.
  testWidgets(
    'Screenshots: Wizard Select (W2) and Wizard Configure (W2)',
    (tester) async {
      // Desktop viewport — 1300×900 logical pixels (per W2 brief).
      tester.view.physicalSize = const Size(1300, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // ── Part 1: Wizard Select step (wizard_select.png) ──────────────────

      final selectKey = GlobalKey();
      final selectFake = _ScreenshotFakeApi();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(selectFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: selectKey,
                child: const ReportWizard(caseId: 'c1', reportId: 'r1'),
              ),
            ),
          ),
        ),
      );
      // Three pumps: (1) initial frame, (2) postFrameCallback fires + getReport
      // resolves, (3) listQuestions resolves + rebuild with question list.
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Verify SelectStep is visible and questions are listed before capturing.
      expect(
        find.byKey(const Key('select_step')),
        findsOneWidget,
        reason: 'W2: wizard must be on SelectStep for wizard_select.png',
      );
      expect(
        find.byType(CheckboxListTile),
        findsWidgets,
        reason: 'W2: question checklist must be visible in SelectStep',
      );

      await _captureScreenshot(tester, selectKey, 'wizard_select.png');

      // Unmount between screenshots to avoid ProviderScope override conflicts.
      await tester.pumpWidget(const SizedBox.shrink());

      // ── Part 2: Wizard Configure step (wizard_configure.png) ────────────

      final configKey = GlobalKey();
      final configFake = _ScreenshotFakeApi();

      // Pre-seed the draft with 3 chart cards via the builder notifier override
      // so we see ConfigureStep with real chart cards without driving the UI
      // through SelectStep first.
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(configFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
            builderProvider.overrideWith(_WizardSeededBuilderNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: configKey,
                child: const _WizardOnConfigureStep(
                  caseId: 'c1',
                  reportId: 'r1',
                ),
              ),
            ),
          ),
        ),
      );
      // Three pumps: (1) initial render, (2) questions async loads,
      // (3) settle animations.
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Verify ConfigureStep chart cards are visible before capturing.
      expect(
        find.byKey(const Key('configure_step')),
        findsOneWidget,
        reason: 'W2: wizard must show ConfigureStep for wizard_configure.png',
      );
      expect(
        find.byKey(const Key('chart_type_dropdown_0')),
        findsOneWidget,
        reason: 'W2: chart cards must be rendered in ConfigureStep',
      );

      await _captureScreenshot(tester, configKey, 'wizard_configure.png');
    },
  );

  // ── Wizard W3 screenshots ────────────────────────────────────────────────────
  //
  // Produces wizard_review.png (Step 3 — Review), wizard_slides.png
  // (Step 4 — Slides), and wizard_download.png (Step 5 — Download).
  // All at 1300×900 logical pixels.
  //
  // Each screenshot uses _WizardSeededBuilderNotifier (3 pre-loaded chart
  // cards) and _ScreenshotFakeApi via a thin wrapper widget that places the
  // relevant step directly inside a minimal wizard-style frame — same pattern
  // as wizard_configure.png.
  testWidgets(
    'Screenshots: Wizard Review/Slides/Download (W3)',
    (tester) async {
      // Desktop viewport — 1300×900 logical pixels.
      tester.view.physicalSize = const Size(1300, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // ── wizard_review.png ─────────────────────────────────────────────────

      final reviewKey = GlobalKey();
      final reviewFake = _ScreenshotFakeApi();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(reviewFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
            builderProvider.overrideWith(_WizardSeededBuilderNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: reviewKey,
                child: const _WizardOnReviewStep(
                  caseId: 'c1',
                  reportId: 'r1',
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(
        find.byKey(const Key('review_grid')),
        findsOneWidget,
        reason: 'W3: ReviewStep grid must be visible for wizard_review.png',
      );

      await _captureScreenshot(tester, reviewKey, 'wizard_review.png');
      await tester.pumpWidget(const SizedBox.shrink());

      // ── wizard_slides.png ─────────────────────────────────────────────────

      final slidesKey = GlobalKey();
      final slidesFake = _ScreenshotFakeApi();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(slidesFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
            builderProvider.overrideWith(_WizardSeededBuilderNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: slidesKey,
                child: const _WizardOnSlidesStep(
                  caseId: 'c1',
                  reportId: 'r1',
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(
        find.byKey(const Key('slides_list')),
        findsOneWidget,
        reason: 'W3: SlidesStep list must be visible for wizard_slides.png',
      );

      await _captureScreenshot(tester, slidesKey, 'wizard_slides.png');
      await tester.pumpWidget(const SizedBox.shrink());

      // ── wizard_download.png ───────────────────────────────────────────────

      final downloadKey = GlobalKey();
      final downloadFake = _ScreenshotFakeApi();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            nsightApiProvider.overrideWithValue(downloadFake),
            activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
            builderProvider.overrideWith(_WizardSeededBuilderNotifier.new),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: RepaintBoundary(
                key: downloadKey,
                child: const _WizardOnDownloadStep(
                  caseId: 'c1',
                  reportId: 'r1',
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(const Key('generate_button')),
        findsOneWidget,
        reason:
            'W3: Generate button must be visible for wizard_download.png',
      );

      await _captureScreenshot(tester, downloadKey, 'wizard_download.png');
    },
  );
}
