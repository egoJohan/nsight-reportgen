// Unit tests for core models, verifying toJson contract fixes. (FIX-4)
// REQ-C-10 / REQ-C-11 / REQ-C-13 / REQ-C-14 / REQ-C-15.

import 'package:flutter_test/flutter_test.dart';
import 'package:nsight_ui/core/models/models.dart';

void main() {
  // FIX-4 — ChartSpecDef.toJson must always emit the four required keys even
  // when the fields are null, so report_from_json never hits a KeyError.
  group('ChartSpecDef.toJson — required keys always present (FIX-4)', () {
    test('minimal spec (all optional fields null) still has required keys', () {
      const spec = ChartSpecDef(
        questionRef: 'q1',
        chartType: 'vertical_bar',
      );
      final json = spec.toJson();

      // Required by backend report_from_json (KeyError if absent).
      expect(json.containsKey('statistic'), isTrue,
          reason: 'statistic must always be emitted');
      expect(json.containsKey('number_format'), isTrue,
          reason: 'number_format must always be emitted');
      expect(json.containsKey('sort'), isTrue,
          reason: 'sort must always be emitted');
      expect(json.containsKey('elements'), isTrue,
          reason: 'elements must always be emitted');

      // Required unconditional keys.
      expect(json.containsKey('question_ref'), isTrue);
      expect(json.containsKey('chart_type'), isTrue);
      expect(json.containsKey('classifying_var'), isTrue);
      expect(json.containsKey('scatter_xy'), isTrue);
    });

    test('canonical defaults are correct values', () {
      const spec = ChartSpecDef(
        questionRef: 'q1',
        chartType: 'vertical_bar',
      );
      final json = spec.toJson();

      expect(json['statistic'], 'pct');
      expect((json['number_format'] as Map)['pct_decimals'], 0);
      expect((json['number_format'] as Map)['mean_decimals'], 1);
      expect((json['sort'] as Map)['basis'], 'data_order');
      expect((json['elements'] as Map)['title'], true);
      expect(json['classifying_var'], isNull);
      expect(json['scatter_xy'], isNull);
    });

    test('explicit values override canonical defaults', () {
      const spec = ChartSpecDef(
        questionRef: 'q2',
        chartType: 'line',
        statistic: 'mean',
        numberFormat: {'pct_decimals': 2, 'mean_decimals': 3,
                       'count_round_up': true, 'show_pct_sign': false},
        sort: {'basis': 'pct', 'topbox_codes': <dynamic>[], 'descending': false},
        elements: {'title': false, 'legend': true, 'n': false,
                   'axis_names': true, 'filter_var': true, 'data_labels': false},
        classifyingVar: 'gender',
        scatterXy: ['x_var', 'y_var'],
      );
      final json = spec.toJson();

      expect(json['statistic'], 'mean');
      expect((json['number_format'] as Map)['pct_decimals'], 2);
      expect((json['sort'] as Map)['basis'], 'pct');
      expect((json['elements'] as Map)['title'], false);
      expect(json['classifying_var'], 'gender');
      expect(json['scatter_xy'], ['x_var', 'y_var']);
    });

    test('template_slot omitted when null, present when set', () {
      const specNoSlot = ChartSpecDef(
          questionRef: 'q1', chartType: 'bar');
      expect(specNoSlot.toJson().containsKey('template_slot'), isFalse);

      const specWithSlot = ChartSpecDef(
          questionRef: 'q1', chartType: 'bar', templateSlot: 's1');
      expect(specWithSlot.toJson()['template_slot'], 's1');
    });
  });

  // FIX-3 — scatterXy is now List<String>? (not Map).
  group('ChartSpecDef scatterXy type (FIX-3)', () {
    test('scatterXy serialises as JSON array', () {
      const spec = ChartSpecDef(
        questionRef: 'q1',
        chartType: 'scatter',
        scatterXy: ['xvar', 'yvar'],
      );
      final json = spec.toJson();
      expect(json['scatter_xy'], isA<List<String>>());
      expect(json['scatter_xy'], ['xvar', 'yvar']);
    });

    test('fromJson round-trips scatter_xy list', () {
      final json = <String, dynamic>{
        'question_ref': 'q1',
        'chart_type': 'scatter',
        'statistic': 'mean',
        'classifying_var': null,
        'scatter_xy': ['xvar', 'yvar'],
        'number_format': {'pct_decimals': 0, 'mean_decimals': 1,
                          'count_round_up': false, 'show_pct_sign': true},
        'sort': {'basis': 'data_order', 'topbox_codes': <dynamic>[],
                 'descending': true},
        'elements': {'title': true, 'legend': true, 'n': true,
                     'axis_names': true, 'filter_var': true, 'data_labels': true},
      };
      final spec = ChartSpecDef.fromJson(json);
      expect(spec.scatterXy, ['xvar', 'yvar']);
      expect(spec.scatterXy, isA<List<String>>());
    });
  });
}
