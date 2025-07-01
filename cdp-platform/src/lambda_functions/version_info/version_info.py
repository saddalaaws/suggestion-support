# -*- coding: utf-8 -*-
"""Print version information of installed libraries."""

import argparse
import datetime
import json
import logging
import os
import socket
import ssl
import sys
import urllib.request
from contextlib import suppress
from typing import Any, Dict, List

import boto3
import pkg_resources
from botocore.client import Config

with suppress(Exception):
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from pyspark.context import SparkContext


def _test_logging() -> None:
    timestamp = datetime.datetime.now().isoformat()
    sys.stdout.write(f'[{timestamp}] <stdout>\n')
    sys.stderr.write(f'[{timestamp}] <stderr>\n')
    logging.getLogger().info('[%s] <pre|info>', timestamp)
    logging.getLogger().error('[%s] <pre|error>', timestamp)
    logging.getLogger('app').info('[%s] <pre|app:info>', timestamp)
    logging.getLogger('app').error('[%s] <pre|app:error>', timestamp)
    logging.basicConfig(level=logging.INFO)
    logging.getLogger().info('[%s] <post|info>', timestamp)
    logging.getLogger().error('[%s] <post|error>', timestamp)
    logging.getLogger('app').info('[%s] <post|app:info>', timestamp)
    logging.getLogger('app').error('[%s] <post|app:error>', timestamp)


def _print_credential_info() -> None:
    print(boto3.Session().get_credentials().method)
    print()


def _print_python_version() -> None:
    version_str = '.'.join(map(str, sys.version_info[:3]))
    print(f'Installed python: {version_str}')
    print()


def _print_installed_packages() -> None:
    print('Installed packages')
    print('~~~~~~~~~~~~~~~~~~')
    package_list = pkg_resources.working_set
    for package in sorted(package_list, key=lambda entry: entry.key):
        print(f' * {package.key}=={package.version}')
    print()


def _print_env() -> None:
    print('Environment variables:')
    for key in os.environ:
        print(f'{key} = {os.environ[key]}')
    print()

    print('Current directory:')
    print(os.listdir('.'))
    print()

    print('Root directory:')
    print(os.listdir('/'))
    print()


def _print_network() -> None:
    print('Host name:')
    print(socket.getfqdn())
    print()

    print('Interfaces:')
    print(socket.if_nameindex())
    print()


def _get_url_json(url: str, timeout: int = 2, verify: bool = True) -> Any:
    kwargs: dict[str, Any] = {}
    if not verify:
        context = getattr(ssl, '_create_unverified_context')()
        kwargs['context'] = context
    if url.startswith('file:'):
        return None
    try:
        with urllib.request.urlopen(  # noqa: S310
                url,
                timeout=timeout,
                **kwargs,
        ) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except socket.timeout:
        return None


def _test_internet_connection() -> None:
    print('Network check')
    try:
        print(_get_url_json('https://54.166.148.227/get', verify=False))
    except Exception as ex:
        print(f'failed: {ex}')
    try:
        print(_get_url_json('https://httpbin.org/get', ))
    except Exception as ex:
        print(f'failed: {ex}')
    print()


def _test_vpc_endpoints(test_layers: List[str], test_bucket: str) -> None:
    config = Config(connect_timeout=2, read_timeout=2)

    print('Testing DynamoDB:')
    try:
        dynamodb_client = boto3.client('dynamodb', config=config)
        response = dynamodb_client.describe_limits()
        response.pop('ResponseMetadata', None)
        print(response)
    except Exception as ex:
        print(f'failed: {ex}')
    print()

    print('Testing Lambda endpoint:')
    try:
        lambda_client = boto3.client('lambda', config=config)
        response = lambda_client.list_layer_versions(
            LayerName=test_layers[0].rsplit(':', 1)[0])
        print(response['LayerVersions'])
    except Exception as ex:
        print(f'failed: {ex}')
    print()

    print('Testing S3:')
    try:
        s3_client = boto3.client('s3', config=config)
        response = s3_client.get_bucket_website(Bucket=test_bucket)
        response.pop('ResponseMetadata', None)
        print(response)
    except Exception as ex:
        print(f'failed: {ex}')
    print()


def _test_glue(args: Dict[str, str]) -> None:
    glue_context = GlueContext(SparkContext())
    job = Job(glue_context)
    job.init(args['job_name'], args)


def _parse_args() -> dict[str, str]:
    """Parse command line arguments into dictionary."""
    print(f'Job arguments: {sys.argv!r}')
    cmd_line_argv = sys.argv[1:]
    parser = argparse.ArgumentParser()
    for key in [arg for arg in cmd_line_argv if arg.startswith('--')]:
        parser.add_argument(key.split('=')[0], nargs='?', default=None)
    args = parser.parse_args(cmd_line_argv)
    result = {key.lower(): value for key, value in vars(args).items()}
    print(f'Parsed job arguments: {result}')
    return result


def _get_arg(args: Dict[str, str], key: str) -> str:
    return args.get(key, os.environ.get(key, ''))


def _test_assume_role() -> None:
    raw_client = boto3.client('sts')
    print(f'Identity: {raw_client.get_caller_identity()}')
    assumed_role_arn = raw_client.get_caller_identity()['Arn']
    role_arn = assumed_role_arn.replace(':sts:', ':iam:').replace(
        ':assumed-role/', ':role/').rsplit('/', 1)[0]
    policy = {
        'Version':
        '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Action': 'sts:GetCallerIdentity',
                'Resource': '*',
            },
        ]
    }
    del policy
    tmp = raw_client.assume_role(RoleArn=role_arn, RoleSessionName='test')
    os.environ['AWS_ACCESS_KEY_ID'] = tmp['Credentials']['AccessKeyId']
    os.environ['AWS_SECRET_ACCESS_KEY'] = tmp['Credentials']['SecretAccessKey']
    os.environ['AWS_SESSION_TOKEN'] = tmp['Credentials']['SessionToken']
    boto3.DEFAULT_SESSION = None
    new_client = boto3.client('sts')
    print(f'Identity: {new_client.get_caller_identity()}')
    print()


def main() -> None:
    """Main function to show installed libraries."""
    _test_logging()
    _print_credential_info()
    _print_python_version()
    _print_installed_packages()
    _print_env()
    _print_network()

    args = _parse_args()
    mode = args.get('mode', 'script')
    if mode == 'error':
        sys.exit(1)
    if mode != 'script':
        _test_glue(args)

    _print_python_version()
    _print_installed_packages()
    _print_env()
    _print_network()
    _test_internet_connection()
    try:
        test_layers = json.loads(_get_arg(args, 'test_layers'))
        _test_vpc_endpoints(test_layers, _get_arg(args, 'test_bucket'))
    except Exception:
        logging.exception('Unable to test VPC endpoint')
    _test_assume_role()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handler for lambda."""
    del event
    del context
    main()
    return {}


if __name__ == '__main__':
    main()
