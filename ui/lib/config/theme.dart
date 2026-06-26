import 'package:flutter/material.dart';

/// nSight color palette — clean light theme adapted from Prima Volta's structure.
class NSightColors {
  static const background = Color(0xFFF5F7FA);
  static const surface = Color(0xFFFFFFFF);
  static const border = Color(0xFFDDE2EC);
  static const text = Color(0xFF1A1F36);
  static const muted = Color(0xFF6B7280);
  static const accent = Color(0xFF2563EB); // blue primary
  static const accentLight = Color(0xFFDEEAFD);
  static const green = Color(0xFF16A34A);
  static const yellow = Color(0xFFD97706);
  static const red = Color(0xFFDC2626);
}

ThemeData buildNSightTheme() {
  final base = ThemeData.light(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: NSightColors.background,
    colorScheme: const ColorScheme.light(
      primary: NSightColors.accent,
      secondary: NSightColors.accent,
      surface: NSightColors.surface,
      error: NSightColors.red,
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: NSightColors.text,
      onError: Colors.white,
    ),
    cardTheme: const CardThemeData(
      color: NSightColors.surface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(8)),
        side: BorderSide(color: NSightColors.border),
      ),
    ),
    dividerTheme: const DividerThemeData(
      color: NSightColors.border,
      thickness: 1,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: NSightColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: NSightColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: NSightColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: const BorderSide(color: NSightColors.accent),
      ),
      labelStyle: const TextStyle(color: NSightColors.muted, fontSize: 12),
      hintStyle: const TextStyle(color: NSightColors.muted, fontSize: 13),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: NSightColors.accent,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: NSightColors.muted,
        side: const BorderSide(color: NSightColors.border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
      ),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: NSightColors.surface,
      foregroundColor: NSightColors.text,
      elevation: 0,
      surfaceTintColor: Colors.transparent,
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: NSightColors.surface,
      contentTextStyle: TextStyle(color: NSightColors.text),
    ),
  );
}
