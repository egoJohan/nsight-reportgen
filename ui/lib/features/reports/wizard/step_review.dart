// Wizard Step 3 — Review: scrollable grid of live chart thumbnails.
// One thumbnail per chart so the user sees the whole report at a glance.
// REQ-U-06 / REQ-C-24a

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
// ReviewStep
// ---------------------------------------------------------------------------

/// Step 3 of the wizard: a scrollable grid of live chart thumbnails.
///
/// One thumbnail card per chart in the draft, each captioned with the
/// question text and chart type.  The user can see the whole report's charts
/// at a glance before assembling slides.
class ReviewStep extends ConsumerWidget {
  const ReviewStep({
    super.key,
    required this.materialId,
  });

  /// The active material ID — passed to [previewChart] for each thumbnail.
  final String? materialId;

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
              Icons.image_not_supported_outlined,
              size: 48,
              color: Theme.of(context)
                  .colorScheme
                  .onSurface
                  .withValues(alpha: 0.3),
            ),
            const SizedBox(height: 16),
            const Text('No charts to review.'),
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

    return GridView.builder(
      key: const Key('review_grid'),
      padding: const EdgeInsets.all(16),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 340,
        mainAxisExtent: 280,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
      ),
      itemCount: charts.length,
      itemBuilder: (context, index) => _ReviewThumbnailCard(
        key: ValueKey('review_card_$index'),
        index: index,
        spec: charts[index],
        materialId: materialId,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _ReviewThumbnailCard
// ---------------------------------------------------------------------------

class _ReviewThumbnailCard extends ConsumerStatefulWidget {
  const _ReviewThumbnailCard({
    super.key,
    required this.index,
    required this.spec,
    required this.materialId,
  });

  final int index;
  final ChartSpecDef spec;
  final String? materialId;

  @override
  ConsumerState<_ReviewThumbnailCard> createState() =>
      _ReviewThumbnailCardState();
}

class _ReviewThumbnailCardState
    extends ConsumerState<_ReviewThumbnailCard> {
  Timer? _timer;
  Uint8List? _bytes;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _fetch();
    });
  }

  @override
  void didUpdateWidget(_ReviewThumbnailCard old) {
    super.didUpdateWidget(old);
    if (old.spec != widget.spec || old.materialId != widget.materialId) {
      _fetch();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _fetch() {
    _timer?.cancel();
    if (widget.materialId == null) return;
    _timer = Timer(
      const Duration(milliseconds: 200),
      _doFetch,
    );
  }

  Future<void> _doFetch() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final bytes = await ref.read(nsightApiProvider).previewChart(
            widget.materialId!,
            widget.spec.toJson(),
          );
      if (mounted) setState(() { _bytes = bytes; _loading = false; });
    } on NsightApiException catch (e) {
      if (mounted) setState(() { _error = e.detail; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final questionsAsync = ref.watch(questionsProvider);
    final allQuestions = questionsAsync.asData?.value ?? const [];
    final question = allQuestions
        .where((q) => q.qid == widget.spec.questionRef)
        .firstOrNull;
    final questionText = question?.text ?? widget.spec.questionRef;
    final chartTypeLabel = _kChartTypeLabels[widget.spec.chartType] ??
        widget.spec.chartType;

    Widget thumbnailContent;
    if (widget.materialId == null) {
      thumbnailContent = const Center(child: Text('No material'));
    } else if (_loading && _bytes == null) {
      thumbnailContent = const Center(
          child: CircularProgressIndicator(strokeWidth: 2));
    } else if (_error != null && _bytes == null) {
      thumbnailContent = Center(
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            _error!,
            style: TextStyle(
              fontSize: 11,
              color: theme.colorScheme.error,
            ),
            textAlign: TextAlign.center,
            maxLines: 4,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      );
    } else if (_bytes != null) {
      thumbnailContent = Stack(
        children: [
          Positioned.fill(
            child: Image.memory(
              _bytes!,
              key: Key('review_thumbnail_${widget.index}'),
              fit: BoxFit.contain,
              errorBuilder: (ctx, err, st) => const Center(
                child: Icon(Icons.broken_image_outlined),
              ),
            ),
          ),
          if (_loading)
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
      thumbnailContent = Center(
        child: Icon(
          Icons.bar_chart,
          size: 40,
          color: theme.colorScheme.primary.withValues(alpha: 0.3),
        ),
      );
    }

    return Card(
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: ClipRRect(
              borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(10)),
              child: Container(
                color: theme.colorScheme.surfaceContainerHighest,
                child: thumbnailContent,
              ),
            ),
          ),
          Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  questionText,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: theme.colorScheme.onSurface,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  chartTypeLabel,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color:
                        theme.colorScheme.onSurface.withValues(alpha: 0.55),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Chart type display labels (subset; matches step_configure's _kChartTypes)
// ---------------------------------------------------------------------------

const _kChartTypeLabels = <String, String>{
  'line': 'Line',
  'pie': 'Pie',
  'vertical_bar': 'Vertical bar',
  'stacked_vertical_bar': 'Stacked vertical bar',
  'horizontal_bar': 'Horizontal bar',
  'stacked_horizontal_bar': 'Stacked horizontal bar',
  'radar': 'Radar',
  'doughnut': 'Doughnut',
  'scatter': 'Scatter',
  'funnel': 'Funnel',
  'combo': 'Combo',
};
