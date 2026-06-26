import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/theme.dart';
import '../features/cases/case_detail.dart';
import '../features/cases/cases_list.dart';
import '../features/cases/providers/selected_case_provider.dart';
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
      child: const CasesList(),
    );
  }

  Widget _buildDetailPane() {
    return Expanded(
      child: Container(
        color: NSightColors.background,
        child: Consumer(
          builder: (context, ref, _) {
            final selected = ref.watch(selectedCaseProvider);
            if (selected == null) {
              return Center(
                child: Text('Select a case', style: _labelStyle()),
              );
            }
            return const CaseDetail();
          },
        ),
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
        child: const CasesList(),
      ),
      bottomNavigationBar: BottomNav(
        selected: _section,
        onSelected: (s) => setState(() => _section = s),
      ),
    );
  }
}
