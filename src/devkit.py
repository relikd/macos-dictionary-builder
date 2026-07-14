#!/usr/bin/env python3
import os
import argparse
import subprocess
from sys import stderr
from shutil import rmtree
from tarfile import TarFile
from tempfile import TemporaryDirectory
from urllib.parse import quote  # for XML_CATALOG_FILES

__all__ = ['callDevKitScript', 'extractBundledDevKit']

# NOTE: The warning "* Note: No reference index record."
#       is shown, if no front/back-matter is used.

SRC_DIR = os.path.join(os.path.dirname(__file__), 'resources')
DEVKIT_DIR = os.path.join(  # TODO: use another location for devkit?
    os.path.expanduser('~'), '.config', 'macos_dictionary_builder')
_CSS_FILE = os.path.join(SRC_DIR, 'style.css')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('outfile', type=str, help='''
        File name and path (auto-appends ".dictionary" if missing)''')
    parser.add_argument('xml', type=str, metavar='dict.xml', help='''
        Path to main xml data file''')
    parser.add_argument('plist', type=str, metavar='meta.plist', help='''
        Path to metadata plist file''')
    parser.add_argument('-c', '--compress', action='store_true', help='''
        Whether to use compression (40%% file size, 6-8x longer)''')
    parser.add_argument('-f', '--force', action='store_true', help='''
        Overwrite existing <outfile>''')
    parser.add_argument('-q', '--quiet', action='count', default=0, help='''
        Reduce console output (-qq: also ignore errors)''')
    parser.add_argument('-css', type=str, metavar='PATH', help='''
        Path to custom CSS file (default: %(default)s)''', default=_CSS_FILE)
    args = parser.parse_args()
    callDevKitScript(
        args.outfile, xml=args.xml, plist=args.plist, compress=args.compress,
        css=args.css, force=args.force, logLevel=args.quiet)


def extractBundledDevKit() -> None:
    os.makedirs(DEVKIT_DIR, exist_ok=True)
    with TarFile.open(f'{SRC_DIR}/DevKit_12.5.tar.gz') as fp:
        fp.extractall(DEVKIT_DIR, [
            x for x in fp
            if x.path.startswith('Dictionary Development Kit/bin')])


def callDevKitScript(
    outfile: str,
    *,
    xml: str,
    plist: str,
    compress: bool = False,
    force: bool = False,
    css: str = _CSS_FILE,
    logLevel: int = 0,
) -> bool:
    '''
    Creates the final `.dictionary` bundle (last step).

    Args:
        outfile : Storage path (auto-appends `.dictionary` if missing)
        xml : Path to xml file generated with `makeDictXML`
        plist : Path to plist file generated with `makeMetaPlistDict`
        compress : Whether to use compression (40% file size, 6-8x longer)
        force : If `True`, overwrite existing `outfile`
        css : Path to custom CSS file
        logLevel : `0`: default, `1`: no stdout, `2`: + no stderr

    Returns:
        `True` if successful. `False` if already exists or shell script error.
    '''
    if not outfile.endswith('.dictionary'):
        outfile += '.dictionary'
    if os.path.exists(outfile) and not force:
        print(f'ERROR: Already exists: {outfile}', file=stderr)
        print('Use -f to overwrite existing files.', file=stderr)
        return False

    cmd = f'{DEVKIT_DIR}/Dictionary Development Kit/bin/build_dict.sh'
    # if no Dev Kit installed, extract bundled version
    if not os.path.exists(cmd):
        print('INFO: Dictionary Developer Kit not found. '
              f'Extracting bundled version into {DEVKIT_DIR} ...')
        extractBundledDevKit()

    # Apple's `build_dict.sh` accepts "10.5", "10.6", and "10.11"
    # The only difference between the last two, is that "10.11" creates a
    # "Resources" subfolder and sets info.plist version to 3 (instead of 2).
    # Apart from that, the files are identical.
    #
    # With a 77 MB text file (470 MB XML file):
    #  - 10.5 takes 8 min and creates a 780 MB dictionary
    #  - 10.11 takes 50-60 min and creates a 295 MB dictionary
    os_target = '10.11' if compress else '10.5'
    if logLevel == 0:
        print('Using compression:', 'YES' if compress else 'NO')
        if compress:
            print('NOTE: this may take a very long time (for large files ~1h)')
        else:
            print('NOTE: this may take a long time (for large files ~8min)')

    # prevent xsltproc from connecting to the internet [optional]
    env = os.environ.copy()
    env['XML_CATALOG_FILES'] = env.get('XML_CATALOG_FILES', '') \
        + ' ' + quote(os.path.join(SRC_DIR, 'catalog'))

    with TemporaryDirectory(prefix='macos_dictionary_builder_') as tmpDir:
        try:
            # "objects" dir is created at current path, change cwd accordingly
            subprocess.run([
                cmd, '-v', os_target, 'Tmp', os.path.abspath(xml),
                os.path.abspath(css), os.path.abspath(plist)],
                env=env, cwd=tmpDir, check=True,
                stdout=subprocess.DEVNULL if logLevel >= 1 else None,
                stderr=subprocess.DEVNULL if logLevel >= 2 else None)
        except subprocess.CalledProcessError:
            print('ERROR: executing shell script.', file=stderr)
            return False

        if os.path.exists(outfile):
            rmtree(outfile)
        os.rename(os.path.join(tmpDir, 'objects', 'Tmp.dictionary'), outfile)
        return True


if __name__ == '__main__':
    main()
