// In-memory fake backend for widget / smoke tests.
// REQ-U-01 — exercises C-03/05/06/07/10/11/19.
//
// [FakeNsightApi] stores cases, questions, and reports in Dart maps.
// No network calls are made; every method resolves immediately (next
// microtask tick via `async`).
//
// Usage:
//   final fake = FakeNsightApi();
//   // Questions for 'mat-smoke' are pre-seeded in the constructor.
//   // Override activeMaterialProvider with 'mat-smoke' to skip upload.
//   ProviderScope(overrides: [nsightApiProvider.overrideWithValue(fake)], ...)

import 'package:dio/dio.dart';

import 'package:nsight_ui/core/models/models.dart';
import 'package:nsight_ui/core/services/nsight_api.dart';

/// In-memory [NsightApi] for widget and smoke tests. (REQ-U-01)
class FakeNsightApi extends NsightApi {
  FakeNsightApi() : super(dio: Dio(), baseUrl: 'http://fake') {
    // Pre-seed a default material so tests that set activeMaterialProvider to
    // 'mat-smoke' find questions immediately without a real upload. (C-05)
    seedMaterial('mat-smoke', _defaultQuestions);
  }

  // ── Internal stores ────────────────────────────────────────────────────────

  final _cases = <CaseRecord>[];
  int _caseSeq = 0;

  // materialId → mutable list of questions
  final _questionsByMaterial = <String, List<QuestionItem>>{};

  // reportId → ReportDef
  final _reports = <String, ReportDef>{};
  int _reportSeq = 0;

  // ── Call tracking (asserted by tests) ─────────────────────────────────────

  /// Names passed to [createCase]. (C-03)
  final List<String> createCaseCalls = [];

  /// Arguments passed to [setGrouping]. (C-06)
  final List<({String materialId, List<String> variables, String kind})>
      setGroupingCalls = [];

  /// Arguments passed to [saveReport]. (C-10)
  final List<({String caseId, String reportId, ReportDef def})>
      saveReportCalls = [];

  /// Arguments passed to [render]. (C-19)
  final List<
      ({String caseId, String reportId, String materialId, String view})>
      renderCalls = [];

  /// True once [getPreviewPdf] has been called. (C-19)
  bool getPreviewPdfCalled = false;

  // ── Seed helper ───────────────────────────────────────────────────────────

  /// Seeds [questions] for [materialId].
  ///
  /// Called automatically by the constructor for `'mat-smoke'`. Tests that
  /// need a different material can call this before pumping the widget tree.
  void seedMaterial(String materialId, List<QuestionItem> questions) {
    _questionsByMaterial[materialId] = List.of(questions);
  }

  /// Default questions available for the `'mat-smoke'` material. (C-05)
  static const _defaultQuestions = [
    QuestionItem(
      qid: 'q1',
      kind: 'single',
      variables: ['q1'],
      text: 'Overall satisfaction',
    ),
    QuestionItem(
      qid: 'q2',
      kind: 'single',
      variables: ['q2'],
      text: 'Net promoter score',
    ),
  ];

  // ── Cases (C-03 / C-07) ───────────────────────────────────────────────────

  @override
  Future<List<CaseRecord>> listCases() async => List.of(_cases);

  @override
  Future<String> createCase(String name) async {
    createCaseCalls.add(name);
    final id = 'case-${++_caseSeq}';
    _cases.add(CaseRecord(id: id, name: name));
    return id;
  }

  // ── Materials (C-01 / C-04) ───────────────────────────────────────────────

  /// Returns a fixed materialId and seeds the question list so [listQuestions]
  /// returns meaningful data without a real SPSS file. (C-04)
  @override
  Future<({String materialId, int questionCount})> uploadMaterial(
    String caseId,
    List<int> bytes,
    String filename,
  ) async {
    const materialId = 'mat-uploaded';
    seedMaterial(materialId, _defaultQuestions);
    return (
      materialId: materialId,
      questionCount: _defaultQuestions.length,
    );
  }

  // ── Questions (C-05 / C-06) ───────────────────────────────────────────────

  @override
  Future<List<QuestionItem>> listQuestions(String materialId) async =>
      List.of(_questionsByMaterial[materialId] ?? const []);

  /// Updates the in-memory kind for the matched question and records the call.
  /// (C-06)
  @override
  Future<QuestionItem> setGrouping(
    String materialId,
    List<String> variables,
    String kind,
  ) async {
    setGroupingCalls.add((
      materialId: materialId,
      variables: variables,
      kind: kind,
    ));
    final questions = _questionsByMaterial[materialId];
    if (questions != null) {
      final idx = questions.indexWhere(
        (q) => q.variables.any(variables.contains),
      );
      if (idx != -1) {
        final updated = QuestionItem(
          qid: questions[idx].qid,
          kind: kind,
          variables: questions[idx].variables,
          text: questions[idx].text,
        );
        questions[idx] = updated;
        return updated;
      }
    }
    // Fallback: synthesise a minimal item.
    return QuestionItem(
      qid: variables.first,
      kind: kind,
      variables: variables,
      text: '',
    );
  }

  // ── Reports (C-07 / C-09 / C-10) ─────────────────────────────────────────

  @override
  Future<String> createReport(String caseId, ReportDef def) async {
    final id = 'rep-${++_reportSeq}';
    _reports[id] = def;
    return id;
  }

  @override
  Future<ReportDef> getReport(String caseId, String reportId) async =>
      _reports[reportId] ??
      const ReportDef(
        name: 'Unknown',
        renderMode: 'native',
        templateRef: 'default',
        charts: [],
      );

  @override
  Future<void> saveReport(
    String caseId,
    String reportId,
    ReportDef def,
  ) async {
    saveReportCalls.add((caseId: caseId, reportId: reportId, def: def));
    _reports[reportId] = def;
  }

  @override
  Future<void> deleteReport(String caseId, String reportId) async {
    _reports.remove(reportId);
  }

  @override
  Future<String> duplicateReport(
    String caseId,
    String reportId,
    String name,
  ) async {
    final original = _reports[reportId];
    final id = 'rep-${++_reportSeq}';
    _reports[id] = original != null
        ? ReportDef(
            name: name,
            renderMode: original.renderMode,
            templateRef: original.templateRef,
            charts: original.charts,
          )
        : ReportDef(
            name: name,
            renderMode: 'native',
            templateRef: 'default',
            charts: const [],
          );
    return id;
  }

  // ── Render (C-19) ─────────────────────────────────────────────────────────

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
      'pptx': 'smoke.pptx',
      'pdf': 'smoke.pdf',
      'preview': <dynamic>[],
      'pdf_url': '/cases/$caseId/reports/$reportId/preview.pdf',
    };
  }

  /// Returns minimal dummy PDF bytes (%PDF magic). (C-19)
  @override
  Future<List<int>> getPreviewPdf(String caseId, String reportId) async {
    getPreviewPdfCalled = true;
    return [37, 80, 68, 70]; // %PDF
  }
}
