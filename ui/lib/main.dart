import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'config/theme.dart';
import 'shell/app_shell.dart';

void main() {
  runApp(const ProviderScope(child: NSightApp()));
}

/// Root application widget.
class NSightApp extends StatelessWidget {
  const NSightApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'nSight',
      theme: buildNSightTheme(),
      debugShowCheckedModeBanner: false,
      home: const AppShell(),
    );
  }
}
