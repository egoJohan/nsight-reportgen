// Question browser: lists questions with auto-detected kind badges.
// REQ-U-05 / REQ-C-05 / REQ-C-26.
// D-06 / W4: replaced non-functional single/multi toggle with read-only badge
// + missing-value surfacing.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import 'providers/questions_provider.dart';

/// Available client-side sort modes for the question list.
enum QuestionSortMode {
  /// Sort by question text A–Z.
  textAZ,

  /// Sort by grouping kind (multi before single, alphabetically).
  byKind,
}

/// Lists all questions for the active material.
///
/// Each row shows the question [text] (with [qid] as a small subtitle),
/// a read-only auto-detected kind badge ("Single" / "Multi · N opts"),
/// and — when present — the question's missing-value mappings as a
/// "Special values → Not answered: …" line (W4.3).
///
/// The old single/multi [SegmentedButton] toggle has been removed: the
/// auto-grouping (A0) already assigns kind correctly; the toggle had no
/// persistent effect on the backend.
/// // TODO: manual regroup — let the user drag variables between questions.
///
/// (REQ-U-05, REQ-C-05, REQ-C-26, D-06)
class QuestionBrowser extends ConsumerWidget {
  const QuestionBrowser({super.key, required this.sortMode});

  final QuestionSortMode sortMode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // REQ-C-05 — watch the questions async provider.
    final questionsAsync = ref.watch(questionsProvider);

    return questionsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error loading questions: $e')),
      data: (questions) {
        if (questions.isEmpty) {
          return const Center(child: Text('No questions found.'));
        }

        // Client-side sort (REQ-C-26).
        final sorted = [...questions];
        switch (sortMode) {
          case QuestionSortMode.textAZ:
            sorted.sort((a, b) => a.text.compareTo(b.text));
          case QuestionSortMode.byKind:
            sorted.sort((a, b) => a.kind.compareTo(b.kind));
        }

        return ListView.builder(
          itemCount: sorted.length,
          itemBuilder: (context, index) {
            final q = sorted[index];
            final hasMissing = q.missingValues.isNotEmpty;

            return ListTile(
              title: Text(q.text),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    q.qid,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (hasMissing)
                    _MissingValuesRow(missingValues: q.missingValues),
                ],
              ),
              isThreeLine: hasMissing,
              // D-06: read-only auto-detected kind badge.
              trailing: _KindBadge(
                kind: q.kind,
                variableCount: q.variables.length,
                variables: q.variables,
              ),
            );
          },
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// Kind badge
// ---------------------------------------------------------------------------

/// Read-only badge showing a question's auto-detected grouping kind.
///
/// "Single" (one answer column) or "Multi · N opts" (tick-box set, N vars).
/// For Multi questions, hovering over the badge shows the variable identifiers
/// in a [Tooltip]. (D-06, W4.2)
class _KindBadge extends StatelessWidget {
  const _KindBadge({
    required this.kind,
    required this.variableCount,
    required this.variables,
  });

  final String kind;
  final int variableCount;
  final List<String> variables;

  @override
  Widget build(BuildContext context) {
    final isMulti = kind == 'multi';
    // U+00B7 = middle dot (·)
    final label = isMulti ? 'Multi · $variableCount opts' : 'Single';
    final scheme = Theme.of(context).colorScheme;

    final badge = Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: isMulti ? scheme.tertiaryContainer : scheme.secondaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: isMulti
              ? scheme.onTertiaryContainer
              : scheme.onSecondaryContainer,
        ),
      ),
    );

    if (isMulti && variables.isNotEmpty) {
      return Tooltip(
        message: 'Variables: ${variables.join(', ')}',
        child: badge,
      );
    }
    return badge;
  }
}

// ---------------------------------------------------------------------------
// Missing-value display
// ---------------------------------------------------------------------------

/// Inline row surfacing missing-value mappings for a question.
///
/// Renders: "Special values → Not answered: 99 = En tiedä, …"
/// (W4.3, D-06)
class _MissingValuesRow extends StatelessWidget {
  const _MissingValuesRow({required this.missingValues});

  final List<MissingValue> missingValues;

  @override
  Widget build(BuildContext context) {
    // U+2192 = →
    final parts =
        missingValues.map((m) => '${m.code} = ${m.label}').join(', ');
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Text(
        'Special values → Not answered: $parts',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
              fontStyle: FontStyle.italic,
            ),
      ),
    );
  }
}
