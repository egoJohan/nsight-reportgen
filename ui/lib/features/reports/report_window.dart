// DEFER REQ-U-07/08/09 — full windowing (move/resize/stack) is out of scope
// this phase; this scaffolds the close + resize affordances only.

import 'package:flutter/material.dart';

/// A simple container that wraps a child with window-like controls.
///
/// Provides:
/// - A title bar with a close icon that calls [onClose]
/// - A resize handle affordance at the bottom-right corner
///
/// This is a scaffold for future windowing functionality (REQ-U-07/08/09).
/// Full move/resize/stack behavior is deferred to a later phase.
class ReportWindow extends StatefulWidget {
  const ReportWindow({
    super.key,
    required this.child,
    required this.onClose,
    this.onResize,
  });

  /// The widget to wrap inside the window.
  final Widget child;

  /// Callback when the close icon is pressed.
  final VoidCallback onClose;

  /// Optional callback when the resize handle reports a size delta.
  ///
  /// Currently wired for gesture detection but does not live-resize.
  final ValueChanged<Size>? onResize;

  @override
  State<ReportWindow> createState() => _ReportWindowState();
}

class _ReportWindowState extends State<ReportWindow> {
  /// Tracks the initial position of the resize gesture.
  Offset? _resizeStart;

  /// Tracks the initial size during resize.
  Size? _initialSize;

  void _onResizePanDown(DragDownDetails details) {
    _resizeStart = details.globalPosition;
    _initialSize = MediaQuery.of(context).size;
  }

  void _onResizePanUpdate(DragUpdateDetails details) {
    if (_resizeStart == null || _initialSize == null) return;

    final delta = details.globalPosition - _resizeStart!;
    final newSize = Size(
      _initialSize!.width + delta.dx,
      _initialSize!.height + delta.dy,
    );

    // REQ-U-08 — resize handle gesture wired; live resizing deferred.
    widget.onResize?.call(newSize);
  }

  void _onResizePanEnd(DragEndDetails details) {
    _resizeStart = null;
    _initialSize = null;
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Title bar with close icon (REQ-U-07)
        Container(
          color: Colors.grey[300],
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: widget.onClose,
                tooltip: 'Close',
              ),
            ],
          ),
        ),
        // Child content
        Expanded(
          child: widget.child,
        ),
        // Resize handle at bottom-right corner (REQ-U-08/09)
        Align(
          alignment: Alignment.bottomRight,
          child: GestureDetector(
            onPanDown: _onResizePanDown,
            onPanUpdate: _onResizePanUpdate,
            onPanEnd: _onResizePanEnd,
            child: MouseRegion(
              cursor: SystemMouseCursors.resizeDownRight,
              child: Padding(
                padding: const EdgeInsets.all(4),
                child: Icon(
                  Icons.drag_handle,
                  size: 20,
                  color: Colors.grey[600],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
