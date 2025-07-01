#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lambda function to process S3-upload-events."""

import datetime
import fnmatch
import json
import logging
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import ics_lambda
from ics.ics_boto_client_factory import BotoClientFactory
from ics.types import (
    DynamoDbTableName,
    S3Path,
    StrictBaseModel,
    StrictBaseSettings,
    TableName,
    WorkflowExecutionArn,
)
from ics.types.user_types import WorkflowInvocationSettings
from ics.types.workflow_types import UploadDBEntry
from pydantic import NonNegativeInt


class UploadTriggerSettings(StrictBaseModel):
    """Configuration for workflow invocations triggered by uploads."""
    #: File selection pattern (using Unix-style as implemented in `fnmatch`)
    file_selector: str
    #: Flag to ignore snowflake data files - while keeping the query id file
    ignore_snowflake_data_files: bool = True
    #: Settings for the workflow that will be executed if the selector matches
    workflow_settings: WorkflowInvocationSettings
    #: Flag that specifies that this workflow will not be executed directly
    check_only: bool = False

    def get_matching_paths(self, path_list: list[S3Path]) -> list[S3Path]:
        """This method checks if this entry was triggered."""
        selected_path_list = [
            path for path in path_list
            if fnmatch.fnmatch(path, self.file_selector)
        ]
        if not self.ignore_snowflake_data_files:
            return selected_path_list
        return [
            path for path in selected_path_list if ('/snowflake/' not in path)
            or path.endswith('last_query_id.parquet')
        ]


class ScheduledTriggerSettings(StrictBaseModel):
    """Configuration for workflow invocations triggered by uploads."""
    #: AWS CloudWatch schedule expression
    schedule_expression: str
    #: Settings for the workflow that will be executed if scheduled
    workflow_settings: WorkflowInvocationSettings


class UploadHandlerConfig(StrictBaseSettings):
    """Configuration for the upload handler."""
    upload_window_seconds: NonNegativeInt
    #: Name of the DynamoDB upload table
    upload_table_name: DynamoDbTableName
    #: List of upload trigger settings
    upload_triggers: list[UploadTriggerSettings]
    #: List of scheduled trigger settings
    scheduled_triggers: list[ScheduledTriggerSettings]


######################################################################
# Data Model Classes


def _format_workflow_name(value: str,
                          max_str_limit_len: int = 80,
                          **kwargs: dict[str, Any]) -> str:
    """Format the specified workflow name."""
    result = value.format(timestamp=time.strftime('%Y-%m-%d_%H-%M-%S'),
                          uuid=str(uuid4()),
                          **kwargs)
    return result[:max_str_limit_len]


def _iter_upload_paths_from_s3_event(
        event: dict[str, Any]) -> Iterator[S3Path]:
    """This method parses the S3 event and iterates the uploaded paths."""
    for record in event['Records']:
        object_key = record.get('s3', {}).get('object', {}).get('key')
        bucket_name = record.get('s3', {}).get('bucket', {}).get('name')
        if bucket_name and object_key:
            yield f's3://{bucket_name}/{object_key}'


def _iter_upload_paths_from_sns_event(
        event: dict[str, Any]) -> Iterator[S3Path]:
    """This method parses the SNS event and iterates the uploaded paths."""
    for record in event['Records']:
        s3_message_body = json.loads(record['Sns']['Message'])
        yield from _iter_upload_paths_from_s3_event(s3_message_body)


def _start_step_function(
        log: logging.Logger,
        workflow_settings: WorkflowInvocationSettings) -> WorkflowExecutionArn:
    """Starts the execution of the step function with the given parameters."""
    log.info('Starting workflow %r with arguments %r as %s',
             workflow_settings.arn, workflow_settings.parameters,
             workflow_settings.name)
    client = BotoClientFactory.get_sfn_client()
    response = client.start_execution(
        name=workflow_settings.name,
        stateMachineArn=workflow_settings.arn,
        input=workflow_settings.parameters,
    )
    log.debug('start_execution response: %s', response)
    return response['executionArn']


def _start_step_functions(
    log: logging.Logger, invocation_list: list[WorkflowInvocationSettings]
) -> list[WorkflowExecutionArn]:
    """Start multiple step functions and delay abort to the the end."""
    result = []
    error_list = []
    for workflow_settings in invocation_list:
        try:
            result.append(_start_step_function(log, workflow_settings))
        except Exception:
            log.exception('Error while starting workflow %s',
                          workflow_settings.name)
            error_list.append(workflow_settings)
    if error_list:
        msg = f'Unable to start workflows: {error_list}'
        raise RuntimeError(msg)
    return result


def _replace_invocation_parameters(result: WorkflowInvocationSettings,
                                   **kwargs: Any) -> None:
    """Modify workflow parameter dictionary by replacing "$" with the given
    value if the key ends with ".$".
    """
    # Wrap items in list as underlying dictionary can change its contents
    workflow_parameters = json.loads(result.parameters)
    for key, value in list(workflow_parameters.items()):
        if key.endswith('.$'):
            for kwargs_key, kwargs_value in list(kwargs.items()):
                if value == f'$.{kwargs_key}':
                    workflow_parameters.pop(key)
                    workflow_parameters[key[:-2]] = kwargs_value
    result.parameters = json.dumps(workflow_parameters)


def _get_invocation_list_for_uploads(
        config: UploadHandlerConfig,
        upload_path_list: list[S3Path]) -> list[WorkflowInvocationSettings]:
    """Get the triggered workflows for the given uploads.

    Check-only workflows are not executed directly, but their parameters
    are stored in a list, which can be accessed by other triggered step
    functions.
    """
    check_only_list: list[dict[str, Any]] = []
    invocation_list: list[WorkflowInvocationSettings] = []
    for upload_config in config.upload_triggers:
        matching_path_list = upload_config.get_matching_paths(upload_path_list)
        if not matching_path_list:
            continue
        _replace_invocation_parameters(upload_config.workflow_settings,
                                       matching_path_list=matching_path_list,
                                       upload_path_list=upload_path_list)
        workflow_name = upload_config.workflow_settings.name or '{uuid}'
        modified_workflow_dict = {
            'name': _format_workflow_name(workflow_name),
            'arn': upload_config.workflow_settings.arn,
            'parameters': upload_config.workflow_settings.parameters,
        }
        if upload_config.check_only:
            check_only_list.append(modified_workflow_dict)
        else:
            invocation_list.append(
                WorkflowInvocationSettings(**modified_workflow_dict))
    # Make the list of check-only workflows available to the triggered ones
    for workflow_settings in invocation_list:
        _replace_invocation_parameters(workflow_settings,
                                       check_only_workflows=check_only_list)
    return invocation_list


def _get_invocation_list_for_schedule(
        config: UploadHandlerConfig,
        trigger_schedule_expr: str) -> list[WorkflowInvocationSettings]:
    """Get the triggered workflows for the given schedule."""
    return [
        WorkflowInvocationSettings(
            name=_format_workflow_name(scheduled_config.workflow_settings.name
                                       or '{uuid}'),
            arn=scheduled_config.workflow_settings.arn,
            parameters=scheduled_config.workflow_settings.parameters,
        ) for scheduled_config in config.scheduled_triggers
        if scheduled_config.schedule_expression == trigger_schedule_expr
    ]


def _write_upload_db(table_name: TableName,
                     entries: list[UploadDBEntry]) -> None:
    """Write upload paths to the DynamoDB."""
    dynamodb = BotoClientFactory.get_dynamodb_resource()
    table = dynamodb.Table(table_name)
    with table.batch_writer() as batch:
        for entry in entries:
            # Turn timestamps into strings and store the entry
            batch.put_item(Item=json.loads(entry.json()))


def _select_upload_paths(
        upload_window_seconds: NonNegativeInt,
        upload_entry_list: list[UploadDBEntry]) -> list[S3Path]:
    """Select the upload paths for the workflow invocation."""
    if not upload_entry_list:
        return []
    current_time = datetime.datetime.now(datetime.timezone.utc)
    time_of_last_upload = max(entry.upload_time for entry in upload_entry_list)
    # Return all uploaded paths if no uploads happened after a certain time
    upload_window = datetime.timedelta(seconds=upload_window_seconds)
    if current_time - time_of_last_upload > upload_window:
        return sorted({entry.upload_path for entry in upload_entry_list})
    return []


def _scan_upload_db(table_name: TableName) -> list[UploadDBEntry]:
    """Read all entries from DynamoDB."""
    dynamodb = BotoClientFactory.get_dynamodb_resource()
    table = dynamodb.Table(table_name)
    response = table.scan()
    item_list = response['Items']
    while response.get('LastEvaluatedKey'):
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        item_list.extend(response['Items'])
    return [UploadDBEntry.model_validate(entry) for entry in item_list]


def _clean_upload_db(table_name: TableName,
                     upload_path_list: list[S3Path]) -> None:
    """Clean upload table."""
    dynamodb = BotoClientFactory.get_dynamodb_resource()
    table = dynamodb.Table(table_name)
    with table.batch_writer() as batch:
        for upload_path in upload_path_list:
            batch.delete_item(Key={'upload_path': upload_path})


def lambda_handler(event: dict[str, Any],
                   context: Any) -> list[WorkflowExecutionArn]:
    """Starts the execution of a step function if conditions are met.

    Returns:
        list[str]: The list of started workflow ARNs
    """
    del context
    log = ics_lambda.lambda_logging('workflow_trigger', event)
    config = UploadHandlerConfig()  # Load configuration from the environment
    log.info('Running with configuration: %r', config)

    if 'Records' in event:
        # Lambda was invoked by SNS topic - store uploaded paths in DynamoDB
        upload_time = datetime.datetime.now(datetime.timezone.utc)
        upload_path_list = list(_iter_upload_paths_from_sns_event(event))
        upload_entry_list = [
            UploadDBEntry(upload_path=upload_path, upload_time=upload_time)
            for upload_path in upload_path_list
        ]
        _write_upload_db(config.upload_table_name, upload_entry_list)
        log.info('Updated upload database with %r', upload_path_list)
        return ics_lambda.finish(
            log, [json.loads(entry.json()) for entry in upload_entry_list])

    if 'drain' in event:
        # Load previously stored upload entries
        upload_entry_list = _scan_upload_db(config.upload_table_name)
        upload_path_list = _select_upload_paths(config.upload_window_seconds,
                                                upload_entry_list)
        # Check which workflows should execute
        invocation_list = _get_invocation_list_for_uploads(
            config, upload_path_list)
        log.info('Uploads %r triggered %d workflows', upload_path_list,
                 len(invocation_list))
        # Start workflows
        result = _start_step_functions(log, invocation_list)
        # Remove uploaded paths from database
        _clean_upload_db(config.upload_table_name, upload_path_list)
        return ics_lambda.finish(log, result)

    if 'schedule_expression' in event:
        # Lambda was invoked via scheduled CloudWatch event
        trigger_schedule_expr = event['schedule_expression']
        invocation_list = _get_invocation_list_for_schedule(
            config, trigger_schedule_expr)
        log.info('Schedule %r triggered %d workflows', trigger_schedule_expr,
                 len(invocation_list))
        result = _start_step_functions(log, invocation_list)
        return ics_lambda.finish(log, result)

    msg = f'Invalid event! {event}'
    raise ValueError(msg)


if __name__ == '__main__':
    ics_lambda.run_local(lambda_handler)
