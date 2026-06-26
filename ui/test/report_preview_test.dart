// Widget tests for the report preview panel — Task 8.8b.
// REQ-C-19a / REQ-C-19b / REQ-C-21 / REQ-C-22.

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nsight_ui/core/providers/api_provider.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';
import 'package:nsight_ui/features/data/providers/material_provider.dart';
import 'package:nsight_ui/features/reports/report_preview.dart';

// ---------------------------------------------------------------------------
// Fake API
// ---------------------------------------------------------------------------

/// Dummy PDF bytes used by the fake API. (REQ-C-22)
const _kDummyPdfBytes = <int>[37, 80, 68, 70]; // %PDF header

class _FakeNsightApi extends NsightApi {
  _FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake');

  /// Calls captured by [render]. (REQ-C-21)
  final List<
      ({
        String caseId,
        String reportId,
        String materialId,
        String view,
      })> renderCalls = [];

  /// True if [getPreviewPdf] was called. (REQ-C-22)
  bool getPreviewPdfCalled = false;

  @override
  Future<Map<String, dynamic>> render(
    String caseId,
    String reportId,
    String materialId, {
    String view = 'slides',
  }) async {
    renderCalls.add((
      caseId: caseId,
      reportId: reportId,
      materialId: materialId,
      view: view,
    ));
    return {
      'pptx': 'x',
      'pdf': 'y',
      'preview': <dynamic>[],
      'pdf_url': '/cases/$caseId/reports/$reportId/preview.pdf',
    };
  }

  @override
  Future<List<int>> getPreviewPdf(String caseId, String reportId) async {
    getPreviewPdfCalled = true;
    return _kDummyPdfBytes;
  }
}

// ---------------------------------------------------------------------------
// Seeded notifier — provides a materialId so Render isn't blocked.
// ---------------------------------------------------------------------------

class _SeededMaterialNotifier extends ActiveMaterialNotifier {
  @override
  String? build() => 'mat-test';
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

Widget _harness(_FakeNsightApi fake) => ProviderScope(
      overrides: [
        nsightApiProvider.overrideWithValue(fake),
        activeMaterialProvider.overrideWith(_SeededMaterialNotifier.new),
      ],
      child: const MaterialApp(
        home: Scaffold(
          body: ReportPreview(caseId: 'c1', reportId: 'r1'),
        ),
      ),
    );

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  // REQ-C-19a — Render button and Slides/Pages toggle are visible.
  group('ReportPreview — initial UI (REQ-C-19a)', () {
    testWidgets('shows Render button and Slides/Pages segmented button',
        (tester) async {
      // REQ-C-19a — SegmentedButton and Render button must be present on load.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // Render button present. (REQ-C-21)
      expect(
        find.byKey(const Key('render_preview_button')),
        findsOneWidget,
        reason: 'REQ-C-21: Render button must be present',
      );

      // Slides/Pages toggle present. (REQ-C-19a)
      expect(
        find.byKey(const Key('view_toggle')),
        findsOneWidget,
        reason: 'REQ-C-19a: Slides/Pages segmented button must be present',
      );

      // 'Render to preview' placeholder shown before any render. (REQ-C-22)
      expect(
        find.byKey(const Key('render_to_preview_placeholder')),
        findsOneWidget,
      );
    });
  });

  // REQ-C-21 / REQ-C-22 — tapping Render calls render + getPreviewPdf and
  // shows the PdfView (stub placeholder on VM).
  group('ReportPreview — tap Render (REQ-C-21 / REQ-C-22)', () {
    testWidgets(
        'tapping Render calls render with materialId and current view, '
        'calls getPreviewPdf, and shows the pdf viewer', (tester) async {
      // REQ-C-21 — render called with correct materialId and view.
      // REQ-C-22 — getPreviewPdf called; PdfView stub rendered.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // Tap Render.
      await tester.tap(find.byKey(const Key('render_preview_button')));
      await tester.pumpAndSettle();

      // render() was called with the correct materialId and default view.
      expect(fake.renderCalls, hasLength(1),
          reason: 'REQ-C-21: render must be called once');
      expect(fake.renderCalls.first.materialId, 'mat-test',
          reason: 'REQ-C-21: render must use activeMaterialProvider value');
      expect(fake.renderCalls.first.view, 'slides',
          reason: 'REQ-C-21: initial view must be "slides"');

      // getPreviewPdf() was called. (REQ-C-22)
      expect(fake.getPreviewPdfCalled, isTrue,
          reason: 'REQ-C-22: getPreviewPdf must be called after render');

      // The PdfView (stub on VM) is rendered; placeholder is gone.
      expect(
        find.byKey(const Key('pdf_view')),
        findsOneWidget,
        reason: 'REQ-C-22: PdfView must appear after successful render',
      );
      expect(find.byKey(const Key('render_to_preview_placeholder')),
          findsNothing);
    });
  });

  // REQ-C-19b — toggling to 'Pages (PDF)' re-renders with view: 'pages'.
  group('ReportPreview — toggle to Pages (REQ-C-19b)', () {
    testWidgets(
        'toggling to Pages (PDF) after a Slides render calls render again '
        'with view: pages', (tester) async {
      // REQ-C-19b — changing the toggle must re-render with the new view.
      final fake = _FakeNsightApi();
      await tester.pumpWidget(_harness(fake));
      await tester.pumpAndSettle();

      // First render (Slides).
      await tester.tap(find.byKey(const Key('render_preview_button')));
      await tester.pumpAndSettle();
      expect(fake.renderCalls, hasLength(1));

      // Toggle to Pages (PDF). (REQ-C-19b)
      await tester.tap(find.text('Pages (PDF)'));
      await tester.pumpAndSettle();

      // render() was called a second time with view: 'pages'. (REQ-C-19b)
      expect(fake.renderCalls, hasLength(2),
          reason: 'REQ-C-19b: render must be called again when view toggles');
      expect(fake.renderCalls.last.view, 'pages',
          reason: 'REQ-C-19b: render must be called with view: pages');
    });
  });
}
