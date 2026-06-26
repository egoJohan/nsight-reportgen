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

/// A chart specification within a report definition.
/// Mirrors the backend ChartSpec keys in snake_case.
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
  // Kept loose for now; task 8.7 fills these in.
  final Map<String, dynamic>? numberFormat;
  final Map<String, dynamic>? sort;
  final String? templateSlot;
  final Map<String, dynamic>? elements;
  final Map<String, dynamic>? scatterXy;

  factory ChartSpecDef.fromJson(Map<String, dynamic> json) => ChartSpecDef(
        questionRef: json['question_ref'] as String,
        chartType: json['chart_type'] as String,
        statistic: json['statistic'] as String?,
        classifyingVar: json['classifying_var'] as String?,
        numberFormat: json['number_format'] as Map<String, dynamic>?,
        sort: json['sort'] as Map<String, dynamic>?,
        templateSlot: json['template_slot'] as String?,
        elements: json['elements'] as Map<String, dynamic>?,
        scatterXy: json['scatter_xy'] as Map<String, dynamic>?,
      );

  /// Produces the exact snake_case keys the backend's report_from_json expects.
  Map<String, dynamic> toJson() {
    final m = <String, dynamic>{
      'question_ref': questionRef,
      'chart_type': chartType,
    };
    if (statistic != null) m['statistic'] = statistic;
    if (classifyingVar != null) m['classifying_var'] = classifyingVar;
    if (numberFormat != null) m['number_format'] = numberFormat;
    if (sort != null) m['sort'] = sort;
    if (templateSlot != null) m['template_slot'] = templateSlot;
    if (elements != null) m['elements'] = elements;
    if (scatterXy != null) m['scatter_xy'] = scatterXy;
    return m;
  }
}

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
  Map<String, dynamic> toJson() => {
        'name': name,
        'render_mode': renderMode,
        'template_ref': templateRef,
        'charts': charts.map((c) => c.toJson()).toList(),
      };
}
