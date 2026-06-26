// Question browser: lists questions with single/multi toggle.
// REQ-U-05 / REQ-C-05 / REQ-C-06 / REQ-C-26.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
/// Each row shows the question [text] (with [qid] as a small subtitle) and a
/// [SegmentedButton] bound to the question's current kind ('single'/'multi').
/// Tapping a segment calls [QuestionsNotifier.setGrouping] via the API.
/// (REQ-U-05, REQ-C-05, REQ-C-06, REQ-C-26)
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
            return ListTile(
              title: Text(q.text),
              subtitle: Text(
                q.qid,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              // REQ-C-06 — single/multi toggle per row.
              trailing: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'single', label: Text('single')),
                  ButtonSegment(value: 'multi', label: Text('multi')),
                ],
                selected: {q.kind},
                multiSelectionEnabled: false,
                onSelectionChanged: (Set<String> newSelection) {
                  // REQ-C-06 / REQ-C-26 — toggle grouping kind via API.
                  final newKind = newSelection.first;
                  if (newKind != q.kind) {
                    ref
                        .read(questionsProvider.notifier)
                        .setGrouping(q.variables, newKind);
                  }
                },
              ),
            );
          },
        );
      },
    );
  }
}
