"""The rules a preview is judged by.

Each oracle is a pure function over a matplotlib figure or a python-pptx slide,
and each ships with a test that feeds it a genuinely broken picture and
requires it to complain. A gate that passes everything looks exactly like a
gate that works.
"""
