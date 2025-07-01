# -*- coding: utf-8 -*-
"""This job starts the custom data processing."""

import argparse
import datetime
import json
import logging
import os
import runpy
import sys
import time
import zipfile
from dataclasses import asdict
from typing import Any, TypeAlias

import boto3

from cdp_tools import (
    apply_glue_config,
    get_deployed_glue_config,
    open_file_path,
)

CmdLineParameterName: TypeAlias = str


def parse_arguments(
        cmd_line_argv: list[str]) -> dict[CmdLineParameterName, str]:
    """Parse command line arguments into dictionary."""
    parser = argparse.ArgumentParser()
    for key in [arg for arg in cmd_line_argv if arg.startswith('--')]:
        parser.add_argument(key.split('=')[0], nargs='?', default=None)
    args = parser.parse_args(cmd_line_argv)
    return {key.lower(): value for key, value in vars(args).items()}


class CloudwatchHandler(logging.StreamHandler):
    """Python logging handler to write to CloudWatch."""

    def __init__(self,
                 log_group: str,
                 stream_name: str,
                 buffer_len: int = 5) -> None:
        self._buffer_len = buffer_len
        self._log_group = log_group
        self._stream_name = stream_name
        self._client = boto3.client('logs')
        self._client.create_log_stream(logGroupName=self._log_group,
                                       logStreamName=self._stream_name)
        self._buffer: list[dict[str, Any]] = []
        super().__init__()

    def flush(self):
        if not self._buffer:
            return super().flush()
        self._client.put_log_events(logGroupName=self._log_group,
                                    logStreamName=self._stream_name,
                                    logEvents=self._buffer)
        self._buffer.clear()
        return super().flush()

    def close(self):
        self.flush()
        return super().close()

    def emit(self, record):
        timestamp = int(round(time.time() * 1000))
        msg = self.format(record)
        self._buffer.append({
            'timestamp': timestamp,
            'message': msg,
        })
        if len(self._buffer) > self._buffer_len:
            self.flush()


def init_job(
    log_name: str, cmd_line_argv: list[str],
    parameters: list[CmdLineParameterName]
) -> tuple[logging.Logger, dict[CmdLineParameterName, str]]:
    """Parse command line arguments and create logger."""
    # Logging setup & job argument handling
    log_level = os.environ.get('CDP_LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s',
                        level=log_level)
    log = logging.getLogger(log_name)
    log.info('Starting %s', log_name)
    # Display command line arguments
    log_args = logging.getLogger(log_name + '.args')
    log_args.debug('Arguments: %r', cmd_line_argv)
    # Parse command line arguments and return config object
    args = parse_arguments(cmd_line_argv)
    if any((parameter not in args) for parameter in parameters):
        raise RuntimeError(f'Missing arguments: {parameters} {args}')
    return (log, args)


def _decompress_job(log: logging.Logger, archive_s3_path: str) -> None:
    """This decompresses the given job archive into the current directory."""
    log.info('Reading job archive from %r ...', archive_s3_path)
    with open_file_path(archive_s3_path) as file_obj:
        with zipfile.ZipFile(file_obj) as zip_file:
            zip_file.extractall()


def _run_script(log: logging.Logger, entry_point: str, args: list[str],
                kwargs: dict[str, str]) -> None:
    """This runs the script / function specified in the config file."""
    entry_point_parts = entry_point.split(':', 1)
    entry_point_file = entry_point_parts[0]
    entry_point_function = None
    if len(entry_point_parts) == 2:
        entry_point_function = entry_point_parts[1]
    # Run script
    try:
        if entry_point_function is None:
            log.info('Running script %r ...', entry_point_file)
            # Set command line arguments for raw scripts
            sys.argv = [entry_point_file] + args
            log.info('Arguments %s ...', repr(sys.argv))
            # Run the script as it is
            runpy.run_path(entry_point_file, run_name='__main__')
        else:
            log.info('Running function %r from %r ...', entry_point_function,
                     entry_point_file)
            sys.argv = [entry_point_file]
            namespace = runpy.run_path(entry_point_file, run_name='__cdp__')
            # Call method with specified parameters
            namespace[entry_point_function](*args, **kwargs)
    except SystemExit as ex:
        if ex.code != 0:
            log.exception('Non-zero exit code of CDP script')
            raise ex
    except Exception as ex:
        log.exception('Exception during CDP script')
        raise ex
    log.info('Task finished')


def _get_cloudwatch_handler(scope: str, task_log_group: str,
                            task_name: str) -> logging.Handler:
    """Get CloudWatch handler."""
    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp = now.isoformat().split('+')[0].replace(':', '-')
    return CloudwatchHandler(log_group=task_log_group,
                             stream_name=f'{scope}_{task_name}_{timestamp}')


def main(cmd_line_argv: list[str]) -> None:
    """Parse the arguments and run the preprocessing steps."""
    log, args = init_job('cdp', cmd_line_argv, [
        'config_lambda_arn',
        'scope',
        'task_log_group',
        'task_name',
        'user_task_config',
    ])
    log.addHandler(
        _get_cloudwatch_handler(args['scope'], args['task_log_group'],
                                args['task_name']))
    log.info('Running task wrapper for %s', args['task_name'])

    # Getting task configuration
    log.info('Getting task config')
    glue_config = get_deployed_glue_config(args['config_lambda_arn'],
                                           args['task_name'],
                                           args['user_task_config'])
    log.info('Using task config:\n%s',
             json.dumps(asdict(glue_config), indent=2, sort_keys=True))
    # Decompress job files
    # Allow to skip code decompression for local testing
    if not os.environ.get('CDP_NO_RETRIEVAL'):
        _decompress_job(log, glue_config.code_storage_path)
    # Apply task configuration
    apply_glue_config(log, glue_config)
    # Basic implementation for script execution
    _run_script(log, glue_config.entry_point, glue_config.arguments,
                glue_config.kwargs)


if __name__ == '__main__':
    main(sys.argv[1:])
