// Session-scoped reports list and selected-report state.
// REQ-U-06 / REQ-C-07 / REQ-C-09.
//
// TODO(list-reports): the backend has no GET /cases/{id}/reports endpoint yet
// (addendum 3). The session list therefore starts empty on each launch.
// Persistent listing awaits that endpoint; all create/duplicate/delete calls
// are real API operations today.

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../../core/providers/api_provider.dart';

/// Lightweight in-session summary of a report.
class ReportSummary {
  const ReportSummary({
    required this.id,
    required this.name,
    required this.renderMode,
  });

  final String id;
  final String name;
  final String renderMode;
}

/// Manages the session-scoped list of [ReportSummary] items.
///
/// State starts empty each session.
/// TODO(list-reports): populate from GET /cases/{id}/reports when available.
class ReportsNotifier extends Notifier<List<ReportSummary>> {
  @override
  List<ReportSummary> build() => const [];

  /// Calls [createReport] on the API and appends the new summary.
  /// REQ-U-06, REQ-C-07
  Future<String> create(
    String caseId,
    String name,
    String renderMode,
  ) async {
    final api = ref.read(nsightApiProvider);
    final def = ReportDef(
      name: name,
      renderMode: renderMode,
      templateRef: 'default',
      charts: const [],
    );
    final id = await api.createReport(caseId, def);
    state = [
      ...state,
      ReportSummary(id: id, name: name, renderMode: renderMode),
    ];
    return id;
  }

  /// Calls [duplicateReport] on the API and appends the duplicated summary.
  /// REQ-C-09
  Future<void> duplicate(
    String caseId,
    String reportId,
    String newName,
  ) async {
    final api = ref.read(nsightApiProvider);
    final original = state.firstWhere((r) => r.id == reportId);
    final newId = await api.duplicateReport(caseId, reportId, newName);
    state = [
      ...state,
      ReportSummary(id: newId, name: newName, renderMode: original.renderMode),
    ];
  }

  /// Calls [deleteReport] on the API and removes the summary from the list.
  Future<void> remove(String caseId, String reportId) async {
    final api = ref.read(nsightApiProvider);
    await api.deleteReport(caseId, reportId);
    state = state.where((r) => r.id != reportId).toList();
  }
}

/// Session-scoped list of reports. Starts empty; mutated by create/duplicate/remove.
final reportsProvider =
    NotifierProvider<ReportsNotifier, List<ReportSummary>>(
  ReportsNotifier.new,
);

// ---------------------------------------------------------------------------
// Selected report (used by the builder — Task 8.7)
// ---------------------------------------------------------------------------

/// Holds the id of the report currently open in the report builder.
/// Null when no report is selected. Defined here so Task 8.7 can consume it.
class SelectedReportNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  void select(String? id) => state = id;
}

final selectedReportProvider =
    NotifierProvider<SelectedReportNotifier, String?>(
  SelectedReportNotifier.new,
);
