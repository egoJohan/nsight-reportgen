import 'package:flutter/material.dart';

import '../config/theme.dart';
import 'icon_rail.dart';

/// Bottom navigation bar shown on narrow (mobile) layouts.
class BottomNav extends StatelessWidget {
  final NavSection selected;
  final ValueChanged<NavSection> onSelected;

  const BottomNav({
    super.key,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: NSightColors.surface,
        border: Border(top: BorderSide(color: NSightColors.border)),
      ),
      child: SafeArea(
        child: SizedBox(
          height: 56,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _NavItem(
                icon: Icons.folder_outlined,
                label: 'Cases',
                selected: selected == NavSection.cases,
                onTap: () => onSelected(NavSection.cases),
              ),
              _NavItem(
                icon: Icons.settings_outlined,
                label: 'Settings',
                selected: selected == NavSection.settings,
                onTap: () => onSelected(NavSection.settings),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = selected ? NSightColors.accent : NSightColors.muted;
    return InkWell(
      onTap: onTap,
      child: SizedBox(
        width: 72,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 10,
                fontWeight:
                    selected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
