// Wizard Step 2 — Configure charts with live per-chart preview thumbnails.
// Each chart card shows all controls + a live PNG thumbnail from previewChart.
// REQ-U-01 / REQ-U-11 / REQ-C-10..15 / REQ-C-26

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../../core/providers/api_provider.dart';
import '../../../core/services/nsight_api.dart';
import '../../data/providers/questions_provider.dart';
import '../providers/builder_provider.dart';

// ---------------------------------------------------------------------------
// Chart-type / statistic / sort tables (reused from chart_spec_editor)
// REQ-C-13
// ---------------------------------------------------------------------------

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
// ConfigureStep
// ---------------------------------------------------------------------------

/// Step 2 of the wizard: per-chart controls + live preview thumbnail.
///
/// Shows a scrollable list of [WizardChartCard] items. When no charts have
/// been added yet (draft is empty), shows a prompt to go back to Select.
class ConfigureStep extends ConsumerWidget {
  const ConfigureStep({
    super.key,
    required this.materialId,
    required this.caseId,
  });

  /// The active material ID — passed to [previewChart]. Null means no material
  /// is active and thumbnails are skipped.
  final String? materialId;

  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(builderProvider);
    final charts = draft?.charts ?? const [];

    if (charts.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.bar_chart,
              size: 48,
              color: Theme.of(context)
                  .colorScheme
                  .onSurface
                  .withValues(alpha: 0.3),
            ),
            const SizedBox(height: 16),
            const Text('No charts added yet.'),
            const SizedBox(height: 8),
            Text(
              'Go back to Select to choose questions.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withValues(alpha: 0.5),
                  ),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: charts.length,
      itemBuilder: (context, index) => WizardChartCard(
        key: ValueKey('wizard_card_$index'),
        index: index,
        spec: charts[index],
        materialId: materialId,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// WizardChartCard
// ---------------------------------------------------------------------------

/// A card for configuring one [ChartSpecDef] in the wizard.
///
/// Controls exposed (REQ-C-13/14/15/26):
/// - Chart type (11 types; image-only — no native/image toggle)
/// - Statistic (pct/count/mean/median/sum)
/// - Number format: Automatic / Manual toggle; manual reveals decimal fields
/// - "Show Not answered" toggle (single-kind questions only, default off)
/// - Classifying variable dropdown
/// - Sort basis dropdown
///
/// A **live thumbnail** (REQ-C-26) is shown on the right:
/// - Calls [NsightApi.previewChart] with the current spec, debounced ~400 ms
/// - Shows a spinner while loading, the PNG Image.memory when ready
/// - Shows error detail on [NsightApiException]
class WizardChartCard extends ConsumerStatefulWidget {
  const WizardChartCard({
    super.key,
    required this.index,
    required this.spec,
    required this.materialId,
  });

  final int index;
  final ChartSpecDef spec;
  final String? materialId;

  @override
  ConsumerState<WizardChartCard> createState() => _WizardChartCardState();
}

class _WizardChartCardState extends ConsumerState<WizardChartCard> {
  bool _isManualFormat = false;

  Timer? _debounceTimer;
  Uint8List? _previewBytes;
  bool _previewLoading = false;
  String? _previewError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _schedulePreview();
    });
  }

  @override
  void didUpdateWidget(WizardChartCard old) {
    super.didUpdateWidget(old);
    if (old.spec != widget.spec || old.materialId != widget.materialId) {
      _schedulePreview();
    }
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    super.dispose();
  }

  void _schedulePreview() {
    _debounceTimer?.cancel();
    if (widget.materialId == null) return;
    _debounceTimer = Timer(
      const Duration(milliseconds: 400),
      _fetchPreview,
    );
  }

  Future<void> _fetchPreview() async {
    if (!mounted) return;
    setState(() {
      _previewLoading = true;
      _previewError = null;
    });
    try {
      final bytes = await ref.read(nsightApiProvider).previewChart(
            widget.materialId!,
            widget.spec.toJson(),
          );
      if (mounted) {
        setState(() {
          _previewBytes = bytes;
          _previewLoading = false;
        });
      }
    } on NsightApiException catch (e) {
      if (mounted) {
        setState(() {
          _previewError = e.detail;
          _previewLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _previewError = e.toString();
          _previewLoading = false;
        });
      }
    }
  }

  void _update(ChartSpecDef updated) {
    ref.read(builderProvider.notifier).updateChart(widget.index, updated);
    _schedulePreview();
  }

  @override
  Widget build(BuildContext context) {
    final spec = widget.spec;
    final theme = Theme.of(context);

    final questionsAsync = ref.watch(questionsProvider);
    final allQuestions = questionsAsync.asData?.value ?? const [];
    final question = allQuestions
        .where((q) => q.qid == spec.questionRef)
        .firstOrNull;

    final singleVars = allQuestions
        .where((q) => q.kind == 'single')
        .expand((q) => q.variables)
        .toList();

    final nf = spec.numberFormat ?? const <String, dynamic>{};
    final sortMap = spec.sort ?? const <String, dynamic>{};
    final sortBasis = (sortMap['basis'] as String?) ?? 'data_order';
    final pctDecimals = (nf['pct_decimals'] as int?) ?? 0;
    final meanDecimals = (nf['mean_decimals'] as int?) ?? 1;
    final el = spec.elements ?? const <String, dynamic>{};
    final showNotAnswered = (el['not_answered'] as bool?) ?? false;
    final isSingleKind = question?.kind == 'single';

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        question?.text ?? spec.questionRef,
                        style: theme.textTheme.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w600),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        spec.questionRef,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface
                              .withValues(alpha: 0.5),
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  key: Key('remove_chart_${widget.index}'),
                  icon: const Icon(Icons.close),
                  tooltip: 'Remove chart',
                  onPressed: () => ref
                      .read(builderProvider.notifier)
                      .removeChart(widget.index),
                ),
              ],
            ),
            const Divider(height: 16),

            // Controls + thumbnail
            LayoutBuilder(
              builder: (context, constraints) {
                final isWide = constraints.maxWidth >= 600;
                final controls = _buildControls(
                  context,
                  spec,
                  singleVars,
                  sortBasis,
                  pctDecimals,
                  meanDecimals,
                  nf,
                  sortMap,
                  el,
                  showNotAnswered,
                  isSingleKind,
                );
                final thumbnail = _buildThumbnail(context);

                if (isWide) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: controls),
                      const SizedBox(width: 16),
                      SizedBox(width: 200, child: thumbnail),
                    ],
                  );
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [controls, const SizedBox(height: 12), thumbnail],
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  // ── Controls ──────────────────────────────────────────────────────────────

  Widget _buildControls(
    BuildContext context,
    ChartSpecDef spec,
    List<String> singleVars,
    String sortBasis,
    int pctDecimals,
    int meanDecimals,
    Map<String, dynamic> nf,
    Map<String, dynamic> sortMap,
    Map<String, dynamic> el,
    bool showNotAnswered,
    bool isSingleKind,
  ) {
    final currentChartType =
        _kChartTypes.any((t) => t.$1 == spec.chartType)
            ? spec.chartType
            : _kChartTypes.first.$1;

    final currentStatistic = _kStatistics.any(
      (s) => s.$1 == (spec.statistic ?? 'pct'),
    )
        ? (spec.statistic ?? 'pct')
        : 'pct';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Chart type (REQ-C-13)
        DropdownButtonFormField<String>(
          key: Key('chart_type_dropdown_${widget.index}'),
          decoration: const InputDecoration(
            labelText: 'Chart type',
            isDense: true,
          ),
          initialValue: currentChartType,
          items: _kChartTypes
              .map(
                (t) => DropdownMenuItem<String>(
                  value: t.$1,
                  child: Text(t.$2),
                ),
              )
              .toList(),
          onChanged: (v) {
            if (v == null) return;
            var updated = spec.copyWith(chartType: v);
            if (v == 'scatter' && spec.scatterXy == null) {
              final x = singleVars.isNotEmpty ? singleVars[0] : null;
              final y = singleVars.length >= 2 ? singleVars[1] : x;
              if (x != null && y != null) {
                updated = updated.copyWith(scatterXy: [x, y]);
              }
            } else if (v != 'scatter') {
              updated = updated.copyWith(scatterXy: null);
            }
            _update(updated);
          },
        ),
        const SizedBox(height: 8),

        // Statistic
        DropdownButtonFormField<String>(
          key: Key('statistic_dropdown_${widget.index}'),
          decoration: const InputDecoration(
            labelText: 'Statistic',
            isDense: true,
          ),
          initialValue: currentStatistic,
          items: _kStatistics
              .map(
                (s) => DropdownMenuItem<String>(
                  value: s.$1,
                  child: Text(s.$2),
                ),
              )
              .toList(),
          onChanged: (v) {
            if (v != null) _update(spec.copyWith(statistic: v));
          },
        ),
        const SizedBox(height: 8),

        // Number format mode toggle — Automatic / Manual (REQ-C-26)
        Row(
          children: [
            Text(
              'Number format',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withValues(alpha: 0.7),
                  ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: SegmentedButton<bool>(
                key: Key('number_format_mode_${widget.index}'),
                segments: const [
                  ButtonSegment(value: false, label: Text('Automatic')),
                  ButtonSegment(value: true, label: Text('Manual')),
                ],
                selected: {_isManualFormat},
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                onSelectionChanged: (sel) {
                  setState(() => _isManualFormat = sel.first);
                  if (!sel.first) {
                    _update(
                      spec.copyWith(
                        numberFormat: const <String, dynamic>{
                          'pct_decimals': 0,
                          'mean_decimals': 1,
                          'count_round_up': false,
                          'show_pct_sign': true,
                        },
                      ),
                    );
                  }
                },
              ),
            ),
          ],
        ),
        if (_isManualFormat) ...[
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextFormField(
                  key: Key('pct_decimals_${widget.index}'),
                  initialValue: pctDecimals.toString(),
                  decoration: const InputDecoration(
                    labelText: 'Pct decimals',
                    isDense: true,
                  ),
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  onChanged: (v) {
                    final n = int.tryParse(v) ?? 0;
                    _update(
                      spec.copyWith(
                        numberFormat: <String, dynamic>{
                          ...nf,
                          'pct_decimals': n,
                        },
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextFormField(
                  key: Key('mean_decimals_${widget.index}'),
                  initialValue: meanDecimals.toString(),
                  decoration: const InputDecoration(
                    labelText: 'Mean decimals',
                    isDense: true,
                  ),
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  onChanged: (v) {
                    final n = int.tryParse(v) ?? 1;
                    _update(
                      spec.copyWith(
                        numberFormat: <String, dynamic>{
                          ...nf,
                          'mean_decimals': n,
                        },
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ],
        const SizedBox(height: 8),

        // Show Not answered (single-kind only, default off)
        if (isSingleKind)
          SwitchListTile(
            key: Key('show_not_answered_${widget.index}'),
            title: const Text('Show "Not answered"'),
            value: showNotAnswered,
            dense: true,
            contentPadding: EdgeInsets.zero,
            onChanged: (v) {
              _update(
                spec.copyWith(
                  elements: <String, dynamic>{...el, 'not_answered': v},
                ),
              );
            },
          ),

        // Classifying variable (REQ-C-14)
        DropdownButtonFormField<String?>(
          key: Key('classifying_var_dropdown_${widget.index}'),
          decoration: const InputDecoration(
            labelText: 'Classifying variable',
            isDense: true,
          ),
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
          onChanged: (v) => _update(spec.copyWith(classifyingVar: v)),
        ),
        const SizedBox(height: 8),

        // Sort basis
        DropdownButtonFormField<String>(
          key: Key('sort_basis_dropdown_${widget.index}'),
          decoration: const InputDecoration(
            labelText: 'Sort basis',
            isDense: true,
          ),
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
              _update(
                spec.copyWith(
                  sort: <String, dynamic>{...sortMap, 'basis': v},
                ),
              );
            }
          },
        ),
      ],
    );
  }

  // ── Live thumbnail ────────────────────────────────────────────────────────

  Widget _buildThumbnail(BuildContext context) {
    final theme = Theme.of(context);
    final onSurface = theme.colorScheme.onSurface;

    Widget inner;

    if (widget.materialId == null) {
      inner = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.bar_chart,
            size: 32,
            color: onSurface.withValues(alpha: 0.2),
          ),
          const SizedBox(height: 8),
          Text(
            'No material',
            style: theme.textTheme.bodySmall?.copyWith(
              color: onSurface.withValues(alpha: 0.4),
            ),
            textAlign: TextAlign.center,
          ),
        ],
      );
    } else if (_previewLoading && _previewBytes == null) {
      inner = const Center(
        child: CircularProgressIndicator(strokeWidth: 2),
      );
    } else if (_previewError != null && _previewBytes == null) {
      inner = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.error_outline, size: 24, color: theme.colorScheme.error),
          const SizedBox(height: 8),
          Text(
            _previewError!,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.error),
            textAlign: TextAlign.center,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      );
    } else if (_previewBytes != null) {
      inner = Stack(
        children: [
          Positioned.fill(
            child: Image.memory(
              _previewBytes!,
              key: Key('preview_thumbnail_${widget.index}'),
              fit: BoxFit.contain,
              errorBuilder: (ctx, err, stack) => Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.bar_chart,
                    size: 40,
                    color: theme.colorScheme.primary.withValues(alpha: 0.4),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Chart preview',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: onSurface.withValues(alpha: 0.5),
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
          if (_previewLoading)
            Positioned.fill(
              child: Container(
                color: Colors.white.withValues(alpha: 0.5),
                child: const Center(
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
        ],
      );
    } else {
      inner = Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.bar_chart,
            size: 40,
            color: theme.colorScheme.primary.withValues(alpha: 0.3),
          ),
          const SizedBox(height: 8),
          Text(
            'Chart preview',
            style: theme.textTheme.bodySmall?.copyWith(
              color: onSurface.withValues(alpha: 0.4),
            ),
            textAlign: TextAlign.center,
          ),
        ],
      );
    }

    return Container(
      key: Key('thumbnail_container_${widget.index}'),
      height: 160,
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.dividerColor),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: inner,
      ),
    );
  }
}
