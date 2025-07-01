#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""This script allows to package the given task for running on CDP."""

import io
import argparse
import json
import logging
import os
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Optional
from urllib.parse import urlparse

import boto3
from nbconvert import PythonExporter
from pydantic import BaseModel, Field

###############################################################################
# This needs to stay in sync with
# src/lambda_functions/configure_jobs/task_config.py


class TaskRunConfig(BaseModel, extra='forbid'):
    """Class to store the run configuration of the task."""
    default: bool = False
    enabled_account_names: Optional[list[str]] = None
    enabled_scopes: Optional[list[str]] = None
    #: References an ICS plugin
    frequency: dict[str, Any] = Field(default_factory=dict)


class TaskConfig(BaseModel, extra='forbid'):
    """Class to store the standardized task configuration."""
    arguments: list[str] = Field(default_factory=list)
    cwd: str = '.'
    entry_point: str = 'script.py'
    environment: dict[str, str] = Field(default_factory=dict)
    kwargs: dict[str, str] = Field(default_factory=dict)
    python_lib_dirs: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    run: TaskRunConfig = TaskRunConfig()


###############################################################################


def _get_task_config() -> TaskConfig:
    """Parse the configuration for the given task."""
    task_config_file = Path('cdp_config.json')
    task_config_content = task_config_file.read_text(encoding='utf-8')
    return TaskConfig.model_validate_json(task_config_content)


def _get_requirements_from_file() -> list[str]:
    """Parse the list of python requirements for the given task."""
    req_file = Path('requirements.txt')
    if not req_file.exists():
        return []
    with req_file.open(encoding='utf-8') as file_obj:
        req_file_content = file_obj.read()
        req_list = [
            line.split('#')[0].split(';')[0].strip()
            for line in req_file_content.splitlines()
        ]
        return [req for req in req_list if req.strip()]


def _process_entry_point(user_entry_point: str) -> str:
    """Process and normalize the given entry point."""
    entry_point: Optional[str] = None
    if ':' in user_entry_point:
        script_file, entry_point = user_entry_point.split(':', 1)
    else:
        script_file = user_entry_point
    # Add missing .py extension
    script_path = Path(script_file)
    if (not script_path.exists()) and script_path.with_suffix('.py').exists():
        script_path = script_path.with_suffix('.py')
    # Convert jupyter notebooks
    if script_path.suffix == '.ipynb':
        export = PythonExporter()
        (body, resources) = export.from_filename(script_path.as_posix())
        del resources
        converted_script_file = Path(f'{script_path.stem}_cdp_conv.py')
        script_path = script_path.parent / converted_script_file
        with script_path.open('w', encoding='utf-8') as file_obj:
            file_obj.write(body)
    # Return the processed entry point
    if entry_point is None:
        return script_path.as_posix()
    return f'{script_path.as_posix()}:{entry_point}'


def get_ssm_parameter(parameter_name: str) -> Any:
    """Helper function to retrieve SSM parameters."""
    client = boto3.client('ssm')
    response = client.get_parameter(Name=parameter_name, WithDecryption=True)
    return json.loads(response['Parameter']['Value'])


def resolve_boto_session(session: Any = None) -> Any:
    """Helper function to determine which boto3 session to use."""
    return session or boto3.DEFAULT_SESSION or boto3.Session()


def _get_s3_client(session: Any = None) -> Any:
    """Get a boto S3 client."""
    session = resolve_boto_session(session)
    return session.client('s3')


def get_s3_bucket_path(s3_path: str) -> tuple[str, str]:
    """Parse the S3 path into bucket and key."""
    parsed_url = urlparse(s3_path, allow_fragments=False)
    data_bucket = parsed_url.netloc
    data_file = parsed_url.path.lstrip('/')
    return data_bucket, data_file


@contextmanager
def open_file_path(url: str,
                   mode='rb',
                   session: Any = None) -> Iterator[BinaryIO]:
    """This returns a file object for reading or writing, depending on the
    specified mode.

    Directories are implicitly created. The accepted URL can start with
    's3://' to refer to files on S3. Local files can be prefixed with
    'file://' (but it is not needed!)
    """
    if mode not in ['rb', 'wb']:
        raise ValueError('Invalid value for mode')
    if url.startswith('s3://'):
        log = logging.getLogger('cdp.utils.s3')
        client = _get_s3_client(session)
        (data_bucket, data_file) = get_s3_bucket_path(url.replace('\\', '/'))
        with io.BytesIO() as file_obj:
            if mode == 'rb':
                log.debug('Loading file %r from %r', data_file, data_bucket)
                client.download_fileobj(data_bucket, data_file, file_obj)
                file_obj.seek(0)
            yield file_obj
            if mode == 'wb':
                log.info('Writing file %r to %r', data_file, data_bucket)
                file_obj.seek(0)
                client.upload_fileobj(file_obj, data_bucket, data_file)
    else:
        if url.startswith('file://'):
            url = url[7:]
        if mode == 'wb':
            # Ensure directory exists and write via temporary file name
            os.makedirs(os.path.dirname(url), exist_ok=True)
            tmp_path = url + '.tmp'
            with open(tmp_path, 'wb') as file_obj:
                yield file_obj
            os.rename(tmp_path, url)
        else:
            with open(url, 'rb') as file_obj:
                yield file_obj


def _write_archive(archive_path: str) -> None:
    """Write archive."""
    with open_file_path(archive_path, 'wb') as file_obj:
        with zipfile.ZipFile(file_obj, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for entry in Path('.').rglob('*'):
                # Skip archive and git directories
                if '.git' in entry.parts:
                    continue
                if entry.is_symlink():
                    for sub_entry in entry.rglob('*'):
                        zip_file.write(sub_entry, sub_entry)
                else:
                    zip_file.write(entry, entry)


def _package_task(task_name: str, account_name: str) -> None:
    """Package the given task for running in the specified account."""
    # Collect the deployment configuration
    log = logging.getLogger('deployment')

    log.info('Reading task configuration')
    task_config = _get_task_config()
    log.info('Collecting task requirements')
    req_list = _get_requirements_from_file()
    task_config.requirements.extend(req_list)
    log.info('Preparing entry point %r', task_config.entry_point)
    task_config.entry_point = _process_entry_point(task_config.entry_point)

    # Store task configuration and code
    parameter_dict = get_ssm_parameter(f'/cdp/{account_name}/code_settings')
    s3_prefix = parameter_dict['code_bucket_s3_path_prefix']
    log.info('Packaging code of task %r', task_name)
    _write_archive(f'{s3_prefix}/{task_name}.zip')

    log.info('Store configuration for task %r', task_name)
    with open_file_path(f'{s3_prefix}/{task_name}.json', 'wb') as file_obj:
        file_obj.write(task_config.model_dump_json().encode('utf-8'))


def main() -> None:
    """Main function that packages the scripts."""
    parser = argparse.ArgumentParser(description='Package task files')
    parser.add_argument('task_name',
                        help='Name of the task / folder that is packaged')
    parser.add_argument('account_name',
                        help='Name of the account where the task should run')
    args = parser.parse_args()

    task_path = Path(args.task_name).resolve()
    os.chdir(task_path)
    _package_task(task_path.name, args.account_name)


if __name__ == '__main__':
    logging.basicConfig(level='INFO')
    main()
