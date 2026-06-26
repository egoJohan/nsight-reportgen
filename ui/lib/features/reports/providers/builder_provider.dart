// Report-builder Riverpod state: draft editing + save.
// REQ-C-10 / REQ-C-11 / REQ-C-13 / REQ-C-14 / REQ-C-15 / REQ-C-26.

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../../core/providers/api_provider.dart';

// ---------------------------------------------------------------------------
// Draft model
// ---------------------------------------------------------------------------

/// In-memory representation of a report while it is being edited.
class ReportDraft {
  const ReportDraft({
    required this.name,
    required this.renderMode,
    required this.charts,
  });

  final String name;
  final String renderMode;
  final List<ChartSpecDef> charts;

  ReportDraft copyWith({
    String? name,
    String? renderMode,
    List<ChartSpecDef>? charts,
  }) =>
      ReportDraft(
        name: name ?? this.name,
        renderMode: renderMode ?? this.renderMode,
        charts: charts ?? this.charts,
      );
}

// ---------------------------------------------------------------------------
// Default values applied to newly added chart cards (REQ-C-11)
// ---------------------------------------------------------------------------

const _kDefaultNumberFormat = <String, dynamic>{
  'pct_decimals': 0,
  'mean_decimals': 1,
  'count_round_up': false,
  'show_pct_sign': true,
};

const _kDefaultSort = <String, dynamic>{
  'basis': 'pct',  // REQ-S-03: default sort by percentage magnitude descending
  'topbox_codes': <dynamic>[],
  'descending': true,
};

const _kDefaultElements = <String, dynamic>{
  'title': true,
  'legend': true,
  'n': true,
  'axis_names': true,
  'filter_var': true,
  'data_labels': true,
};

// ---------------------------------------------------------------------------
// Notifier
// ---------------------------------------------------------------------------

/// Manages draft state for the currently-open report.
///
/// State is null until [load] is called. [save] writes back to the API
/// with `template_slot` auto-assigned by card position (REQ-C-10).
class ReportBuilderNotifier extends Notifier<ReportDraft?> {
  @override
  ReportDraft? build() => null;

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  /// Clears the draft back to null (called on builder close or case switch). (FIX-2)
  void reset() => state = null;

  /// Fetches the report and initialises the draft. (REQ-C-10)
  Future<void> load(String caseId, String reportId) async {
    final api = ref.read(nsightApiProvider);
    final def = await api.getReport(caseId, reportId);
    state = ReportDraft(
      name: def.name,
      renderMode: def.renderMode,
      charts: def.charts,
    );
  }

  // ── Mutations ──────────────────────────────────────────────────────────────

  /// Appends a default [ChartSpecDef] for each qid in [qids]. (REQ-C-11)
  ///
  /// Defaults: chart_type vertical_bar, statistic pct, no classifying var.
  void addQuestions(List<String> qids) {
    if (state == null) return;
    final newCards = qids
        .map(
          (qid) => ChartSpecDef(
            questionRef: qid,
            chartType: 'vertical_bar',
            statistic: 'pct',
            classifyingVar: null,
            numberFormat: _kDefaultNumberFormat,
            sort: _kDefaultSort,
            elements: _kDefaultElements,
            scatterXy: null,
          ),
        )
        .toList();
    state = state!.copyWith(charts: [...state!.charts, ...newCards]);
  }

  /// Appends chart cards for [items], using each question's
  /// [QuestionItem.suggestedChartType] as the chart type. (W2 — REQ-U-01/11)
  ///
  /// Defaults: statistic pct, show_not_answered off, no classifying var.
  void addQuestionsFromItems(List<QuestionItem> items) {
    if (state == null) return;
    final newCards = items
        .map(
          (q) => ChartSpecDef(
            questionRef: q.qid,
            chartType: q.suggestedChartType,
            statistic: 'pct',
            classifyingVar: null,
            numberFormat: _kDefaultNumberFormat,
            sort: _kDefaultSort,
            elements: <String, dynamic>{
              ..._kDefaultElements,
              'not_answered': false,
            },
            scatterXy: null,
          ),
        )
        .toList();
    state = state!.copyWith(charts: [...state!.charts, ...newCards]);
  }

  /// Replaces the card at [index] with [spec]. (REQ-C-14)
  void updateChart(int index, ChartSpecDef spec) {
    if (state == null) return;
    final charts = List<ChartSpecDef>.of(state!.charts);
    charts[index] = spec;
    state = state!.copyWith(charts: charts);
  }

  /// Removes the card at [index]. (REQ-C-15)
  void removeChart(int index) {
    if (state == null) return;
    final charts = List<ChartSpecDef>.of(state!.charts)..removeAt(index);
    state = state!.copyWith(charts: charts);
  }

  /// Reorders cards (ReorderableListView semantics: newIndex is post-remove).
  void reorder(int oldIndex, int newIndex) {
    if (state == null) return;
    final charts = List<ChartSpecDef>.of(state!.charts);
    final item = charts.removeAt(oldIndex);
    final insertAt = newIndex > oldIndex ? newIndex - 1 : newIndex;
    charts.insert(insertAt, item);
    state = state!.copyWith(charts: charts);
  }

  /// Updates the report name.
  void setName(String name) {
    if (state == null) return;
    state = state!.copyWith(name: name);
  }

  /// Updates the render mode ('native' | 'image').
  void setMode(String mode) {
    if (state == null) return;
    state = state!.copyWith(renderMode: mode);
  }

  // ── Persistence ────────────────────────────────────────────────────────────

  /// Saves the current draft to the backend.
  ///
  /// `template_slot` is auto-assigned by card position (REQ-C-10).
  /// Throws [NsightApiException] on error — the caller catches it.
  Future<void> save(String caseId, String reportId) async {
    if (state == null) return;
    final draft = state!;
    // template_slot is assigned by ReportDef.toJson() via copyWith; calling
    // toJson() on the ReportDef will produce the correct positions.
    final def = ReportDef(
      name: draft.name,
      renderMode: draft.renderMode,
      templateRef: 'default',
      charts: draft.charts,
    );
    final api = ref.read(nsightApiProvider);
    await api.saveReport(caseId, reportId, def);
  }
}

/// Session-scoped builder state. One report open at a time.
final builderProvider = NotifierProvider<ReportBuilderNotifier, ReportDraft?>(
  ReportBuilderNotifier.new,
);
