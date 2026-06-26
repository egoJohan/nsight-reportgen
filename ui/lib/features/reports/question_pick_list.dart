// Left panel of the report builder: searchable checklist of material questions.
// REQ-C-11 / REQ-U-11.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../data/providers/material_provider.dart';
import '../data/providers/questions_provider.dart';
import 'providers/builder_provider.dart';

/// Searchable, checkable list of the active material's questions.
///
/// The user checks one or more questions and taps "Add checked →" to append
/// default chart cards in the right panel. (REQ-C-11 / REQ-U-11)
class QuestionPickList extends ConsumerStatefulWidget {
  const QuestionPickList({super.key});

  @override
  ConsumerState<QuestionPickList> createState() => _QuestionPickListState();
}

class _QuestionPickListState extends ConsumerState<QuestionPickList> {
  final _searchController = TextEditingController();
  final _checked = <String>{};
  String _filter = '';

  @override
  void initState() {
    super.initState();
    _searchController.addListener(
      () => setState(() => _filter = _searchController.text.trim().toLowerCase()),
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
        padding: EdgeInsets.all(16),
        child: Text('Upload/select a material in the Data tab first.'),
      );
    }

    final questionsAsync = ref.watch(questionsProvider);
    return questionsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error loading questions: $e')),
      data: _buildList,
    );
  }

  Widget _buildList(List<QuestionItem> questions) {
    final filtered = _filter.isEmpty
        ? questions
        : questions
            .where(
              (q) =>
                  q.text.toLowerCase().contains(_filter) ||
                  q.qid.toLowerCase().contains(_filter),
            )
            .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Search field
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 8, 8, 4),
          child: TextField(
            controller: _searchController,
            decoration: const InputDecoration(
              hintText: 'Search questions…',
              prefixIcon: Icon(Icons.search),
              isDense: true,
              border: OutlineInputBorder(),
            ),
          ),
        ),
        // Checklist
        Expanded(
          child: filtered.isEmpty
              ? const Center(child: Text('No questions match the search.'))
              : ListView.builder(
                  itemCount: filtered.length,
                  itemBuilder: (context, i) {
                    final q = filtered[i];
                    return CheckboxListTile(
                      key: ValueKey(q.qid),
                      value: _checked.contains(q.qid),
                      title: Text(q.text),
                      subtitle: Text(
                        q.qid,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      dense: true,
                      onChanged: (v) => setState(() {
                        if (v == true) {
                          _checked.add(q.qid);
                        } else {
                          _checked.remove(q.qid);
                        }
                      }),
                    );
                  },
                ),
        ),
        // Add button
        Padding(
          padding: const EdgeInsets.all(8),
          child: ElevatedButton.icon(
            key: const Key('add_checked_button'),
            onPressed: _checked.isEmpty ? null : _addChecked,
            icon: const Icon(Icons.arrow_forward),
            label: const Text('Add checked →'),
          ),
        ),
      ],
    );
  }

  void _addChecked() {
    final qids = List<String>.of(_checked);
    ref.read(builderProvider.notifier).addQuestions(qids);
    setState(() => _checked.clear());
  }
}
