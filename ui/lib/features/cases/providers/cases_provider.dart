// Riverpod AsyncNotifier provider for the cases list.
// REQ-U-04 / REQ-C-03 / REQ-C-07

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';
import '../../../core/providers/api_provider.dart';

/// AsyncNotifier that holds and manages the list of cases.
class CasesNotifier extends AsyncNotifier<List<CaseRecord>> {
  @override
  Future<List<CaseRecord>> build() async {
    return ref.read(nsightApiProvider).listCases();
  }

  /// Creates a new case with [name] via the API and refreshes the list.
  Future<void> create(String name) async {
    final api = ref.read(nsightApiProvider);
    await api.createCase(name);
    ref.invalidateSelf();
  }
}

final casesProvider =
    AsyncNotifierProvider<CasesNotifier, List<CaseRecord>>(CasesNotifier.new);
