// Wizard Step 4 — Slides: reorderable list with per-slide title + description.
// REQ-U-06: the "modify slides" step.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../../core/providers/api_provider.dart';
import '../../data/providers/questions_provider.dart';
import '../providers/builder_provider.dart';

// ---------------------------------------------------------------------------
// SlidesStep
// ---------------------------------------------------------------------------

/// Step 4 of the wizard: a reorderable list of slide cards.
///
/// Each card shows a small thumbnail, an editable **slide title** (defaults to
/// the question text), and an optional **description** text field. Drag handles
/// allow reordering (updates chart order / template_slot). (REQ-U-06)
class SlidesStep extends ConsumerWidget {
  const SlidesStep({
    super.key,
    required this.materialId,
  });

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
              Icons.slideshow_outlined,
              size: 48,
              color: Theme.of(context)
                  .colorScheme
                  .onSurface
                  .withValues(alpha: 0.3),
            ),
            const SizedBox(height: 16),
            const Text('No slides yet.'),
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

    return ReorderableListView.builder(
      key: const Key('slides_list'),
      padding: const EdgeInsets.all(16),
      onReorder: (oldIndex, newIndex) {
        ref.read(builderProvider.notifier).reorder(oldIndex, newIndex);
      },
      itemCount: charts.length,
      itemBuilder: (context, index) => _SlideCard(
        key: ValueKey('slide_card_$index'),
        index: index,
        spec: charts[index],
        materialId: materialId,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// _SlideCard
// ---------------------------------------------------------------------------

class _SlideCard extends ConsumerStatefulWidget {
  const _SlideCard({
    super.key,
    required this.index,
    required this.spec,
    required this.materialId,
  });

  final int index;
  final ChartSpecDef spec;
  final String? materialId;

  @override
  ConsumerState<_SlideCard> createState() => _SlideCardState();
}

class _SlideCardState extends ConsumerState<_SlideCard> {
  late TextEditingController _titleController;
  late TextEditingController _descController;

  Timer? _thumbTimer;
  Uint8List? _thumbBytes;
  bool _thumbLoading = false;

  @override
  void initState() {
    super.initState();
    _titleController =
        TextEditingController(text: widget.spec.slideTitle ?? '');
    _descController =
        TextEditingController(text: widget.spec.slideDescription ?? '');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _fetchThumb();
    });
  }

  @override
  void didUpdateWidget(_SlideCard old) {
    super.didUpdateWidget(old);
    // If the spec changed externally (e.g. reorder changed questionRef),
    // sync the text controllers.
    if (old.spec.questionRef != widget.spec.questionRef) {
      _titleController.text = widget.spec.slideTitle ?? '';
      _descController.text = widget.spec.slideDescription ?? '';
      _fetchThumb();
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _descController.dispose();
    _thumbTimer?.cancel();
    super.dispose();
  }

  void _fetchThumb() {
    _thumbTimer?.cancel();
    if (widget.materialId == null) return;
    _thumbTimer = Timer(const Duration(milliseconds: 300), _doFetchThumb);
  }

  Future<void> _doFetchThumb() async {
    if (!mounted) return;
    setState(() => _thumbLoading = true);
    try {
      final bytes = await ref.read(nsightApiProvider).previewChart(
            widget.materialId!,
            widget.spec.toJson(),
          );
      if (mounted) setState(() { _thumbBytes = bytes; _thumbLoading = false; });
    } catch (_) {
      if (mounted) setState(() => _thumbLoading = false);
    }
  }

  void _commitTitle(String value) {
    final updated = widget.spec.copyWith(
      slideTitle: value.isEmpty ? null : value,
    );
    ref.read(builderProvider.notifier).updateChart(widget.index, updated);
  }

  void _commitDesc(String value) {
    final updated = widget.spec.copyWith(
      slideDescription: value.isEmpty ? null : value,
    );
    ref.read(builderProvider.notifier).updateChart(widget.index, updated);
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

    // Default the title placeholder to the question text.
    final titlePlaceholder = questionText;

    Widget thumb;
    if (_thumbBytes != null) {
      thumb = Image.memory(
        _thumbBytes!,
        key: Key('slide_thumbnail_${widget.index}'),
        fit: BoxFit.cover,
        errorBuilder: (ctx, err, st) =>
            const Icon(Icons.broken_image_outlined, size: 24),
      );
    } else if (_thumbLoading) {
      thumb = const Center(
        child: SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    } else {
      thumb = Icon(
        Icons.bar_chart,
        size: 30,
        color: theme.colorScheme.primary.withValues(alpha: 0.3),
      );
    }

    return Card(
      key: widget.key,
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // Drag handle
            const Icon(Icons.drag_handle, size: 20, color: Colors.grey),
            const SizedBox(width: 8),

            // Slide number chip
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: theme.colorScheme.primary.withValues(alpha: 0.12),
              ),
              child: Center(
                child: Text(
                  '${widget.index + 1}',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: theme.colorScheme.primary,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),

            // Thumbnail
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Container(
                width: 72,
                height: 54,
                color: theme.colorScheme.surfaceContainerHighest,
                child: thumb,
              ),
            ),
            const SizedBox(width: 12),

            // Title + description fields
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    key: Key('slide_title_field_${widget.index}'),
                    controller: _titleController,
                    decoration: InputDecoration(
                      labelText: 'Slide title',
                      hintText: titlePlaceholder,
                      isDense: true,
                      border: const OutlineInputBorder(),
                    ),
                    onChanged: _commitTitle,
                    onSubmitted: _commitTitle,
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    key: Key('slide_desc_field_${widget.index}'),
                    controller: _descController,
                    decoration: const InputDecoration(
                      labelText: 'Description (optional)',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    onChanged: _commitDesc,
                    onSubmitted: _commitDesc,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
