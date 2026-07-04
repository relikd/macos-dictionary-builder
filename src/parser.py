#!/usr/bin/env python3
import os
import re
import argparse
from dataclasses import dataclass
from typing import TextIO, NamedTuple

__all__ = ['makeDictXML', 'readDictTxt', 'writeDictXML',
           'Word', 'Line', 'Pair', 'Grouping']

_PARENS_PAIR_LOOKUP = {
    ']': '[', ')': '(', '}': '{', '>': '<',
    '[': ']', '(': ')', '{': '}', '<': '>',
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('infile', type=argparse.FileType('r', encoding='utf8'),
                        metavar='FILE', help='word list (e.g., "DE-EN.txt")')
    parser.add_argument('-outfile', type=str, metavar='OUT', help='''
        XML output file (default: <FILE> + .xml)''')
    parser.add_argument('--no-reverse', action='store_true', help='''
        By default, this script creates a reverse translation for all entries.
        With this flag, the word list is parsed as-is (no reverse mapping).''')
    args = parser.parse_args()
    fname = args.outfile or (args.infile.name + '.xml')
    makeDictXML(args.infile, fname, no_reverse=args.no_reverse)


def makeDictXML(
    infile: TextIO, outfile: str, *, no_reverse: bool = False,
) -> int:
    '''
    This is a wrapper around `readDictTxt()` + `writeDictXML()`.
    NOTE: Closes input file automatically once it is processed.
    '''
    data = readDictTxt(infile)
    infile.close()  # close as soon as parsed to free up IO
    return writeDictXML(data, outfile, no_reverse=no_reverse)


######################################################
#
#  Helper methods
#
######################################################

def _htmlSafe(txt: str) -> str:
    return txt.replace('&', '&amp;').replace('<', '&lt;').replace(
        '>', '&gt;').replace('"', '&quot;')


def _trimWhitespace(txt: str) -> str:
    ''' `strip()` and remove multiple whitespace. '''
    return re.compile(r'[ ]{2,}').sub(' ', txt.strip())


######################################################
#
#  Word (parser for a single translation string)
#
######################################################

class Word(list[str]):
    ''' Class for parsing metadata of a translation string. '''
    @staticmethod
    def new(raw: str) -> 'Word':
        '''
        Split by top-level modifier data fields:
        `<abbreviations> [comments] (optional) {word-class}`
        '''
        rv = Word()
        prev = 0
        level = 0
        inbetween = False
        chrOpen, chrClose = '', ''
        for i, char in enumerate(raw.strip()):
            if char in '[({<':
                if chrOpen:
                    inbetween = True
                    if char == chrOpen:
                        level += 1
                else:
                    level = 1
                    if i != prev:
                        rv.append(raw[prev:i])
                    prev = i
                    chrOpen, chrClose = char, _PARENS_PAIR_LOOKUP[char]
            elif char == chrClose:
                level -= 1
                if level == 0:
                    rv.append(raw[prev:i + 1])
                    prev = i + 1
                    inbetween = False
                    chrOpen, chrClose = '', ''
        if prev <= i:
            rv.append(raw[prev:i+1])
        # hopefully, all parenthesis are balanced
        if level == 0:
            return rv
        # else: fix unbalanced parenthesis
        # if no other parenthesis exists until EOL, close last opened
        if not inbetween:
            return Word.new(raw + chrClose)
        # if other parenthesis exists, assume the first is erroneous
        return Word.new(raw[:prev] + raw[prev + 1:].lstrip())

    @property
    def raw(self) -> str:
        ''' Just the plain string (all parts concatenated). '''
        return ''.join(self)

    @property
    def plain(self) -> str:
        ''' Remove all additional modifier ranges. As clean as possible. '''
        return _htmlSafe(_trimWhitespace(''.join(
            x for x in self if x[0] not in '[({<')))

    @property
    def optional(self) -> str:
        '''Alternative version which keeps parenthesis (optional keywords).'''
        return _htmlSafe(_trimWhitespace(''.join(
            x[1:-1] if x[0] == '(' else x for x in self if x[0] not in '[{<')))

    @property
    def abbrevs(self) -> list[str]:
        ''' Just the abbreviation part (angle brackets) '''
        return [_htmlSafe(y.strip())
                for x in self if x[0] == '<'
                for y in x[1:-1].split(',') if y.strip()]

    @property
    def styled(self) -> str:
        ''' `normal <abbrev> [expl] (opt) {cls}` '''
        rv = ''
        prependWhitespace = False
        for part in self:
            # Apple removes whitespace between inline text.
            # e.g.: "<cls>{f}</cls> <expl>[me]</expl>" ==> '{f}[me]'
            # Stupid workaround: move space into next container.
            if part == ' ':
                prependWhitespace = True
                continue
            safe = (' ' if prependWhitespace else '') + _htmlSafe(part)
            prependWhitespace = False
            # add tags according to meta type
            char = part[0]
            if char == '[':
                rv += '<expl>' + safe + '</expl>'
            elif char == '(':
                rv += '<opt>' + safe + '</opt>'
            elif char == '{':
                rv += '<cls>' + safe + '</cls>'
            else:
                rv += safe  # keep abbrev as normal text
        return rv


######################################################
#
#  Line (parser for a translation line / pair of two `Word`)
#
######################################################

@dataclass
class Line:
    '''An entry is defined by: `word\ttranslation\tpartOfSpeech\tcategories`'''
    lineNo: int
    word: Word
    trans: Word
    partOfSpeech: str
    categories: list[str]

    def __init__(self, lineNo: int, line: str):
        self.lineNo = lineNo
        parts = line.split('\t') + ['']  # categories are optional
        assert len(parts) > 3, 'expects at least 2 tabs per line'
        self.word = Word.new(parts[0])
        self.trans = Word.new(parts[1])
        self.partOfSpeech = parts[2].strip()
        category = parts[3]
        if len(category) < 3:
            self.categories = []
        else:
            assert category[0] == '[' and category[-1] == ']'
            self.categories = category[1:-1].strip().split('] [')


######################################################
#
#  Grouping
#
######################################################

class Pair(NamedTuple):
    word: Word
    trans: Word


class Grouping(dict[str, list[int]]):
    def __init__(self, data: list[Line], inverse: bool):
        self.data = data
        self.inverse = inverse

        def fn(word: Word, index: int) -> None:
            # abbreviations get their own search term
            for w in [word.plain] + word.abbrevs:
                self.setdefault(w, []).append(index)

        if inverse:
            for i, entry in enumerate(data):
                fn(entry.trans, i)
        else:
            for i, entry in enumerate(data):
                fn(entry.word, i)

    def sortedEntries(self, key: str) -> list[Pair]:
        ''' If `inverse`, return `(trans, word)` else `(word, trans)`. '''
        gen = (self.data[x] for x in self[key])
        if self.inverse:
            return sorted(map(lambda x: Pair(x.trans, x.word), gen))
        else:
            return sorted(map(lambda x: Pair(x.word, x.trans), gen))

    def unreferenced(self) -> set[int]:
        ''' Return line numbers for omitted entries. '''
        return set(self.data[x].lineNo for x in self.get('', []))


######################################################
#
#  Actual processing
#
######################################################

def readDictTxt(infile: TextIO) -> list['Line']:
    ''' Parse input file and generate in-memory list (calls `readlines`). '''
    rv = []  # type: list[Line]
    for lineNo, line in enumerate(infile.readlines(), 1):
        line = line.strip(' \n\r')  # keep tabs
        if line and not line.startswith('#'):  # ignore empty & comments
            rv.append(Line(lineNo, line))
    return rv


def writeDictXML(data: list[Line], toFile: str, *, no_reverse: bool) -> int:
    ''' Iterate in-memory dictionary tree and write to file. '''
    tmp_file = toFile + '.tmp'
    if os.path.exists(tmp_file):
        os.remove(tmp_file)

    unref = {}  # type: dict[bool, set[int]]
    with open(tmp_file, 'w', encoding='utf8') as fp:
        fp.write('''
<?xml version="1.0" encoding="UTF-8"?>
<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">
'''.strip())
        idx = 0
        for inverse in [False] if no_reverse else [False, True]:
            grp = Grouping(data, inverse)
            for key in sorted(grp.keys()):
                if not key:
                    continue  # ignore sayings
                idx += 1
                fp.write('\n\n' + _generateEntry(idx, key, grp))
            unref[inverse] = grp.unreferenced()
            del grp  # free up memory immediatelly

        fp.write('\n\n</d:dictionary>')

    # atomic write
    os.rename(tmp_file, toFile)

    ur = unref[False] & unref.get(True, set())
    if ur:
        print(f'WARN: {len(ur)} unreferenced entries: (line no: {sorted(ur)})')
    return idx


# In general:
# - Apple auto-creates lower cased variants for <d:index> entries.
# - Thus, Dictionary app can concatenates multiple <d:entry> into one.
# - However, Spotlight only finds the first <d:entry> (even if multiple exist).
#
# We could fix this by manually concatenating <d:entry> into one (lower cased).
# But then, <d:entry> can only have one title.
# The Spotlight search would disply a wrong search term (noun vs. verb issue)
def _generateEntry(idn: int, plainTitle: str, store: Grouping) -> str:
    ''' Generate dictionary `<d:entry>` from list of `Entry`. '''
    data = store.sortedEntries(plainTitle)
    # d:title is shown in Spotlight as search term title
    rv = f'<d:entry id="{idn}" d:title="{plainTitle}">'
    # Generate alternative versions (with optional parenthesis in tact)
    alternatives = set(x.word.optional for x in data)
    # d:value is what can be found by search
    for term in sorted(alternatives.union([plainTitle])):
        if term:
            rv += f'<d:index d:value="{term}"/>'
    # TODO: remove verbose prefix, "to be ..."

    # generate visible part (in Dictionary app)
    prevTitle = Word()
    translations = set()  # type: set[str]
    # for entry in entries:
    for word, trans in data:
        if word != prevTitle:
            prevTitle = word
            rv += f'<h1>{word.styled}</h1>'
        rv += f'<p>{trans.styled}</p>'
        translations.add(trans.plain or trans.optional or _htmlSafe(trans.raw))

    # generate visible part (in Spotlight search)
    # sure, we could add a d:def for each translation separately,
    # but then, Spotlight will limit the results to the first two only
    rv += '<p d:def="1" hidden="1">{} <d:def></d:def></p>'.format(
        ' · '.join(sorted(translations)))
    return rv + '</d:entry>'


if __name__ == '__main__':
    main()
