import 'package:flutter/material.dart';

import '../config/theme.dart';

/// Navigation sections for the nSight app.
enum NavSection { cases, settings }

/// Vertical icon rail shown on the left side of the 3-pane desktop layout.
class IconRail extends StatelessWidget {
  final NavSection selected;
  final ValueChanged<NavSection> onSelected;

  const IconRail({
    super.key,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      decoration: const BoxDecoration(
        color: NSightColors.surface,
        border: Border(right: BorderSide(color: NSightColors.border)),
      ),
      child: Column(
        children: [
          const SizedBox(height: 16),
          // App logo placeholder
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: NSightColors.accent,
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Icon(Icons.insights, color: Colors.white, size: 20),
          ),
          const SizedBox(height: 16),
          _RailIcon(
            icon: Icons.folder_outlined,
            selected: selected == NavSection.cases,
            onTap: () => onSelected(NavSection.cases),
            tooltip: 'Cases',
          ),
          const Spacer(),
          _RailIcon(
            icon: Icons.settings_outlined,
            selected: selected == NavSection.settings,
            onTap: () => onSelected(NavSection.settings),
            tooltip: 'Settings',
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _RailIcon extends StatelessWidget {
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final String tooltip;

  const _RailIcon({
    required this.icon,
    required this.selected,
    required this.onTap,
    required this.tooltip,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: selected
                  ? NSightColors.accentLight
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              icon,
              color: selected ? NSightColors.accent : NSightColors.muted,
              size: 22,
            ),
          ),
        ),
      ),
    );
  }
}
