#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Module to generate Terraform s3 backend."""

import argparse
import functools
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# This `dataclass` has an identical implementation in other repositories!
# Please keep them in sync!
@dataclass(frozen=True)
class TFStateConfig:
    """Container with settings for the Terraform backend."""
    bucket_name: str
    key_arn: str
    region: str
    workspace_key_prefix: str
    aws_profile: Optional[str] = None
    role_arn: Optional[str] = None

    def get_backend_config(self) -> str:
        """Terraform S3 backend template in JSON form."""
        s3_backend_config = {
            'region': self.region,
            'bucket': self.bucket_name,
            'use_lockfile': True,
            'encrypt': True,
            'kms_key_id': self.key_arn,
            'key': 'default',
            'workspace_key_prefix': self.workspace_key_prefix
        }
        if self.aws_profile:
            s3_backend_config['profile'] = self.aws_profile
        if self.role_arn:
            s3_backend_config['assume_role'] = {'role_arn': self.role_arn}
        backend_config = {'terraform': {'backend': {'s3': s3_backend_config}}}
        return json.dumps(backend_config, indent=4, sort_keys=True) + '\n'

    @classmethod
    def get_backend_config_from_env(cls) -> str:
        """Initializes Terraform backend configuration."""
        config = TFStateConfig(
            bucket_name=json.loads(os.environ['TF_STATE_BUCKET_NAME']),
            key_arn=json.loads(os.environ['TF_STATE_KEY_ARN']),
            region=json.loads(os.environ['TF_STATE_REGION']),
            role_arn=json.loads(os.environ['TF_STATE_ROLE_ARN']),
            workspace_key_prefix=os.environ['TF_STATE_WORKSPACE_KEY_PREFIX'],
        )
        return config.get_backend_config()

    @staticmethod
    @functools.cache
    def _get_tf_state_setting(project: str, name: str) -> str:
        session = __import__('boto3').Session()
        client = session.client('ssm')
        path = f'/devops/{project}/terraform-state/{name}'
        response = client.get_parameter(Name=path, WithDecryption=True)
        return json.loads(response['Parameter']['Value'])

    @classmethod
    def get_backend_config_from_ssm(cls, project: str,
                                    workspace_key_prefix: str) -> str:
        """Interpolates Terraform backend template and returns Terraform
        backend as JSON.
        """
        config = TFStateConfig(
            aws_profile='ics_devops',
            bucket_name=cls._get_tf_state_setting(project, 'bucket_name'),
            key_arn=cls._get_tf_state_setting(project, 'key_arn'),
            region=cls._get_tf_state_setting(project, 'region'),
            workspace_key_prefix=workspace_key_prefix,
        )
        return config.get_backend_config()


def _write_single_file_from_env(backend_file_path: Path) -> None:
    backend_file_path = Path(backend_file_path)
    backend_str = TFStateConfig.get_backend_config_from_env()
    backend_file_path.write_text(backend_str, encoding='utf-8')


def _rewrite_all_matching_files_from_ssm(root_path: Path,
                                         get_project: Callable,
                                         match_pattern: str) -> None:
    for backend_file_path in sorted(root_path.rglob(match_pattern)):
        sys.stdout.write(f'{backend_file_path}\n')
        project = get_project(backend_file_path)
        rel_dir_path = backend_file_path.relative_to(root_path).parent
        workspace_key_prefix = rel_dir_path.as_posix()
        if workspace_key_prefix.endswith('-cleanup'):
            raw_name = workspace_key_prefix.split('-', 1)[-1]
            match_name = raw_name.removesuffix('-cleanup')
            folder_name = next(iter(root_path.rglob(f'*{match_name}')))
            workspace_key_prefix = folder_name.name
        backend_str = TFStateConfig.get_backend_config_from_ssm(
            project=project, workspace_key_prefix=workspace_key_prefix)
        backend_file_path.write_text(backend_str, encoding='utf-8')


def main() -> None:
    """Main function of the Terraform backend generation module."""
    parser = argparse.ArgumentParser()
    parser.add_argument('tf_backend_file_path',
                        nargs='?',
                        help='Write path for Terraform backend config file.')
    args = parser.parse_args()
    if args.tf_backend_file_path:
        _write_single_file_from_env(args.tf_backend_file_path)
    else:
        script_folder = Path(__file__).absolute().parent
        repo_name = script_folder.parent.parent.name
        if repo_name.startswith('devops-pipeline-app'):
            root_path = script_folder

            def get_project(backend_file_path) -> str:
                return backend_file_path.parent.parent.name.split('-')[-1]
        elif repo_name.startswith('devops-pipeline-meta'):
            root_path = script_folder

            def get_project(backend_file_path) -> str:
                del backend_file_path
                return 'meta'
        elif repo_name.endswith('-platform'):
            root_path = script_folder

            def get_project(backend_file_path) -> str:
                del backend_file_path
                return 'cdp'
        else:
            root_path = script_folder.parent / 'infrastructure'

            def get_project(backend_file_path) -> str:
                del backend_file_path
                return repo_name.split('-')[0]

        _rewrite_all_matching_files_from_ssm(
            root_path, get_project, match_pattern='LOCAL_backend.tf.json')


if __name__ == '__main__':
    main()
