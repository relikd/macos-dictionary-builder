#!/usr/bin/env python3
import os
import argparse
from shutil import rmtree
from .parse import makeDictXML
from .meta import makeMetaPlistInteractive, writeMetaPlist, TODAY
from .devkit import callDevKitScript
from typing import TextIO, Optional

__all__ = ['runDictPipeline']


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('infile', type=argparse.FileType('r', encoding='utf8'),
                        metavar='FILE', help='word list (e.g., "DE-EN.txt")')
    parser.add_argument('-outdir', type=str, metavar='DIR', help='''
        Output directory (default: same as input file).''')
    parser.add_argument('--no-reverse', action='store_true', help='''
        By default, this script creates a reverse translation for all entries.
        With this flag, the word list is parsed as-is (no reverse mapping).''')
    args = parser.parse_args()
    runDictPipeline(args.infile, args.outdir, reverse=not args.no_reverse)


def runDictPipeline(
    infile: TextIO, outdir: Optional[str] = None, *, reverse: bool = True,
) -> None:
    '''
    Generates XML and meta plist files (in interactive mode).

    Calls:
        1. `makeDictXML`
        2. `makeMetaPlistInteractive`
        3. `writeMetaPlist`
        4. `callDevKitScript`

    Args:
        outdir : If empty, use same dir as input file.
        reverse : If `False`, generate only one way translations.
    '''
    outdir = outdir or os.path.dirname(infile.name)
    workdir = os.path.join(outdir, os.path.basename(infile.name) + '.tmp')
    clean_name = os.path.splitext(os.path.basename(infile.name))[0]

    rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)

    xml_file = os.path.join(workdir, 'data.xml')
    plist_file = os.path.join(workdir, 'meta.plist')
    dict_file = os.path.join(workdir, 'Tmp.dictionary')

    print('[1/3] Generate XML: data.xml ...')
    # NOTE: "infile" is auto-closed after this call
    entryCount = makeDictXML(infile, xml_file, reverse=reverse)
    print(f'=> {entryCount} entries')

    print()
    print('[2/3] Generate metadata: meta.plist ...')
    plistDict = makeMetaPlistInteractive(
        version=TODAY, reverse=reverse,
        extra_info=f'Generated on {TODAY} ({entryCount} entries)')
    writeMetaPlist(plist_file, plistDict)

    print()
    print('[3/3] Generate dictionary ...')
    if not callDevKitScript(dict_file, xml=xml_file, plist=plist_file):
        exit(1)

    print()
    print('Finalize ...')
    chosen_name = plistDict.get('CFBundleName')
    if not chosen_name:
        chosen_name = (input(f'Dictionary filename (default: {clean_name}): ')
                       or clean_name)
    chosen_name = chosen_name.removesuffix('.dictionary') + '.dictionary'
    print(f'=> using filename: {chosen_name}')

    sys_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Dictionaries')
    if _askBool(f'Install (move) to {sys_dir}? [Yn]', 'y'):
        outdir = sys_dir

    fname = os.path.join(outdir, chosen_name)
    if os.path.exists(fname):
        print(f'WARN: Already exists: {fname}')
        if not _askBool('overwrite? [yN]', 'n'):
            print(f'abort. keeping {workdir}')
            return

    rmtree(fname, ignore_errors=True)  # cleanup previous
    os.rename(dict_file, fname)
    print(f'=> {fname}')
    rmtree(workdir, ignore_errors=True)  # workdir is always a ".tmp" subfolder

    print()
    print('done.')


def _askBool(msg: str, default: str) -> bool:
    ''' Helper for asking a yes-no questions. '''
    return (input(msg + ' ') or default)[0].lower() == 'y'


if __name__ == '__main__':
    main()
