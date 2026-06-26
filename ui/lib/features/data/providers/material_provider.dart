// Provider holding the active material ID. REQ-U-05 / REQ-C-01.

import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers/api_provider.dart';

/// Holds the materialId of the currently-active material (null until uploaded).
///
/// Exposes [upload] to POST a .sav file to the backend and store the returned
/// materialId. Throws [NsightApiException] on error — the caller catches it.
class ActiveMaterialNotifier extends Notifier<String?> {
  @override
  String? build() => null;

  /// Uploads [bytes] as [filename] for [caseId], then stores the returned
  /// materialId. (REQ-C-01)
  Future<void> upload(
    String caseId,
    Uint8List bytes,
    String filename,
  ) async {
    final api = ref.read(nsightApiProvider);
    final result = await api.uploadMaterial(caseId, bytes, filename);
    state = result.materialId;
  }
}

final activeMaterialProvider =
    NotifierProvider<ActiveMaterialNotifier, String?>(
  ActiveMaterialNotifier.new,
);
