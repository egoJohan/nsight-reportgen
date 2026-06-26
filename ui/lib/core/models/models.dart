// Core data models for the nSight API.
// REQ-U-04 / C-07

/// A case record returned by GET /cases.
class CaseRecord {
  const CaseRecord({required this.id, required this.name});

  final String id;
  final String name;

  factory CaseRecord.fromJson(Map<String, dynamic> json) => CaseRecord(
        id: json['id'] as String,
        name: json['name'] as String,
      );

  Map<String, dynamic> toJson() => {'id': id, 'name': name};
}

/// A question item returned by GET /materials/{materialId}/questions.
class QuestionItem {
  const QuestionItem({
    required this.qid,
    required this.kind,
    required this.variables,
    required this.text,
  });

  final String qid;
  final String kind;
  final List<String> variables;
  final String text;

  factory QuestionItem.fromJson(Map<String, dynamic> json) => QuestionItem(
        qid: json['qid'] as String,
        kind: json['kind'] as String,
        variables: (json['variables'] as List<dynamic>).cast<String>(),
        text: json['text'] as String,
      );

  Map<String, dynamic> toJson() => {
        'qid': qid,
        'kind': kind,
        'variables': variables,
        'text': text,
      };
}

// ---------------------------------------------------------------------------
// Canonical JSON defaults for ChartSpecDef required keys (FIX-4).
// These match the backend's NumberFormat(), SortSpec(), ElementToggles()
// zero-argument constructors so report_from_json never hits a KeyError.
// ---------------------------------------------------------------------------

const _kDefaultStatistic = 'pct';

const _kDefaultNumberFormatJson = <String, dynamic>{
  'pct_decimals': 0,
  'mean_decimals': 1,
  'count_round_up': false,
  'show_pct_sign': true,
};

const _kDefaultSortJson = <String, dynamic>{
  'basis': 'data_order',
  'topbox_codes': <dynamic>[],
  'descending': true,
};

const _kDefaultElementsJson = <String, dynamic>{
  'title': true,
  'legend': true,
  'n': true,
  'axis_names': true,
  'filter_var': true,
  'data_labels': true,
};

/// A chart specification within a report definition.
/// Mirrors the backend ChartSpec keys in snake_case.
///
/// [scatterXy] is a two-element list [xVar, yVar] used only when
/// [chartType] is 'scatter'.
class ChartSpecDef {
  const ChartSpecDef({
    required this.questionRef,
    required this.chartType,
    this.statistic,
    this.classifyingVar,
    this.numberFormat,
    this.sort,
    this.templateSlot,
    this.elements,
    this.scatterXy,
  });

  final String questionRef;
  final String chartType;
  final String? statistic;
  final String? classifyingVar;
  final Map<String, dynamic>? numberFormat;
  final Map<String, dynamic>? sort;
  final String? templateSlot;
  final Map<String, dynamic>? elements;
  /// Two-element [xVar, yVar] for scatter charts; null for all others.
  final List<String>? scatterXy;

  factory ChartSpecDef.fromJson(Map<String, dynamic> json) => ChartSpecDef(
        questionRef: json['question_ref'] as String,
        chartType: json['chart_type'] as String,
        statistic: json['statistic'] as String?,
        classifyingVar: json['classifying_var'] as String?,
        numberFormat: json['number_format'] as Map<String, dynamic>?,
        sort: json['sort'] as Map<String, dynamic>?,
        templateSlot: json['template_slot'] as String?,
        elements: json['elements'] as Map<String, dynamic>?,
        scatterXy:
            (json['scatter_xy'] as List<dynamic>?)?.cast<String>(),
      );

  /// Produces the exact snake_case keys the backend's report_from_json expects.
  ///
  /// Required keys (`statistic`, `number_format`, `sort`, `elements`) are
  /// ALWAYS present — null fields fall back to their canonical backend defaults
  /// so report_from_json never hits a KeyError. (FIX-4)
  ///
  /// `classifying_var` and `scatter_xy` are always emitted (may be null).
  /// `template_slot` is emitted when set (auto-assigned in [ReportDef.toJson]).
  Map<String, dynamic> toJson() {
    final m = <String, dynamic>{
      'question_ref': questionRef,
      'chart_type': chartType,
      // Always emit — backend raises KeyError if absent. (FIX-4)
      'statistic': statistic ?? _kDefaultStatistic,
      // Always emit classifying_var — null means no segmentation.
      'classifying_var': classifyingVar,
      // Always emit with canonical defaults when null. (FIX-4)
      'number_format': numberFormat ?? _kDefaultNumberFormatJson,
      'sort': sort ?? _kDefaultSortJson,
      'elements': elements ?? _kDefaultElementsJson,
    };
    if (templateSlot != null) m['template_slot'] = templateSlot;
    // Always emit scatter_xy — null for non-scatter charts.
    m['scatter_xy'] = scatterXy;
    return m;
  }

  /// Returns a copy with the given fields replaced.
  ChartSpecDef copyWith({
    String? questionRef,
    String? chartType,
    Object? statistic = _sentinel,
    Object? classifyingVar = _sentinel,
    Object? numberFormat = _sentinel,
    Object? sort = _sentinel,
    Object? templateSlot = _sentinel,
    Object? elements = _sentinel,
    Object? scatterXy = _sentinel,
  }) =>
      ChartSpecDef(
        questionRef: questionRef ?? this.questionRef,
        chartType: chartType ?? this.chartType,
        statistic:
            statistic == _sentinel ? this.statistic : statistic as String?,
        classifyingVar: classifyingVar == _sentinel
            ? this.classifyingVar
            : classifyingVar as String?,
        numberFormat: numberFormat == _sentinel
            ? this.numberFormat
            : numberFormat as Map<String, dynamic>?,
        sort: sort == _sentinel ? this.sort : sort as Map<String, dynamic>?,
        templateSlot: templateSlot == _sentinel
            ? this.templateSlot
            : templateSlot as String?,
        elements: elements == _sentinel
            ? this.elements
            : elements as Map<String, dynamic>?,
        scatterXy: scatterXy == _sentinel
            ? this.scatterXy
            : scatterXy as List<String>?,
      );
}

/// Sentinel object used by [ChartSpecDef.copyWith] to distinguish null from
/// "not provided".
const Object _sentinel = Object();

/// A full report definition — sent to and received from the backend.
class ReportDef {
  const ReportDef({
    required this.name,
    required this.renderMode,
    required this.templateRef,
    required this.charts,
  });

  final String name;
  final String renderMode;
  final String templateRef;
  final List<ChartSpecDef> charts;

  factory ReportDef.fromJson(Map<String, dynamic> json) => ReportDef(
        name: json['name'] as String,
        renderMode: json['render_mode'] as String,
        templateRef: json['template_ref'] as String,
        charts: (json['charts'] as List<dynamic>)
            .map((e) => ChartSpecDef.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  /// Produces the exact snake_case keys the backend's report_from_json expects.
  ///
  /// `template_slot` is auto-assigned to `s{index+1}` by chart card position.
  Map<String, dynamic> toJson() => {
        'name': name,
        'render_mode': renderMode,
        'template_ref': templateRef,
        'charts': [
          for (var i = 0; i < charts.length; i++)
            charts[i].copyWith(templateSlot: 's${i + 1}').toJson(),
        ],
      };
}
