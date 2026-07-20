#!/usr/bin/env python3
import os
import re
import bisect
import argparse
from dataclasses import dataclass
from typing import TextIO, NamedTuple, Iterator, Iterable

__all__ = ['makeDictXML', 'readDictTxt', 'groupDictKeys', 'writeDictXML',
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
    makeDictXML(args.infile, fname, reverse=not args.no_reverse)


def makeDictXML(infile: TextIO, outfile: str, *, reverse: bool = True) -> int:
    '''
    A wrapper around `readDictTxt()` + `groupDictKeys()` + `writeDictXML()`.
    '''
    grouping = groupDictKeys(readDictTxt(infile), reverse=reverse)
    return writeDictXML(grouping, outfile)


######################################################
#
#  Helper methods
#
######################################################

_unsafeIndex = str.maketrans('', '', '-‐–−—\u030F®©™')
_unsafeHtml = {
    # delete lower control chars (except \t\n\r)
    **dict.fromkeys(set(range(0x20)).difference([0x9, 0xA, 0xD])),
    **dict.fromkeys(set(range(0x7F, 0xA0)).difference([0x85])),
    # technically also the following, but a dict with 2048 keys might be slower
    # (assuming these chars wont be used anyway)
    # : set(range(0xD800, 0xE000)).union([0xFFFE, 0xFFFF])
    ord('"'): '&quot;', ord('&'): '&amp;', ord('<'): '&lt;', ord('>'): '&gt;',
}


def _htmlSafe(txt: str) -> str:
    ''' Replace chars which are reserved in XML (`"&<>` + `ord(0-8)`). '''
    return txt.translate(_unsafeHtml)


def _indexSafe(txt: str) -> str:
    ''' Remove chars which break Apple's dictionary builder + 64 char limit '''
    # Apple's `build_key_index` has a limit of 127 characters.
    # But some chars will be expanded into multiple chars (e.g., ß -> ss)
    # The limit is for the expanded string, thus choose a lower limit
    if len(txt) == 1 and txt in '®©™':
        return txt
    return _trimWhitespace(txt.translate(_unsafeIndex))[:64]


def _trimWhitespace(txt: str) -> str:
    ''' `strip()` and remove multiple whitespace. '''
    return re.compile(r'[ ]{2,}').sub(' ', txt.strip())


def _printProgress(msg: str, percent: float) -> None:
    ''' Show progress bar: `{msg} [######  ] 75.0%` '''
    done = '#' * int(40 * percent)
    print(f'\r{msg} [{done:<40}] {percent:.1%}', end='')


def _printProgressDone(msg: str) -> None:
    ''' Set progess to 100% and end print line. '''
    _printProgress(msg, 1.0)
    print()


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
            rv.append(raw[prev:i + 1])
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
        if len(parts) < 4:  # incl. +1 see above
            msg = f'expects at least 2 tabs per line (line {lineNo})'
            raise RuntimeError(msg)
        self.word = Word.new(parts[0])
        self.trans = Word.new(parts[1])
        self.partOfSpeech = parts[2].strip()
        category = parts[3]
        if category.startswith('[') and category.endswith(']'):
            self.categories = category[1:-1].strip().split('] [')
        else:
            self.categories = []


######################################################
#
#  Grouping
#
######################################################

class Pair(NamedTuple):
    word: Word
    trans: Word
    isAbbrev: bool


class Grouping(dict[str, list[Pair]]):
    def __init__(
        self,
        data: Iterable[Line],
        *,
        forward: bool = True,
        backward: bool = True,
    ):
        self.unreferenced: list[Line] = []

        def fn(a: Word, b: Word) -> bool:
            ''' Returns `True` if referenced '''
            # abbreviations get their own search term
            rv = False
            for i, w in enumerate([a.plain] + a.abbrevs):
                key = _indexSafe(w)
                if key:
                    bisect.insort(self.setdefault(key, []), Pair(a, b, i > 0))
                    rv = True
            return rv

        for entry in data:
            refA = fn(entry.word, entry.trans) if forward else False
            refB = fn(entry.trans, entry.word) if backward else False
            if not (refA or refB):
                self.unreferenced.append(entry)


######################################################
#
#  Actual processing
#
######################################################

PROGRESS_INTERVAL = 0xFFF  # every 4k


def readDictTxt(infile: TextIO, *, progress: bool = True) -> Iterator['Line']:
    '''
    Parse input file and generate in-memory list (calls `readlines`).

    Yields
        In-memory data structure `Line` by line
    '''
    filesize = os.fstat(infile.fileno()).st_size
    lineNo = 0
    line = infile.readline()
    while line:
        if progress and lineNo & PROGRESS_INTERVAL == 0:
            _printProgress('reading lines', infile.tell() / filesize)
        line = line.strip(' \n\r')  # keep tabs
        if line and not line.startswith('#'):  # ignore empty & comments
            lineNo += 1
            yield Line(lineNo, line)
        line = infile.readline()
    if progress:
        _printProgressDone('reading lines')
        print(f'\rdone reading. {lineNo} lines')


def groupDictKeys(data: Iterable[Line], *, reverse: bool = True) -> Grouping:
    '''
    Iterate over all `Line` and group by plain / simple name.

    Params:
        reverse : If `True`, include reverse mapping (de>en + en>de)
    '''
    return Grouping(data, forward=True, backward=reverse)


def writeDictXML(data: Grouping, toFile: str, *, progress: bool = True) -> int:
    ''' Iterate in-memory dictionary tree and write to file. '''
    tmp_file = toFile + '.tmp'
    if os.path.exists(tmp_file):
        os.remove(tmp_file)

    with open(tmp_file, 'w', encoding='utf8') as fp:
        fp.write('''
<?xml version="1.0" encoding="UTF-8"?>
<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">
'''.strip())

        total = len(data)
        for idx, key in enumerate(sorted(data.keys()), 1):
            fp.write('\n' + _generateEntry(idx, key, data.pop(key)))
            if progress and idx & PROGRESS_INTERVAL == 0:
                _printProgress('write entries', idx / total)

        fp.write('\n</d:dictionary>')

    if progress:
        _printProgressDone('write entries')
        print(f'done writing. {total} entries')

    # atomic write
    os.rename(tmp_file, toFile)

    if data.unreferenced:
        print('WARN: {} unreferenced entries: (line no: {})'.format(
            len(data.unreferenced), [x.lineNo for x in data.unreferenced]))
    return idx


# In general:
# - Apple auto-creates lower cased variants for <d:index> entries.
# - Thus, Dictionary app can concatenates multiple <d:entry> into one.
# - However, Spotlight only finds the first <d:entry> (even if multiple exist).
#
# We could fix this by manually concatenating <d:entry> into one (lower cased).
# But then, <d:entry> can only have one title.
# The Spotlight search would disply a wrong search term (noun vs. verb issue)
def _generateEntry(idn: int, plainTitle: str, data: list[Pair]) -> str:
    ''' Generate dictionary `<d:entry>` from list of `Entry`. '''
    # d:title is shown in Spotlight as search term title
    rv = f'<d:entry id="{idn}" d:title="{plainTitle}">'

    # d:value is what can be found by search
    searchTerms = {plainTitle}.union(
        _indexSafe(x.word.optional) for x in data if not x.isAbbrev)
    for term in sorted(searchTerms):
        if term:
            rv += f'<d:index d:value="{term}"/>'

    # TODO: remove verbose prefix, "to be ..."

    # generate visible part (in Dictionary app)
    prevTitle = Word()
    translations: set[str] = set()
    # for entry in entries:
    for word, trans, _ in data:
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
