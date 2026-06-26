// Provider managing the list of questions for the active material.
// REQ-C-04 / REQ-C-05 / REQ-C-06.

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../../core/providers/api_provider.dart';
import 'material_provider.dart';

/// Async notifier that loads questions for the active material.
///
/// Returns `[]` immediately when no material is active (activeMaterialProvider
/// is null). Rebuilds automatically when the active material changes.
class QuestionsNotifier extends AsyncNotifier<List<QuestionItem>> {
  @override
  Future<List<QuestionItem>> build() async {
    // REQ-C-04 — watch the active material; rebuild when it changes.
    final materialId = ref.watch(activeMaterialProvider);
    if (materialId == null) return [];
    final api = ref.read(nsightApiProvider);
    return api.listQuestions(materialId);
  }

  /// Sets the grouping kind for [variables] then refreshes the question list.
  /// (REQ-C-06)
  Future<void> setGrouping(List<String> variables, String kind) async {
    final materialId = ref.read(activeMaterialProvider);
    if (materialId == null) return;
    final api = ref.read(nsightApiProvider);
    await api.setGrouping(materialId, variables, kind);
    // Refresh to pick up the updated kind from the server.
    ref.invalidateSelf();
  }
}

final questionsProvider =
    AsyncNotifierProvider<QuestionsNotifier, List<QuestionItem>>(
  QuestionsNotifier.new,
);
