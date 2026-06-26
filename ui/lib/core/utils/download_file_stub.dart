// Non-web stub: file downloads are web-only.
// On the VM test platform this is a no-op.
import 'dart:typed_data';

/// Triggers a browser download of [bytes] as [filename].
/// On non-web platforms this is a no-op.
void downloadFile(Uint8List bytes, String filename) {
  // No-op on non-web platforms.
}
