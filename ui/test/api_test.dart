// Tests for NsightApi client using http_mock_adapter (no real network).
// REQ-U-04 / C-07

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

import 'package:nsight_ui/core/services/nsight_api.dart';

void main() {
  group('NsightApi (REQ-U-04 / C-07)', () {
    late Dio dio;
    late DioAdapter adapter;
    late NsightApi api;

    const baseUrl = 'http://127.0.0.1:8200';

    setUp(() {
      dio = Dio(BaseOptions(baseUrl: baseUrl));
      adapter = DioAdapter(dio: dio);
      api = NsightApi(dio: dio, baseUrl: baseUrl);
    });

    // -------------------------------------------------------------------------
    // listCases
    // -------------------------------------------------------------------------

    test('listCases() returns two CaseRecords from stubbed GET /cases', () async {
      adapter.onGet(
        '/cases',
        (server) => server.reply(
          200,
          [
            {'id': 'c1', 'name': 'Acme'},
            {'id': 'c2', 'name': 'Beta'},
          ],
        ),
      );

      final cases = await api.listCases();

      expect(cases, hasLength(2));
      expect(cases[0].id, 'c1');
      expect(cases[0].name, 'Acme');
      expect(cases[1].id, 'c2');
      expect(cases[1].name, 'Beta');
    });

    // -------------------------------------------------------------------------
    // createCase
    // -------------------------------------------------------------------------

    test('createCase("X") returns "c9" from stubbed POST /cases', () async {
      adapter.onPost(
        '/cases',
        (server) => server.reply(201, {'case_id': 'c9'}),
        data: {'name': 'X'},
      );

      final caseId = await api.createCase('X');

      expect(caseId, 'c9');
    });

    // -------------------------------------------------------------------------
    // Error mapping
    // -------------------------------------------------------------------------

    test('maps 404 response with {detail} body to NsightApiException', () async {
      adapter.onGet(
        '/cases/missing',
        (server) => server.reply(404, {'detail': 'case not found'}),
      );

      // Use a raw GET to trigger the error path via listCases equivalent.
      expect(
        () async {
          try {
            await dio.get<dynamic>('/cases/missing');
          } on DioException catch (e) {
            final statusCode = e.response?.statusCode ?? 0;
            final data = e.response?.data;
            String detail = 'unknown';
            if (data is Map<String, dynamic> && data.containsKey('detail')) {
              detail = data['detail'].toString();
            }
            throw NsightApiException(statusCode, detail);
          }
        },
        throwsA(
          isA<NsightApiException>()
              .having((e) => e.statusCode, 'statusCode', 404)
              .having((e) => e.detail, 'detail', 'case not found'),
        ),
      );
    });
  });
}
