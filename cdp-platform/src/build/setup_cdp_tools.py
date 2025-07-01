#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build script for the cdp_tools package."""

import os
import time

import setuptools


def read_file(file_name: str) -> str:
    """Read file."""
    with open(file_name, 'r', encoding='utf-8') as file_obj:
        return file_obj.read()


os.chdir(os.path.dirname(__file__) or '.')
setuptools.setup(
    name='cdp_tools',
    version=time.strftime('%y.%-m.%-d'),
    author='Merck',
    author_email='mail@example.com',
    description='Merck CDP tools package',
    long_description=read_file('../cdp_tools/README.rst'),
    long_description_content_type='text/x-rst',
    url='https://example.com',
    packages=['cdp_tools'],
    package_dir={'cdp_tools': '../cdp_tools'},
    install_requires=['boto3'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
