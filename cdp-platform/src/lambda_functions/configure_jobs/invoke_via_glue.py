# -*- coding: utf-8 -*-
"""Module to handle the Lambda function invocation via the Glue job."""

from dataclasses import asdict
from logging import Logger
from typing import Any, Literal

from lambda_config import LambdaConfig
from pydantic import BaseModel
from task_config import TaskName, load_task_config
from user_config import UserTaskConfig

from cdp_tools import GlueConfig


class DeployedGluePayload(BaseModel, extra='forbid'):
    """Class with the Lambda payload when invoked by the Glue job."""
    mode: Literal['get-deployed-glue-config']
    task_name: TaskName
    user_task_config: UserTaskConfig

    def process(self, log: Logger,
                lambda_config: LambdaConfig) -> dict[str, Any]:
        """Get Task parameters."""
        task_config = load_task_config(log, lambda_config.config_file_dir,
                                       self.task_name)
        if task_config is None:
            error_msg = f'Unable to load config file for {self.task_name!r}'
            raise RuntimeError(error_msg)
        combined_config = self.user_task_config.combine(
            default_arguments=task_config.arguments,
            default_environment=task_config.environment,
            default_kwargs=task_config.kwargs,
        )
        environment = combined_config.environment
        environment.update(lambda_config.task_env)
        code_storage_path = (
            f'{lambda_config.config_file_dir}/{self.task_name}.zip')
        return asdict(
            GlueConfig(
                arguments=combined_config.arguments,
                cwd=task_config.cwd,
                code_storage_path=code_storage_path,
                entry_point=task_config.entry_point,
                environment=environment,
                kwargs=combined_config.kwargs,
                python_lib_dirs=task_config.python_lib_dirs,
            ))


class BasicGluePayload(BaseModel, extra='forbid'):
    """Class with the Lambda payload when invoked by the Glue job."""
    mode: Literal['get-basic-glue-config']

    def process(self, log: Logger,
                lambda_config: LambdaConfig) -> dict[str, Any]:
        """Get Task parameters."""
        log.info('Return basic Glue parameters')
        return asdict(
            GlueConfig(
                arguments=[],
                cwd='.',
                code_storage_path='',
                entry_point='',
                environment=lambda_config.task_env,
                kwargs={},
                python_lib_dirs=[],
            ))
