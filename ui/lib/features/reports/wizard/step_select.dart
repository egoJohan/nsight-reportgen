// Wizard Step 1 — Select questions.
// Searchable checklist of the material's questions with kind badges.
// "Add selected →" appends chart cards using each question's suggestedChartType.
// REQ-U-01 / REQ-U-11 / REQ-C-11

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../data/providers/material_provider.dart';
import '../../data/providers/questions_provider.dart';
import '../providers/builder_provider.dart';

// ---------------------------------------------------------------------------
// Kind badge colours
// ---------------------------------------------------------------------------

const _kKindColors = <String, Color>{
  'single': Color(0xFF1565C0),
  'multi': Color(0xFF2E7D32),
  'scale': Color(0xFF6A1B9A),
  'open': Color(0xFFE65100),
};

Color _kindColor(String kind) =>
    _kKindColors[kind] ?? const Color(0xFF546E7A);

// ---------------------------------------------------------------------------
// SelectStep
// ---------------------------------------------------------------------------

/// Step 1 of the wizard: browse and select questions to include in the report.
///
/// Questions are shown with a kind badge (single/multi/scale/open).
/// "Add selected →" appends chart cards to the draft using each question's
/// [QuestionItem.suggestedChartType] and advances to the Configure step via
/// [onQuestionsAdded]. (REQ-C-11 / REQ-U-11)
class SelectStep extends ConsumerStatefulWidget {
  const SelectStep({
    super.key,
    required this.onQuestionsAdded,
  });

  /// Called after questions are successfully added, so the wizard can advance
  /// to the Configure step.
  final VoidCallback onQuestionsAdded;

  @override
  ConsumerState<SelectStep> createState() => _SelectStepState();
}

class _SelectStepState extends ConsumerState<SelectStep> {
  final _searchController = TextEditingController();
  final _selected = <String>{}; // selected qids
  String _filter = '';

  @override
  void initState() {
    super.initState();
    _searchController.addListener(
      () => setState(
        () => _filter = _searchController.text.trim().toLowerCase(),
      ),
    );
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final materialId = ref.watch(activeMaterialProvider);
    if (materialId == null) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: Center(
          child: Text(
            'Upload or select a material in the Data tab first.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    final questionsAsync = ref.watch(questionsProvider);
    return questionsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error loading questions: $e')),
      data: (questions) => _buildContent(context, questions),
    );
  }

  Widget _buildContent(BuildContext context, List<QuestionItem> questions) {
    final filtered = _filter.isEmpty
        ? questions
        : questions
            .where(
              (q) =>
                  q.text.toLowerCase().contains(_filter) ||
                  q.qid.toLowerCase().contains(_filter) ||
                  q.kind.toLowerCase().contains(_filter),
            )
            .toList();

    final draft = ref.watch(builderProvider);
    final addedQids = draft?.charts.map((c) => c.questionRef).toSet() ?? {};

    final theme = Theme.of(context);
    final onSurface = theme.colorScheme.onSurface;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
          child: Text(
            'Select questions for your report',
            style: theme.textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
        const SizedBox(height: 4),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
          child: Text(
            'Check the questions you want to include. '
            'Each will be added as a chart card in the Configure step.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: onSurface.withValues(alpha: 0.6),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 8),
          child: TextField(
            key: const Key('select_search_field'),
            controller: _searchController,
            decoration: const InputDecoration(
              hintText: 'Search questions…',
              prefixIcon: Icon(Icons.search),
              isDense: true,
              border: OutlineInputBorder(),
            ),
          ),
        ),
        Expanded(
          child: filtered.isEmpty
              ? Center(
                  child: Text(
                    'No questions match the search.',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                  itemCount: filtered.length,
                  itemBuilder: (context, i) {
                    final q = filtered[i];
                    final isAdded = addedQids.contains(q.qid);
                    final isSelected = _selected.contains(q.qid);

                    return Card(
                      key: ValueKey('q_card_${q.qid}'),
                      margin: const EdgeInsets.symmetric(
                        vertical: 3,
                        horizontal: 0,
                      ),
                      elevation: isSelected ? 2 : 0,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                        side: BorderSide(
                          color: isSelected
                              ? theme.colorScheme.primary
                              : theme.dividerColor,
                          width: isSelected ? 1.5 : 1,
                        ),
                      ),
                      child: CheckboxListTile(
                        key: ValueKey('q_check_${q.qid}'),
                        value: isSelected,
                        enabled: !isAdded,
                        title: Text(
                          q.text,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: isAdded
                                ? onSurface.withValues(alpha: 0.5)
                                : null,
                          ),
                        ),
                        subtitle: Row(
                          children: [
                            _KindBadge(kind: q.kind),
                            const SizedBox(width: 8),
                            Text(
                              q.qid,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: onSurface.withValues(alpha: 0.5),
                              ),
                            ),
                            if (isAdded) ...[
                              const SizedBox(width: 8),
                              Icon(
                                Icons.check_circle,
                                size: 14,
                                color: theme.colorScheme.primary,
                              ),
                              const SizedBox(width: 2),
                              Text(
                                'Added',
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.primary,
                                ),
                              ),
                            ],
                          ],
                        ),
                        controlAffinity: ListTileControlAffinity.leading,
                        dense: true,
                        onChanged: isAdded
                            ? null
                            : (v) => setState(() {
                                  if (v == true) {
                                    _selected.add(q.qid);
                                  } else {
                                    _selected.remove(q.qid);
                                  }
                                }),
                      ),
                    );
                  },
                ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
          child: Row(
            children: [
              if (_selected.isNotEmpty)
                Text(
                  '${_selected.length} question${_selected.length == 1 ? '' : 's'} selected',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.primary,
                  ),
                ),
              const Spacer(),
              FilledButton.icon(
                key: const Key('add_selected_button'),
                onPressed: _selected.isEmpty ? null : _addSelected,
                icon: const Icon(Icons.add_chart),
                label: const Text('Add selected →'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  void _addSelected() {
    final allQuestions =
        ref.read(questionsProvider).asData?.value ?? const [];
    final toAdd = allQuestions
        .where((q) => _selected.contains(q.qid))
        .toList();

    if (toAdd.isEmpty) return;

    ref.read(builderProvider.notifier).addQuestionsFromItems(toAdd);
    setState(() => _selected.clear());
    widget.onQuestionsAdded();
  }
}

// ---------------------------------------------------------------------------
// Kind badge
// ---------------------------------------------------------------------------

class _KindBadge extends StatelessWidget {
  const _KindBadge({required this.kind});

  final String kind;

  @override
  Widget build(BuildContext context) {
    final color = _kindColor(kind);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        kind,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
