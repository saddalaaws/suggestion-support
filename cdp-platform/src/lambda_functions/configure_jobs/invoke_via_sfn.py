# -*- coding: utf-8 -*-
"""Module to handle the lambda function invocation via the Step Function."""
import copy
import json
from contextlib import contextmanager
from logging import Logger
from typing import Annotated, Any, Literal, Optional, TypeAlias

import boto3
from ics.ics_db import DBContext
from ics.ics_db_default import get_context
from ics.ics_frequency_base import FrequencyBase
from ics.ics_plugin import PluginLoader
from lambda_config import LambdaConfig
from pydantic import BaseModel, BeforeValidator, Field
from task_config import TaskConfig, TaskName, load_task_config
from user_config import UserTaskConfig
from utils import split_csl

JobType: TypeAlias = str
JobName: TypeAlias = str


class JobInfo(BaseModel, extra='forbid'):
    """Class with the CDP job settings."""
    additional_python_modules: str
    job_name: JobName
    task_name: TaskName
    user_task_config: UserTaskConfig


class SFNOutputEvent(BaseModel, extra='forbid'):
    """Class to store the output of the lambda function when invoked by the
    Step Function."""
    job_list: list[JobInfo]


class UserConfig(BaseModel, extra='forbid'):
    """Class with the config that can be specified in the step function."""
    comment: Optional[str] = Field(default='', alias='Comment')
    started_by: Optional[str] = Field(
        default='', alias='AWS_STEP_FUNCTIONS_STARTED_BY_EXECUTION_ID')

    check_schedule: Optional[bool] = None
    settings: Optional[dict[TaskName, UserTaskConfig]] = None
    tasks: Optional[Annotated[list[TaskName],
                              BeforeValidator(split_csl)]] = None
    update_run_db: bool = True

    def get_task_list(self) -> Optional[list[TaskName]]:
        """Get the tasks provided by the user."""
        # Check if user task information is provided
        if (self.settings is None) and (self.tasks is None):
            return None
        # Fill in empty defaults before returning the union
        user_settings: dict[TaskName, UserTaskConfig] = self.settings or {}
        user_tasks: list[TaskName] = self.tasks or []
        return list(set(user_tasks).union(user_settings.keys()))

    def get_check_schedule(self) -> bool:
        """Decide if the task schedule should be checked.

        check_schedule = False: Run tasks regardless of their run config
        check_schedule = True:  Run tasks according to their run config
        check_schedule = None:  If tasks are specified by the user, run
        them regardless of their run config If no tasks are specified by
        the user, run tasks according to their run config
        """
        if self.check_schedule is None:
            has_no_user_tasks = self.get_task_list() is None
            return has_no_user_tasks
        return self.check_schedule


class SFNPayload(BaseModel, extra='forbid'):
    """Class with the Lambda payload when invoked by the Step Function."""
    mode: Literal['get-sfn-jobs']
    job_name_map: dict[JobType, JobName]
    user_config: UserConfig

    def _get_task_candidates(self,
                             lambda_config: LambdaConfig) -> list[TaskName]:
        """Get the tasks that might be run."""
        user_tasks = self.user_config.get_task_list()
        if user_tasks is not None:
            if set(user_tasks).difference(lambda_config.allowed_tasks):
                raise ValueError(f'Invalid tasks selected: {user_tasks}')
            return user_tasks
        return lambda_config.allowed_tasks

    def _get_task_config_map(
            self, log: Logger, lambda_config: LambdaConfig,
            task_name_list: list[TaskName]) -> dict[TaskName, TaskConfig]:
        """Load map with the task configuration."""
        result = {}
        for task_name in task_name_list:
            task_config = load_task_config(log, lambda_config.config_file_dir,
                                           task_name)
            if task_config is not None:
                result[task_name] = task_config
        return result

    def _get_triggered_tasks(
            self, log: Logger, lambda_config: LambdaConfig,
            task_plugin_map: dict[TaskName, FrequencyBase]) -> list[TaskName]:
        """Get list of tasks that should be run according to their
        configuration."""
        result = []
        context = _get_db_context(lambda_config)
        with _get_run_db_table(lambda_config) as run_db_entry:
            run_db_entry_copy = copy.deepcopy(run_db_entry)
            for task_name, task_frequency_plugin in task_plugin_map.items():
                task_frequency_state = run_db_entry_copy.get(task_name, {})
                log.debug('Accessing stored task state',
                          json.dumps(task_frequency_state, indent=2))
                task_frequency_state['use_case_name'] = task_name
                # TODO(platform): Move use case access into correct plugins
                # 7101
                try:
                    if not task_frequency_plugin.trigger(
                            context, lambda_config.run_db_key,
                            copy.deepcopy(task_frequency_state)):
                        # Task was not triggered
                        log.info('Task %r was not triggered', task_name)
                        continue
                except Exception:
                    log.info('Task %r has a trigger issue!', task_name)
                    continue
                # Task was triggered
                log.info('Task %r was triggered', task_name)
                result.append(task_name)
                if not self.user_config.update_run_db:
                    continue
                # Reload trigger and store new state into the run DB
                task_frequency_state = task_frequency_plugin.reload_trigger(
                    context, lambda_config.run_db_key, task_frequency_state)
                log.debug('Writing new task state',
                          json.dumps(task_frequency_state, indent=2))
                run_db_entry_copy[task_name] = task_frequency_state
            # Transfer state into persistent entry
            run_db_entry.update(run_db_entry_copy)
        return result

    @staticmethod
    def _check_in_optional_list(value: str,
                                optional_list: Optional[list[str]],
                                default: bool = True) -> bool:
        """Checks if the value is in a list and returns the default if the list
        is not given."""
        if optional_list is None:
            return default
        return value in optional_list

    @classmethod
    def _check_run_config(cls, log: Logger, lambda_config: LambdaConfig,
                          task_name: TaskName,
                          task_config: TaskConfig) -> bool:
        """Check task configuration for enabled scope / environment."""
        if not cls._check_in_optional_list(lambda_config.scope,
                                           task_config.run.enabled_scopes):
            log.info('Task %r did not request to run for scope %r', task_name,
                     lambda_config.scope)
            return False
        if not cls._check_in_optional_list(
                lambda_config.account_name,
                task_config.run.enabled_account_names):
            log.info('Task %r did not request to run for account_name %r',
                     task_name, lambda_config.account_name)
            return False
        return True

    def _get_scheduled_tasks(
            self, log: Logger, lambda_config: LambdaConfig,
            task_config_map: dict[TaskName, TaskConfig]) -> list[TaskName]:
        """Get list of tasks that should be run according to their
        configuration."""
        # Filter out tasks which are neither selected by the user
        # nor configured to run by default
        task_plugin_map = {}
        plugin_loader = PluginLoader()
        is_user_specified_task = self.user_config.get_task_list() is not None
        for task_name, task_config in task_config_map.items():
            if not self._check_run_config(log, lambda_config, task_name,
                                          task_config):
                continue
            if not task_config.run.frequency:
                log.info('Task %r does not define a frequency plugin',
                         task_name)
                # This is just an informative note - it will fail below with
                # even more messages
            log.info('Loading frequency plugin: %s',
                     json.dumps(task_config.run.frequency, indent=2))
            try:
                task_frequency_plugin = plugin_loader.load(
                    task_config.run.frequency)
            except Exception:
                log.error('Unable to load frequency plugin for %r', task_name)
                continue
            if is_user_specified_task or task_config.run.default:
                task_plugin_map[task_name] = task_frequency_plugin
        return self._get_triggered_tasks(log, lambda_config, task_plugin_map)

    def _get_job_info(self, lambda_config: LambdaConfig, task_name: TaskName,
                      task_config: TaskConfig):
        """Construct the job information for the step function."""
        task_req_list = list(task_config.requirements)
        task_req_list.append(str(lambda_config.cdp_tools_wheel))
        user_settings = self.user_config.settings or {}
        user_task_config = user_settings.get(task_name, None)
        if user_task_config is None:
            user_task_config = UserTaskConfig()
        return JobInfo(
            additional_python_modules=','.join(task_req_list),
            job_name=self.job_name_map['python'],
            task_name=task_name,
            user_task_config=user_task_config,
        )

    def process(self, log: Logger,
                lambda_config: LambdaConfig) -> SFNOutputEvent:
        """Process event and return output event."""
        candidate_task_list = self._get_task_candidates(lambda_config)
        task_config_map = self._get_task_config_map(log, lambda_config,
                                                    candidate_task_list)
        if self.user_config.get_check_schedule():
            selected_task_list = self._get_scheduled_tasks(
                log, lambda_config, task_config_map)
        else:
            selected_task_list = list(task_config_map.keys())
        return SFNOutputEvent(job_list=[
            self._get_job_info(lambda_config, task_name,
                               task_config_map[task_name])
            for task_name in sorted(selected_task_list)
        ])


def _get_db_context(lambda_config: LambdaConfig) -> DBContext:
    """Create a configured DB context."""
    source_database_map = {None: lambda_config.preprocessing_database_name}
    return get_context(source_databases=source_database_map)


@contextmanager
def _get_run_db_table(lambda_config: LambdaConfig) -> Any:
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(lambda_config.run_db_table)
    try:
        prev_run_query = table.get_item(
            Key={'workflow': lambda_config.run_db_key}, ConsistentRead=True)
    except Exception as ex:
        msg = (f'Unable to access {lambda_config.run_db_key!r} '
               f'in table {lambda_config.run_db_table!r}')
        raise ValueError(msg) from ex
    workflow_info = prev_run_query.get('Item', {})
    try:
        yield workflow_info
    finally:
        workflow_info.setdefault('workflow', lambda_config.run_db_key)
        table.put_item(Item=workflow_info)
