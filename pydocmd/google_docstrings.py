# Copyright (c) 2017  Niklas Rosenstein
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
This module implements preprocessing Google + Markdown-like docstrings and
converts it to fully markdown compatible markup.
"""


import re


class LineFinished(Exception):
  pass


class Preprocessor(object):
  """
  This class implements the basic preprocessing.
  """

  def __init__(self, config):
    self.config = config
    self.indent = 0
    self.valid_sections = {
      'args': 'Arguments',
      'arguments': 'Arguments',
      'parameters': 'Arguments',
      'params': 'Arguments',
      'attributes': 'Attributes',
      'members': 'Attributes',
      'raises': 'Raises',
      'return': 'Returns',
      'returns': 'Returns',
      'yields': 'Yields',
    }
    self._current_section = None
    self._in_codeblock = False
    self._in_doctest_codeblock = False
    self._lines = []

  def preprocess_section(self, section):
    """
    Preprocess the contents of *section*.
    """
    self._current_section = None
    self._in_codeblock = False
    self._in_doctest_codeblock = False
    self._lines = []

    sig = section.loader_context.get('sig')
    if sig:
      # sig is not markdown, but will be read as markdown.
      #   Any '_*\' should be escaped.
      for char in r'\*_':
        sig = sig.replace(char, '\\' + char)
      section.title = sig
      if self.config.get('markdown_header_id'):
        section.title = section.title + '  {{#{}}}'.format(sig.split('(', 1)[0])

    current_section = None
    for line in section.content.split('\n'):
      try:
        line = self._process_codeblock(line)
        line = self._process_doctest_codeblock(line)
        line = self._process_line(line)
        self._lines.append(line)
      except LineFinished:
        continue
    section.content = self._preprocess_refs('\n'.join(self._lines))

  def _process_codeblock(self, line):
    if line.startswith("```"):
      self._in_codeblock = not self._in_codeblock
    if self._in_codeblock:
      self._lines.append(line)
      raise LineFinished()  # no further processing of line.
    return line

  def _process_doctest_codeblock(self, line):
    blank_token = "<BLANKLINE>"
    block_indicated = line.lstrip()[:4] in ['>>> ', '... ']

    # Expand tabs
    # Doctests expects output to not contain tabs, and processes input tabs to 8 spaces.
    # We should follow suit, since doctest is the reference here.
    whitespace = line[0:len(line) - len(line.lstrip())]
    processed_line = whitespace.replace('\t', ' '*8) + line[len(whitespace):]

    if not self._in_doctest_codeblock:
      if block_indicated:
        # start a block.
        self._in_doctest_codeblock = True
        self._lines.append("```python")
        self._lines.append(processed_line)  # No further processing.
        raise LineFinished
      else:
        # No block.
        return line

    # We're in a doctest codeblock
    # Valid case: Line is code
    if block_indicated:
      # Normal case
      self._lines.append(processed_line)
      raise LineFinished  # No further processing.
    # Valid case:  Line is the blank output line token.
    if line.strip() == blank_token:
      self._lines.append('')
      # It's fairly possible that the blank line token isn't spaced the same,
      # and it's not explicitly required to by the python docs, so I skipped
      # adding it as the doctest_codeblock_last line here.
      raise LineFinished
    # Valid case: Output line
    if line.strip():
      self._lines.append(processed_line)
      raise LineFinished
    # Valid case: Blank line ends block
    else:
      self._in_doctest_codeblock = False
      self._lines.append("```")
      return line

  def _process_line(self, line):
    if not line.strip():
      return line

    match = re.match(r'^(.+):$', line.rstrip())
    if match:
      sec_name = match.group(1).strip().lower()
      if sec_name in self.valid_sections:
        self._current_section = self.valid_sections[sec_name]
        line = '__{}__\n'.format(self._current_section)
        self.indent = -1
        return line

    # check indent level.
    match = re.match('(\s+)', line)
    whitespace = ''
    if match:
      whitespace = match.group(1)
    if self.indent == -1:
      # this should be the first line with content after a section start.
      self.indent = len(whitespace)
    else:
      if len(whitespace) < self.indent:
        # indentation reduced, section ends.
        self._current_section = None
        # we're not handling nested sections
        self.indent = 0
    line = line[self.indent:]

    # TODO: Parse type names in parentheses after the argument/attribute name.
    if self._current_section in ('Arguments',):
      if ':' in line:
        a, b = line.strip().split(':', 1)
        if all((a.strip(), b.strip())):
          line = '* __{}__: {}'.format(a, b)
    elif self._current_section in ('Attributes', 'Raises'):
      if ':' in line:
        a, b = line.strip().split(':', 1)
        if all((a.strip(), b.strip())):
          line = '* `{}`: {}'.format(a, b)
    elif self._current_section in ('Returns', 'Yields'):
      if ':' in line:
        a, b = line.strip().split(':', 1)
        if all((a.strip(), b.strip())):
          line = '`{}`:{}'.format(a, b)
    return line

  def _preprocess_refs(self, content):
    # TODO: Generate links to the referenced symbols.
    def handler(match):
      ref = match.group('ref')
      parens = match.group('parens') or ''
      has_trailing_dot = False
      if not parens and ref.endswith('.'):
        ref = ref[:-1]
        has_trailing_dot = True
      result = '`{}`'.format(ref + parens)
      if has_trailing_dot:
        result += '.'
      return (match.group('prefix') or '') + result
    return re.sub('(?P<prefix>^| |\t)#(?P<ref>[\w\d\._]+)(?P<parens>\(\))?', handler, content)
