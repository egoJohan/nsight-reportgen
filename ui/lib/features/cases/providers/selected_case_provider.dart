// Provider holding the currently-selected case. REQ-U-04.

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/models/models.dart';

/// Holds the case the user has selected in the list pane.
/// Null when nothing is selected (detail pane shows empty state).
class SelectedCaseNotifier extends Notifier<CaseRecord?> {
  @override
  CaseRecord? build() => null;

  /// Set (or clear) the active case. Called from [CasesList] on row tap.
  void select(CaseRecord? record) => state = record;
}

final selectedCaseProvider =
    NotifierProvider<SelectedCaseNotifier, CaseRecord?>(
  SelectedCaseNotifier.new,
);
