// Dio-based client for the nSight REST API.
// REQ-U-04 / C-03..22

import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../models/models.dart';

const String _kDefaultBaseUrl = String.fromEnvironment(
  'NSIGHT_API_BASE',
  defaultValue: 'http://127.0.0.1:8200',
);

/// Thrown when the backend returns a non-2xx response.
class NsightApiException implements Exception {
  const NsightApiException(this.statusCode, this.detail);

  final int statusCode;
  final String detail;

  @override
  String toString() => 'NsightApiException($statusCode): $detail';
}

/// Dio-based HTTP client wrapping the nSight REST API.
///
/// The [Dio] instance is injectable so tests can attach `http_mock_adapter`
/// without touching real network. [baseUrl] is configurable for integration
/// and staging environments.
class NsightApi {
  NsightApi({Dio? dio, String? baseUrl})
      : _dio = dio ?? Dio(),
        _baseUrl = baseUrl ?? _kDefaultBaseUrl {
    _dio.options.baseUrl = _baseUrl;
    _dio.options.connectTimeout = const Duration(seconds: 10);
    _dio.options.receiveTimeout = const Duration(seconds: 30);
  }

  final Dio _dio;
  final String _baseUrl;

  // ---------------------------------------------------------------------------
  // Error mapping
  // ---------------------------------------------------------------------------

  Never _throw(DioException e) {
    final statusCode = e.response?.statusCode ?? 0;
    final data = e.response?.data;
    String detail;
    if (data is Map<String, dynamic> && data.containsKey('detail')) {
      detail = data['detail'].toString();
    } else if (data != null) {
      detail = data.toString();
    } else {
      detail = e.message ?? 'unknown error';
    }
    throw NsightApiException(statusCode, detail);
  }

  // ---------------------------------------------------------------------------
  // Cases
  // ---------------------------------------------------------------------------

  /// Lists all cases. [GET /cases]
  Future<List<CaseRecord>> listCases() async {
    try {
      final res = await _dio.get<List<dynamic>>('/cases');
      return (res.data as List<dynamic>)
          .map((e) => CaseRecord.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Creates a new case with [name]. [POST /cases]
  /// Returns the new `case_id`.
  Future<String> createCase(String name) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/cases',
        data: {'name': name},
      );
      return (res.data as Map<String, dynamic>)['case_id'] as String;
    } on DioException catch (e) {
      _throw(e);
    }
  }

  // ---------------------------------------------------------------------------
  // Materials
  // ---------------------------------------------------------------------------

  /// Uploads a material file (bytes) to [caseId]. [POST /cases/{caseId}/materials]
  /// Returns a record with [materialId] and [questionCount].
  Future<({String materialId, int questionCount})> uploadMaterial(
    String caseId,
    List<int> bytes,
    String filename,
  ) async {
    try {
      final formData = FormData.fromMap({
        'file': MultipartFile.fromBytes(bytes, filename: filename),
      });
      final res = await _dio.post<Map<String, dynamic>>(
        '/cases/$caseId/materials',
        data: formData,
      );
      final body = res.data as Map<String, dynamic>;
      return (
        materialId: body['material_id'] as String,
        questionCount: body['question_count'] as int,
      );
    } on DioException catch (e) {
      _throw(e);
    }
  }

  // ---------------------------------------------------------------------------
  // Questions
  // ---------------------------------------------------------------------------

  /// Lists questions for a material. [GET /materials/{materialId}/questions]
  Future<List<QuestionItem>> listQuestions(String materialId) async {
    try {
      final res =
          await _dio.get<Map<String, dynamic>>('/materials/$materialId/questions');
      final body = res.data as Map<String, dynamic>;
      return (body['questions'] as List<dynamic>)
          .map((e) => QuestionItem.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Sets the grouping for a material. [PUT /materials/{materialId}/grouping]
  /// Returns the updated [QuestionItem].
  Future<QuestionItem> setGrouping(
    String materialId,
    List<String> variables,
    String kind,
  ) async {
    try {
      final res = await _dio.put<Map<String, dynamic>>(
        '/materials/$materialId/grouping',
        data: {'variables': variables, 'kind': kind},
      );
      return QuestionItem.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      _throw(e);
    }
  }

  // ---------------------------------------------------------------------------
  // Reports
  // ---------------------------------------------------------------------------

  /// Creates a new report for [caseId]. [POST /cases/{caseId}/reports]
  /// Returns the new `report_id`.
  Future<String> createReport(String caseId, ReportDef def) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/cases/$caseId/reports',
        data: def.toJson(),
      );
      return (res.data as Map<String, dynamic>)['report_id'] as String;
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Saves (updates) an existing report. [PUT /cases/{caseId}/reports/{reportId}]
  Future<void> saveReport(
    String caseId,
    String reportId,
    ReportDef def,
  ) async {
    try {
      await _dio.put<void>(
        '/cases/$caseId/reports/$reportId',
        data: def.toJson(),
      );
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Fetches a report definition. [GET /cases/{caseId}/reports/{reportId}]
  Future<ReportDef> getReport(String caseId, String reportId) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '/cases/$caseId/reports/$reportId',
      );
      return ReportDef.fromJson(res.data as Map<String, dynamic>);
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Deletes a report. [DELETE /cases/{caseId}/reports/{reportId}]
  Future<void> deleteReport(String caseId, String reportId) async {
    try {
      await _dio.delete<void>('/cases/$caseId/reports/$reportId');
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Duplicates a report under a new [name]. [POST .../duplicate]
  /// Returns the new `report_id`.
  Future<String> duplicateReport(
    String caseId,
    String reportId,
    String name,
  ) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/cases/$caseId/reports/$reportId/duplicate',
        data: {'name': name},
      );
      return (res.data as Map<String, dynamic>)['report_id'] as String;
    } on DioException catch (e) {
      _throw(e);
    }
  }

  // ---------------------------------------------------------------------------
  // Chart preview (W1/W2)
  // ---------------------------------------------------------------------------

  /// Posts one [ChartSpec] JSON to get a PNG preview thumbnail.
  /// [POST /materials/{materialId}/preview-chart] → image/png bytes.
  ///
  /// Throws [NsightApiException] on non-200 or 422 (bad spec). (REQ-C-26)
  Future<Uint8List> previewChart(
    String materialId,
    Map<String, dynamic> chartSpecJson,
  ) async {
    try {
      final res = await _dio.post<List<int>>(
        '/materials/$materialId/preview-chart',
        data: chartSpecJson,
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(res.data as List<int>);
    } on DioException catch (e) {
      _throw(e);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  /// Downloads the preview PDF for a rendered report.
  /// [GET /cases/{caseId}/reports/{reportId}/preview.pdf]
  /// Returns the raw PDF bytes.
  Future<List<int>> getPreviewPdf(String caseId, String reportId) async {
    try {
      final res = await _dio.get<List<int>>(
        '/cases/$caseId/reports/$reportId/preview.pdf',
        options: Options(responseType: ResponseType.bytes),
      );
      return res.data as List<int>;
    } on DioException catch (e) {
      _throw(e);
    }
  }

  /// Renders a report to pptx/pdf/slides preview.
  /// [POST /cases/{caseId}/reports/{reportId}/render]
  /// Returns `{pptx, pdf, preview:[...]}`.
  Future<Map<String, dynamic>> render(
    String caseId,
    String reportId,
    String materialId, {
    String view = 'slides',
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/cases/$caseId/reports/$reportId/render',
        data: {'material_id': materialId, 'view': view},
      );
      return res.data as Map<String, dynamic>;
    } on DioException catch (e) {
      _throw(e);
    }
  }
}
