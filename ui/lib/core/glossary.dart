/// Canonical user-facing terms and forbidden synonyms — REQ-U-02.
///
/// Import this file in tests to drive the terminology lint.
/// Do not import it in production widgets; it is a policy definition only.
library;

/// The canonical set of user-facing terms in nSight's vocabulary.
const canonicalTerms = [
  'Case',
  'Material',
  'Question',
  'Report',
  'Variable',
  'Chart',
  'Single',
  'Multi',
];

/// Maps each forbidden synonym to the canonical term that must replace it.
///
/// Keys are the disallowed words (matched case-insensitively as whole words).
/// Values are the canonical nSight terms to use instead.
const forbiddenSynonyms = <String, String>{
  'Project': 'Case',
  'Folder': 'Case',
  'Dataset': 'Material',
  'Field': 'Variable',
  'Column': 'Variable',
  'Graph': 'Chart',
  'Plot': 'Chart',
  'Diagram': 'Chart',
  'Deck': 'Report',
};
