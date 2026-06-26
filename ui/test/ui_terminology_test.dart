// Objective terminology lint — REQ-U-02.
//
// Scans every lib/**/*.dart file for user-facing display strings and fails if
// any of the forbidden synonyms (defined in lib/core/glossary.dart) appear as
// whole words inside those strings.
//
// Heuristic: a line is considered to contain a display string when it includes
// one of the following patterns:
//   Text(   label:   labelText:   title:   hintText:   tooltip:   SnackBar
//
// Escape hatch: add `// glossary-ignore` anywhere on a line to suppress the
// check for that line (e.g. when a forbidden word is used as a proper noun).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:nsight_ui/core/glossary.dart';

void main() {
  test(
    'UI display strings use only canonical nSight terms (REQ-U-02)',
    () {
      // Regex matching lines that are likely to contain user-facing strings.
      final displayLineRe = RegExp(
        r'Text\(|label:|labelText:|title:|hintText:|tooltip:|SnackBar',
      );

      // Regex that extracts single- or double-quoted string literals.
      // Handles backslash-escaped characters inside strings.
      final stringLiteralRe = RegExp(
        r'''('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")''',
      );

      final violations = <String>[];

      final libDir = Directory('lib');
      final dartFiles = libDir
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart'));

      for (final file in dartFiles) {
        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];

          // Skip lines carrying the escape-hatch marker.
          if (line.contains('// glossary-ignore')) continue;

          // Only inspect lines that look like display-string contexts.
          if (!displayLineRe.hasMatch(line)) continue;

          // Check each quoted string literal on this line.
          for (final literalMatch in stringLiteralRe.allMatches(line)) {
            final content = literalMatch.group(0)!;
            for (final entry in forbiddenSynonyms.entries) {
              final synonym = entry.key;
              final canonical = entry.value;
              final wordRe = RegExp(
                r'\b' + RegExp.escape(synonym) + r'\b',
                caseSensitive: false,
              );
              if (wordRe.hasMatch(content)) {
                violations.add(
                  '${file.path}:${i + 1} — forbidden synonym "$synonym" '
                  '(use "$canonical" instead): $content',
                );
              }
            }
          }
        }
      }

      if (violations.isNotEmpty) {
        fail(
          'Forbidden nSight terminology found in UI display strings '
          '(REQ-U-02):\n\n'
          '${violations.join('\n')}\n\n'
          'Fix the strings or add `// glossary-ignore` to suppress '
          'false positives.',
        );
      }
    },
  );
}
