# -*- coding: utf-8 -*-
"""Module with the configuration given to the lambda function."""

from typing import TypeAlias

from pydantic import AnyUrl
from pydantic_settings import BaseSettings
from task_config import TaskName
from utils import AnyPath

S3Url: TypeAlias = AnyUrl
DynamoDbTableName: TypeAlias = str


class LambdaConfig(BaseSettings, extra='forbid'):
    """Class with the settings given to the lambda function."""
    account_name: str
    allowed_tasks: list[TaskName]
    cdp_tools_wheel: S3Url
    config_file_dir: AnyPath
    preprocessing_database_name: str
    run_db_key: str
    run_db_table: DynamoDbTableName
    scope: str
    task_env: dict[str, str]
