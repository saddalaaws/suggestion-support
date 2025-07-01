# -*- coding: utf-8 -*-
"""This module contains the task configuration models."""
from contextlib import suppress
from logging import Logger
from typing import Any, Optional, TypeAlias

from pydantic import BaseModel, Field
from utils import AnyPath, load_config

TaskName: TypeAlias = str
TaskArgument: TypeAlias = str
TaskEnvironmentVariableName: TypeAlias = str
TaskEnvironmentVariableValue: TypeAlias = str
TaskRequirement: TypeAlias = str

###############################################################################
# This needs to stay in sync with
# src/build/package_task.py


class TaskRunConfig(BaseModel, extra='forbid'):
    """Class to store the run configuration of the task."""
    default: bool = False
    enabled_account_names: Optional[list[str]] = None
    enabled_scopes: Optional[list[str]] = None
    #: References an ICS plugin
    frequency: dict[str, Any] = Field(default_factory=dict)


class TaskConfig(BaseModel, extra='forbid'):
    """Class to store the standardized task configuration."""
    arguments: list[TaskArgument] = Field(default_factory=list)
    cwd: str = '.'
    entry_point: str = 'script.py'
    environment: dict[TaskEnvironmentVariableName,
                      TaskEnvironmentVariableValue] = Field(
                          default_factory=dict)
    kwargs: dict[str, str] = Field(default_factory=dict)
    python_lib_dirs: list[str] = Field(default_factory=list)
    requirements: list[TaskRequirement] = Field(default_factory=list)
    run: TaskRunConfig = TaskRunConfig()


###############################################################################


def load_task_config(log: Logger, config_file_dir: AnyPath,
                     task_name: TaskName) -> Optional[TaskConfig]:
    """Load task configuration."""
    task_config_path = f'{config_file_dir}/{task_name}.json'
    log.info('Loading config file for task %r from %r', task_name,
             task_config_path)
    task_config_dict = None
    with suppress(Exception):
        task_config_dict = load_config(task_config_path)
    if task_config_dict is None:
        log.warning('Unable to load config file %r', task_config_path)
        return None
    # Check validity of config file content
    try:
        return TaskConfig.model_validate(task_config_dict)
    except Exception:
        log.exception('Unable to parse config file %r', task_config_path)
    return None
