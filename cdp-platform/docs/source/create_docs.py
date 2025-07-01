#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create the ics documentation."""

import argparse
import os
import pickle  # nosec
import shutil
import subprocess  # nosec
from pathlib import Path


def _run_cmd(cmd: str, args: list[str | Path]):
    """Run command with arguments."""
    cmd_path = shutil.which(cmd)
    if cmd_path is None:
        raise RuntimeError(f'{cmd!r} not found!')
    cmd_args: list[str | Path] = [cmd_path]
    subprocess.check_call(cmd_args + args)  # nosec


def main() -> None:
    """Main function to create the documentation."""
    doc_source_path = Path(__file__).resolve().parent
    os.chdir(doc_source_path)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--output_format',
        default='singlehtml',
        help='Output format [singlehtml, html, pdf, confluence]')
    parser.add_argument(
        '--refs',
        default=False,
        action='store_true',
        help='Dump references after creating the documentation')
    args = parser.parse_args()

    ics_root_path = doc_source_path.parent.parent
    # -W Stop on warnings
    # -E ignore existing environment
    # -a write all files
    if args.refs:
        build_args = '-q'
    else:
        # Disabled -W for now because of:
        # https://github.com/pydantic/pydantic/discussions/7763
        build_args = '-a'
    if args.output_format == 'confluence':
        build_args = '-Ea'
        shutil.copy('indices_and_tables.rst.confluence',
                    'indices_and_tables.rst')
    else:
        shutil.copy('indices_and_tables.rst.local', 'indices_and_tables.rst')
    build_path = ics_root_path / 'docs' / 'build'
    _run_cmd(
        'sphinx-build',
        [build_args, doc_source_path, build_path, '-b', args.output_format])
    print('PLEASE IGNORE "autodoc: failed to import module..." WARNINGS ABOVE')
    os.unlink('indices_and_tables.rst')

    if args.refs:
        env_pickle_path = build_path / '.doctrees' / 'environment.pickle'
        with env_pickle_path.open('rb') as file_obj:
            dat = pickle.load(file_obj)  # nosec
            print('\n'.join(dat.domaindata['std']['labels'].keys()))


if __name__ == '__main__':
    main()
