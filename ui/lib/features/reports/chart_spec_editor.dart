// Chart card editor: all dropdowns, fields, and checkboxes for one ChartSpecDef.
// REQ-C-11 / REQ-C-13 / REQ-C-14 / REQ-C-15 / REQ-C-26.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../data/providers/questions_provider.dart';
import 'providers/builder_provider.dart';

// ---------------------------------------------------------------------------
// Option tables (REQ-C-11 / REQ-C-13)
// ---------------------------------------------------------------------------

/// All 11 chart types supported by the backend. (REQ-C-13)
const _kChartTypes = <(String, String)>[
  ('line', 'Line'),
  ('pie', 'Pie'),
  ('vertical_bar', 'Vertical bar'),
  ('stacked_vertical_bar', 'Stacked vertical bar'),
  ('horizontal_bar', 'Horizontal bar'),
  ('stacked_horizontal_bar', 'Stacked horizontal bar'),
  ('radar', 'Radar'),
  ('doughnut', 'Doughnut'),
  ('scatter', 'Scatter'),
  ('funnel', 'Funnel'),
  ('combo', 'Combo'),
];

const _kStatistics = <(String, String)>[
  ('pct', 'Percent'),
  ('count', 'Count'),
  ('mean', 'Mean'),
  ('median', 'Median'),
  ('sum', 'Sum'),
];

const _kSortBases = <(String, String)>[
  ('data_order', 'Data order'),
  ('pct', 'Percent'),
  ('topbox_sum', 'Topbox sum'),
  ('mean', 'Mean'),
  ('count', 'Count'),
];

// ---------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------

/// Card UI for configuring one [ChartSpecDef].
///
/// Every change calls [ReportBuilderNotifier.updateChart]. The card is wrapped
/// in a [ReorderableListView] item by the parent; drag-and-drop is provided by
/// that list. (REQ-C-14 / REQ-C-15)
class ChartSpecEditor extends ConsumerWidget {
  const ChartSpecEditor({
    super.key,
    required this.index,
    required this.spec,
    required this.renderMode,
  });

  final int index;
  final ChartSpecDef spec;

  /// Current report render mode — used to disable combo when 'native'.
  /// (REQ-C-13)
  final String renderMode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Build classifying-var options from single questions in the material.
    final questionsAsync = ref.watch(questionsProvider);
    final singleVars = questionsAsync.asData?.value
            .where((q) => q.kind == 'single')
            .expand((q) => q.variables)
            .toList() ??
        const <String>[];

    void update(ChartSpecDef updated) {
      ref.read(builderProvider.notifier).updateChart(index, updated);
    }

    // Compute chart-type items; combo disabled when native. (REQ-C-13)
    final chartTypeItems = _kChartTypes
        .where((t) => !(t.$1 == 'combo' && renderMode == 'native'))
        .map(
          (t) => DropdownMenuItem<String>(
            value: t.$1,
            child: Text(t.$2),
          ),
        )
        .toList();

    // Ensure current value is valid (safety if combo was selected before
    // switching to native).
    final currentChartType =
        chartTypeItems.any((i) => i.value == spec.chartType)
            ? spec.chartType
            : chartTypeItems.first.value!;

    final nf = spec.numberFormat ?? const <String, dynamic>{};
    final el = spec.elements ?? const <String, dynamic>{};
    final sortMap = spec.sort ?? const <String, dynamic>{};

    final pctDecimals = (nf['pct_decimals'] as int?) ?? 0;
    final meanDecimals = (nf['mean_decimals'] as int?) ?? 1;
    final sortBasis = (sortMap['basis'] as String?) ?? 'data_order';

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header: question ref + remove button
            Row(
              children: [
                Expanded(
                  child: Text(
                    spec.questionRef,
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
                IconButton(
                  key: Key('remove_chart_$index'),
                  icon: const Icon(Icons.close),
                  tooltip: 'Remove chart',
                  onPressed: () =>
                      ref.read(builderProvider.notifier).removeChart(index),
                ),
              ],
            ),
            const Divider(height: 16),

            // Chart type (REQ-C-13)
            DropdownButtonFormField<String>(
              key: const Key('chart_type_dropdown'),
              decoration: const InputDecoration(labelText: 'Chart type'),
              initialValue: currentChartType,
              items: chartTypeItems,
              onChanged: (v) {
                if (v == null) return;
                var updated = spec.copyWith(chartType: v);
                if (v == 'scatter' && spec.scatterXy == null) {
                  // Auto-init scatter_xy to first two available variables. (FIX-3)
                  final x = singleVars.isNotEmpty ? singleVars[0] : null;
                  final y = singleVars.length >= 2 ? singleVars[1] : x;
                  if (x != null && y != null) {
                    updated = updated.copyWith(scatterXy: [x, y]);
                  }
                } else if (v != 'scatter') {
                  // Clear scatter_xy when switching away from scatter.
                  updated = updated.copyWith(scatterXy: null);
                }
                update(updated);
              },
            ),
            const SizedBox(height: 8),

            // Statistic
            DropdownButtonFormField<String>(
              key: const Key('statistic_dropdown'),
              decoration: const InputDecoration(labelText: 'Statistic'),
              initialValue: spec.statistic ?? 'pct',
              items: _kStatistics
                  .map(
                    (s) => DropdownMenuItem<String>(
                      value: s.$1,
                      child: Text(s.$2),
                    ),
                  )
                  .toList(),
              onChanged: (v) {
                if (v != null) update(spec.copyWith(statistic: v));
              },
            ),
            const SizedBox(height: 8),

            // Classifying var (REQ-C-14)
            DropdownButtonFormField<String?>(
              key: const Key('classifying_var_dropdown'),
              decoration:
                  const InputDecoration(labelText: 'Classifying variable'),
              initialValue: singleVars.contains(spec.classifyingVar)
                  ? spec.classifyingVar
                  : null,
              items: [
                const DropdownMenuItem<String?>(
                  value: null,
                  child: Text('None'),
                ),
                ...singleVars.map(
                  (v) => DropdownMenuItem<String?>(
                    value: v,
                    child: Text(v),
                  ),
                ),
              ],
              onChanged: (v) => update(spec.copyWith(classifyingVar: v)),
            ),
            const SizedBox(height: 8),

            // Scatter X / Y variables — shown only for scatter charts. (FIX-3)
            if (currentChartType == 'scatter') ...[
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                key: const Key('scatter_x_dropdown'),
                decoration: const InputDecoration(labelText: 'Scatter X'),
                initialValue:
                    singleVars.contains(spec.scatterXy?.elementAtOrNull(0))
                        ? spec.scatterXy![0]
                        : (singleVars.isNotEmpty ? singleVars[0] : null),
                items: singleVars
                    .map(
                      (v) => DropdownMenuItem<String>(
                        value: v,
                        child: Text(v),
                      ),
                    )
                    .toList(),
                onChanged: (v) {
                  if (v == null) return;
                  final y = spec.scatterXy?.elementAtOrNull(1) ?? v;
                  update(spec.copyWith(scatterXy: [v, y]));
                },
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                key: const Key('scatter_y_dropdown'),
                decoration: const InputDecoration(labelText: 'Scatter Y'),
                initialValue:
                    singleVars.contains(spec.scatterXy?.elementAtOrNull(1))
                        ? spec.scatterXy![1]
                        : (singleVars.length >= 2
                            ? singleVars[1]
                            : (singleVars.isNotEmpty ? singleVars[0] : null)),
                items: singleVars
                    .map(
                      (v) => DropdownMenuItem<String>(
                        value: v,
                        child: Text(v),
                      ),
                    )
                    .toList(),
                onChanged: (v) {
                  if (v == null) return;
                  final x = spec.scatterXy?.elementAtOrNull(0) ?? v;
                  update(spec.copyWith(scatterXy: [x, v]));
                },
              ),
            ],

            // Sort basis
            DropdownButtonFormField<String>(
              key: const Key('sort_basis_dropdown'),
              decoration: const InputDecoration(labelText: 'Sort basis'),
              initialValue: _kSortBases.any((s) => s.$1 == sortBasis)
                  ? sortBasis
                  : 'data_order',
              items: _kSortBases
                  .map(
                    (s) => DropdownMenuItem<String>(
                      value: s.$1,
                      child: Text(s.$2),
                    ),
                  )
                  .toList(),
              onChanged: (v) {
                if (v != null) {
                  final newSort = <String, dynamic>{
                    ...sortMap,
                    'basis': v,
                  };
                  update(spec.copyWith(sort: newSort));
                }
              },
            ),
            const SizedBox(height: 8),

            // Number format fields
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    key: const Key('pct_decimals_field'),
                    initialValue: pctDecimals.toString(),
                    decoration:
                        const InputDecoration(labelText: 'Pct decimals'),
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    onChanged: (v) {
                      final n = int.tryParse(v) ?? 0;
                      final newNf = <String, dynamic>{...nf, 'pct_decimals': n};
                      update(spec.copyWith(numberFormat: newNf));
                    },
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextFormField(
                    key: const Key('mean_decimals_field'),
                    initialValue: meanDecimals.toString(),
                    decoration:
                        const InputDecoration(labelText: 'Mean decimals'),
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    onChanged: (v) {
                      final n = int.tryParse(v) ?? 1;
                      final newNf = <String, dynamic>{...nf, 'mean_decimals': n};
                      update(spec.copyWith(numberFormat: newNf));
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Element toggles (REQ-C-14)
            Wrap(
              spacing: 0,
              children: [
                for (final key in ['title', 'legend', 'n', 'axis_names', 'data_labels'])
                  SizedBox(
                    width: 140,
                    child: CheckboxListTile(
                      key: Key('el_${key}_$index'),
                      title: Text(key),
                      value: (el[key] as bool?) ?? true,
                      dense: true,
                      controlAffinity: ListTileControlAffinity.leading,
                      onChanged: (v) {
                        final newEl = <String, dynamic>{
                          ...el,
                          key: v ?? true,
                          // filter_var always true (not shown in UI per brief)
                          'filter_var': el['filter_var'] ?? true,
                        };
                        update(spec.copyWith(elements: newEl));
                      },
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
