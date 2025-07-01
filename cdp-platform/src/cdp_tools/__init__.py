# -*- coding: utf-8 -*-
"""This is the main module of the CDP tools."""

import inspect
import io
import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, BinaryIO, Iterator, Optional, TypeAlias
from urllib.parse import urlparse

import boto3
import botocore

Arn: TypeAlias = str
TaskName: TypeAlias = str


def _resolve_boto_session(session: Any = None) -> Any:
    """Helper function to determine which boto3 session to use."""
    return session or boto3.DEFAULT_SESSION or boto3.Session()


def _get_s3_client(session: Any = None) -> Any:
    """Get a boto S3 client."""
    session = _resolve_boto_session(session)
    return session.client('s3')


def _get_s3_bucket_path(s3_path: str) -> tuple[str, str]:
    """Parse the S3 path into bucket and key."""
    parsed_url = urlparse(s3_path, allow_fragments=False)
    data_bucket = parsed_url.netloc
    data_file = parsed_url.path.lstrip('/')
    return data_bucket, data_file


@contextmanager
def open_file_path(url: str,
                   mode='rb',
                   log: Optional[logging.Logger] = None,
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
        log = log or logging.getLogger('cdp_tools.s3')
        client = _get_s3_client(session)
        (data_bucket, data_file) = _get_s3_bucket_path(url.replace('\\', '/'))
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


def _invoke_lambda(lambda_arn: Arn, arg_str: str) -> str:
    """Invoke Lambda function with the given payload."""
    client = boto3.client('lambda')
    arg_bytes = arg_str.encode('utf-8')
    for retry in range(10):
        try:
            response = client.invoke(FunctionName=lambda_arn,
                                     Payload=arg_bytes)
            response_msg = response['Payload'].read().decode('utf-8')
            return response_msg
        except botocore.exceptions.ClientError as ex:
            if ex.response['Error']['Code'] == 'TooManyRequestsException':
                time.sleep(retry)
                continue
            raise ex
    raise RuntimeError(f'Unable to call lambda function {lambda_arn}')


@dataclass
class GlueConfig:
    """Class for the output of the Lambda function when run by the Glue job."""
    arguments: list[str]
    code_storage_path: str
    cwd: str
    entry_point: str
    environment: dict[str, str]
    kwargs: dict[str, str]
    python_lib_dirs: list[str]


def get_basic_glue_config(lambda_arn: Arn) -> GlueConfig:
    """Get basic task configuration from the lambda function."""
    config_lambda_event_str = json.dumps({
        'mode': 'get-basic-glue-config',
    })
    glue_config_str = _invoke_lambda(lambda_arn, config_lambda_event_str)
    return GlueConfig(**json.loads(glue_config_str))


def get_deployed_glue_config(lambda_arn: Arn, task_name: TaskName,
                             user_task_config_str: str) -> GlueConfig:
    """Get deployed task configuration from the lambda function."""
    user_task_config = json.loads(user_task_config_str)
    config_lambda_event_str = json.dumps({
        'mode': 'get-deployed-glue-config',
        'task_name': task_name,
        'user_task_config': user_task_config,
    })
    glue_config_str = _invoke_lambda(lambda_arn, config_lambda_event_str)
    tmp_glue_config_dict = json.loads(glue_config_str)
    if 'errorMessage' in tmp_glue_config_dict:
        lambda_error_msg = tmp_glue_config_dict.get('errorMessage')
        error_msg = f'Error while invoking lambda function: {lambda_error_msg}'
        raise RuntimeError(error_msg)
    environment = tmp_glue_config_dict['environment']
    final_glue_config = Template(glue_config_str).safe_substitute(environment)
    return GlueConfig(**json.loads(final_glue_config))


def apply_glue_config(log: logging.Logger, glue_config: GlueConfig) -> None:
    """Apply the given glue settings to the environment."""
    # Set current directory
    new_cwd = os.path.abspath(glue_config.cwd)
    log.info('Setting work directory %s ...', new_cwd)
    os.makedirs(new_cwd, exist_ok=True)
    os.chdir(new_cwd)
    sys.path.append(new_cwd)
    # Update python package search paths
    log.info('Setting python package directories ...')
    python_lib_dirs = glue_config.python_lib_dirs
    sys.path.extend(map(os.path.abspath, python_lib_dirs))
    # Set environment variables
    log.info('Setting job environment ...')
    os.environ['CDP_RUN'] = 'glue'
    for key, value in glue_config.environment.items():
        os.environ[key.upper()] = value


def _get_task_name() -> str:
    """Try to get task name from the caller stack."""
    msg = ('Unable to determine task name. '
           'Please call RunInfo.init with the test_task_name parameter!')
    module = inspect.getmodule(inspect.stack()[2][0])
    if module is None:
        raise RuntimeError(msg)
    caller_file = inspect.getfile(module)
    for path in Path(caller_file).resolve().parents:
        if (path / '.git').exists():
            return path.name
    raise RuntimeError(msg)


class RunInfo:
    """Container for CDP environment information."""

    @staticmethod
    def init(test_env: str,
             test_scope: str,
             test_profile: Optional[str] = None,
             test_task_name: Optional[str] = None,
             use_deployed_config: bool = False) -> None:
        """Initialize function for local running."""
        if not RunInfo.is_local():
            return
        if test_task_name is None:
            test_task_name = _get_task_name()
        test_task_name = 'template'
        if test_profile is not None:
            os.environ['AWS_PROFILE'] = test_profile
        run_info_init_path = (f's3://merck-cdp-{test_env}-code-storage'
                              f'/run_info/{test_scope}.json')
        with open_file_path(run_info_init_path, 'rb') as file_obj:
            run_info_init_dict = json.load(file_obj)
        config_lambda_arn = run_info_init_dict['lambda_arn']
        if use_deployed_config:
            glue_config = get_deployed_glue_config(config_lambda_arn,
                                                   test_task_name, '{}')
        else:
            glue_config = get_basic_glue_config(config_lambda_arn)
        apply_glue_config(logging.getLogger('cdp.local'), glue_config)

    @staticmethod
    def is_local() -> bool:
        """Return true if script is not run as part of the step function."""
        return os.environ.get('CDP_RUN', '') != 'glue'

    @staticmethod
    def get_country() -> str:
        """Return the ISO 3166-1 country code."""
        return RunInfo.get_scope()

    @staticmethod
    def get_scope() -> str:
        """Return the ISO 3166-1 country code."""
        return RunInfo.get_job_env('CDP_ENV_SCOPE')

    @staticmethod
    def get_account_name() -> str:
        """Return the account name (dev/staging/prod)."""
        return RunInfo.get_job_env('CDP_ENV_ACCOUNT_NAME')

    @staticmethod
    def get_franchise_list() -> list[str]:
        """Return list of franchises."""
        result = list(RunInfo.get_input_database_map())
        if 'shared' in result:
            result.remove('shared')
        return result

    @staticmethod
    def get_ics_database_prefix() -> str:
        """Return prefix of ICS database resources."""
        prefix = RunInfo.get_job_env('CDP_ENV_PREFIX')
        return prefix.replace('-', '_')

    @staticmethod
    def get_input_bucket_name_map() -> dict[str, str]:
        """Get mapping with the input database."""
        return RunInfo.get_job_env('CDP_ENV_INPUT_BUCKET_NAME_MAP')

    @staticmethod
    def get_input_bucket(franchise: str) -> str:
        """Return name of the input bucket."""
        input_bucket_name_map = RunInfo.get_input_bucket_name_map()
        if franchise not in input_bucket_name_map:
            raise ValueError('Invalid franchise')
        return input_bucket_name_map[franchise]

    @staticmethod
    def get_input_database_map() -> dict[str, str]:
        """Get mapping with the input database."""
        return RunInfo.get_job_env('CDP_ENV_INPUT_DATABASE_MAP')

    @staticmethod
    def get_input_database(franchise: str) -> str:
        """Return name of the input database with the raw csv files."""
        input_database_map = RunInfo.get_input_database_map()
        if franchise not in input_database_map:
            raise ValueError(f'Unknown franchise {franchise!r}!')
        return input_database_map[franchise]

    @staticmethod
    def get_preprocessing_database(franchise: str) -> str:
        """Return name of the preprocessing database with the raw csv files."""
        input_database_map = RunInfo.get_input_database_map()
        if franchise not in input_database_map:
            raise ValueError(f'Unknown franchise {franchise!r}!')
        prefix = RunInfo.get_ics_database_prefix()
        return f'{prefix}_01_preprocessing_database_{franchise}'

    @staticmethod
    def get_global_tables_database(franchise: str) -> str:
        """Return name of the preprocessing database with the raw csv files."""
        if franchise == 'shared':
            raise ValueError('There is no shared global tables database!')
        if franchise not in RunInfo.get_franchise_list():
            raise ValueError(f'Unknown franchise {franchise!r}!')
        prefix = RunInfo.get_ics_database_prefix()
        return f'{prefix}_b1_global_tables_processing_database_{franchise}'

    @staticmethod
    def get_storage_bucket() -> str:
        """Return name of the storage bucket."""
        return RunInfo.get_job_env('CDP_ENV_STORAGE_BUCKET_NAME')

    @staticmethod
    def get_storage_bucket_path() -> str:
        """Return name of the storage bucket."""
        return RunInfo.get_job_env('CDP_ENV_STORAGE_PATH')

    @staticmethod
    def get_storage_database() -> str:
        """Return name of the storage database."""
        return RunInfo.get_job_env('CDP_ENV_DATABASE_NAME')

    @staticmethod
    def get_athena_workspace() -> str:
        """Return name of the Athena workspace."""
        return RunInfo.get_job_env('CDP_ENV_WORKSPACE_NAME')

    @staticmethod
    def get_job_env(key: str) -> Any:
        """Get job environment information from the environment variables."""
        return json.loads(os.environ[key])
