import 'package:flutter/material.dart';

import '../config/theme.dart';
import 'bottom_nav.dart';
import 'icon_rail.dart';

/// Responsive shell — REQ-U-04.
///
/// At width >= 900 (desktop): icon rail + list pane (280 px) + expanded detail pane.
/// At width < 900 (mobile/narrow): single content pane + bottom nav.
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  NavSection _section = NavSection.cases;

  static const _desktopBreakpoint = 900.0;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final isDesktop = width >= _desktopBreakpoint;

    return isDesktop ? _buildDesktop() : _buildMobile();
  }

  // ── Desktop layout ────────────────────────────────────────────────────────

  Widget _buildDesktop() {
    return Scaffold(
      body: Row(
        children: [
          IconRail(
            selected: _section,
            onSelected: (s) => setState(() => _section = s),
          ),
          _buildListPane(),
          _buildDetailPane(),
        ],
      ),
    );
  }

  Widget _buildListPane() {
    return Container(
      width: 280,
      decoration: const BoxDecoration(
        color: NSightColors.surface,
        border: Border(right: BorderSide(color: NSightColors.border)),
      ),
      child: Center(child: Text('Cases', style: _labelStyle())),
    );
  }

  Widget _buildDetailPane() {
    return Expanded(
      child: Container(
        color: NSightColors.background,
        child: Center(child: Text('Detail', style: _labelStyle())),
      ),
    );
  }

  TextStyle _labelStyle() => const TextStyle(
        color: NSightColors.muted,
        fontSize: 16,
        fontWeight: FontWeight.w500,
      );

  // ── Mobile layout ─────────────────────────────────────────────────────────

  Widget _buildMobile() {
    return Scaffold(
      body: Container(
        color: NSightColors.background,
        child: Center(child: Text('Cases', style: _labelStyle())),
      ),
      bottomNavigationBar: BottomNav(
        selected: _section,
        onSelected: (s) => setState(() => _section = s),
      ),
    );
  }
}
