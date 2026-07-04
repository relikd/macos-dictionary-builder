#!/usr/bin/env python3
import argparse
import plistlib
from sys import stderr
from datetime import datetime
from typing import Optional, NoReturn

__all__ = ['makeMetaPlistInteractive', 'makeMetaPlistDict', 'writeMetaPlist']

TODAY = datetime.today().strftime('%Y-%m-%d')


def _fatal(msg: str) -> NoReturn:
    print(f'ERROR: {msg}', file=stderr)
    exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('outfile', type=str, metavar='FILE', help='''
        Output plist file''')
    parser.add_argument('-bundleId', type=str, metavar='ID', help='''
        Unique identifier for dictionary (required unless interactive mode)''')
    parser.add_argument('-name', type=str, help='''
        Name shown on dictionary tab and in Spotlight results.
        If none provided, macOS will use the filename as name.''')
    parser.add_argument('-version', type=str, help=f'''
        If none provided, use current date ("{TODAY}")''')
    parser.add_argument('-description', type=str, metavar='DESC', help='''
        Text visible in settings (in dictionary info box).''')
    parser.add_argument('-extra-info', type=str, metavar='INFO', help='''
        Append extra info after description (even if description is empty).''')
    parser.add_argument('-lang', type=str, nargs=2, metavar='CODE', help='''
        Pair of two-letter country code (e.g., "de en").
        Visible in settings (in parenthesis after dict name).''')
    parser.add_argument('--no-reverse', action='store_true', help='''
        Only relevant for the -lang option. Omits the reverse translation pair.
        If xml was generated with this flag, you should use it here too.''')
    parser.add_argument('--frontmatter', action='store_true', help='''
        Enables front-/backmatter. Requires a new XML entry:
        <d:entry id="front_back_matter" d:title="..">..</d:entry>''')
    parser.add_argument('--interactive', action='store_true', help='''
        Interactive mode. Ask user for input values.''')

    args = parser.parse_args()
    if args.interactive:
        data = makeMetaPlistInteractive(
            bundleId=args.bundleId, name=args.name, version=args.version,
            desc=args.description, extra_info=args.extra_info, lang=args.lang,
            no_reverse=args.no_reverse, frontmatter=args.frontmatter)
    else:
        if not args.bundleId:
            _fatal('bundleId is mandatory in non-interactive mode')
        data = makeMetaPlistDict(
            args.bundleId, name=args.name, version=args.version,
            desc=args.description, extra_info=args.extra_info, lang=args.lang,
            no_reverse=args.no_reverse, frontmatter=args.frontmatter)

    writeMetaPlist(args.outfile, data)


def makeMetaPlistInteractive(
    *,
    bundleId: Optional[str] = None,
    name: Optional[str] = None,
    version: Optional[str] = None,
    desc: Optional[str] = None,
    extra_info: Optional[str] = None,
    lang: Optional[tuple[str, str]] = None,
    no_reverse: bool = False,  # pass-through / no user-input
    frontmatter: bool = False,  # pass-through / no user-input
) -> dict:
    '''
    Ask user for input for any field which is not pre-filled.
    See `makeMetaPlistDict` for further details.
    '''
    bundleId = bundleId or input(
        'Unique identifier (e.g. "cc.dict.de-en") [required]: ')
    if not bundleId:
        _fatal('unique identifier is mandatory!')

    name = name if name is not None else input(
        'Short name (shown in dictionary tab and Spotlight results)'
        ' (if empty, macOS will use filename as name) [optional]: ')

    version = version if version is not None else input(
        f'Version number (default: {TODAY}) [optional]: ')

    desc = desc if desc is not None else input(
        'Description & copyright (shown in Dictionary settings) [optional]: ')

    if lang is None:
        l1 = input(
            'First language (two-letter country code, e.g. "de") [optional]: ')
        l2 = input(
            'Second language (two-letter country code, e.g. "en") [required]: '
            ) if l1 else None
        if l1 and l2:
            lang = (l1, l2)
        elif l1 and not l2:
            print('WARN: ignored. Must provide both (or none at all).')

    return makeMetaPlistDict(
        bundleId, name=name, version=version, desc=desc, lang=lang,
        extra_info=extra_info, no_reverse=no_reverse, frontmatter=frontmatter)


def makeMetaPlistDict(
    bundleId: str,
    *,
    name: Optional[str] = None,
    version: Optional[str] = None,
    desc: Optional[str] = None,
    extra_info: Optional[str] = None,
    lang: Optional[tuple[str, str]] = None,
    no_reverse: bool = False,
    frontmatter: bool = False,
) -> dict:
    '''
    Generate a meta plist file, describing the content of the dictionary.

    Args:
        bundleId : Unique identifier for the dictionary file
        name : If none provided, uses filename as title
        version : If none provided, use current date in iso format
        desc : Text visible in settings (dictionary info box)
        lang : Also visible in settings (in parenthesis after dict name)
        no_reverse : Omits the reverse translation pair (de-en but not en-de)
        frontmatter : Enables front-/backmatter. Requires a new XML entry:
                `<d:entry id="front_back_matter" d:title="..">..</d:entry>`
    '''
    # All fields allow a dash ("-") to indicate a missing value
    if not version or version == '-':
        version = TODAY
    data = {
        'CFBundleDevelopmentRegion': 'English',
        'CFBundleIdentifier': bundleId,
        'DCSDictionaryPreviewMarkupVersion': 1,  # enable Spotlight results
        'CFBundleShortVersionString': version,
    }

    # shown in Spotlight results and in Dictionary app
    if name and name != '-':
        # Either of those will fallback to the filename if not provided. Users
        # can rename their dictionary and see the change reflected everywhere.
        data['CFBundleName'] = name  # name of tab in Dictionary app
        data['CFBundleDisplayName'] = name  # Dictionary settings and Spotlight

    # "about this dictionary" info box (in Dictionary settings)
    info = ''.join(f'<p>{x}</p>' for x in [desc, extra_info] if x and x != '-')
    if info:
        data['DCSDictionaryCopyright'] = info

    # languages are shown in parenthesis (in Dictionary settings)
    if lang and lang[0] != '-' and lang[1] != '-':
        data['DCSDictionaryLanguages'] = [
            {
                'DCSDictionaryIndexLanguage': x,
                'DCSDictionaryDescriptionLanguage': y,
            }
            for x, y in ([lang] if no_reverse else [lang, lang[::-1]])
        ]

    # if an XML entry exists, this adds the `Go > Front/Back Matter` option
    if frontmatter:
        data['DCSDictionaryFrontMatterReferenceID'] = 'front_back_matter'
    return data


def writeMetaPlist(fname: str, data: dict) -> None:
    with open(fname, 'wb') as fp:
        plistlib.dump(data, fp, sort_keys=True)


if __name__ == '__main__':
    main()
