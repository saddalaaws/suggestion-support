#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lambda function to parse the errors from the Step Function."""

import copy
import json
import urllib.parse
from collections.abc import Iterator
from contextlib import suppress
from datetime import datetime, timedelta
from logging import Logger
from typing import Annotated, Any, Optional

import ics_lambda
from ics.connectors.teams import send_templated_adaptive_card
from ics.ics_boto_client_factory import BotoClientFactory, auto_paginate
from ics.ics_utils import CloudTrailIterator
from ics.types import (
    SecretArn,
    StepFunctionExecutionArn,
    StepFunctionName,
    StrictBaseModel,
)
from ics.types.user_types import WorkflowSettings
from pydantic import EmailStr, Field, StringConstraints


class StepFunctionStartInfo(StrictBaseModel):
    """Information container about the user who triggered a step function."""
    start_time: Optional[datetime] = None
    user_email: Optional[EmailStr] = None
    user_name: str = 'Team'


class StepFunctionErrorParserParameters(StrictBaseModel):
    """Information container with the step function information."""
    execution_arn: StepFunctionExecutionArn
    execution_start_time: datetime
    sfn_result: Any
    workflow_description: str
    workflow_name: StepFunctionName
    enable_user_discovery: bool = True
    teams_secret_arn: Optional[SecretArn] = None
    teams_channel: Optional[str] = None

    def describe(self) -> str:
        """Describe workflow."""
        return f'{self.workflow_description} {self.workflow_name!r}'


class ErrorParseResult(StrictBaseModel):
    """Information container with the result of the error parser function."""
    create_bug_tickets: bool = False
    message: Annotated[str, StringConstraints(strip_whitespace=True)]
    message_attributes: dict[str, dict[str, str]] = Field(default_factory=dict)
    notify: bool = True
    success: bool = False
    subject: Annotated[str, StringConstraints(strip_whitespace=True)]


def _format_json(value: Any) -> str:
    """Format json."""
    return json.dumps(value, indent=2, sort_keys=True)


def _encode_aws_style(value: str) -> str:
    """Encode URLs AWS-style."""
    value = urllib.parse.quote(value, safe='')
    return urllib.parse.quote(value).replace('%', '$')


def _get_sfn_execution_url(aws_region: str,
                           execution_arn: StepFunctionExecutionArn) -> str:
    """Get URL to step function execution log."""
    return (f'https://{aws_region}.console.aws.amazon.com/states/home?'
            f'region={aws_region}#/executions/details/{execution_arn}')


def _get_log_group_url(aws_region: str, log_group: str) -> str:
    """Get URL to a log group."""
    log_group = _encode_aws_style(log_group)
    return (f'https://{aws_region}.console.aws.amazon.com/cloudwatch/home?'
            f'region={aws_region}#logsV2:log-groups/log-group/{log_group}')


def _get_log_stream_url(aws_region: str, log_group: str,
                        log_stream: str) -> str:
    """Get URL to a log stream."""
    log_group_url = _get_log_group_url(aws_region, log_group)
    return f'{log_group_url}/log-events/{log_stream}'


def _get_glue_job_run_url(aws_region: str, job_name: str,
                          job_run_id: str) -> str:
    """Get URL to a glue job run."""
    return (f'https://{aws_region}.console.aws.amazon.com/gluestudio/home?'
            f'region={aws_region}#/job/{job_name}/run/{job_run_id}')


class MessageBase:
    """Base class for messages."""

    def __init__(self, template: ErrorParseResult, tags: dict[str, str],
                 recipient_name: str) -> None:
        # Set template and message attributes
        self._template = template.model_copy(deep=True)
        for key, value in tags.items():
            self._template.message_attributes[key] = {
                'DataType': 'String',
                'StringValue': str(value),
            }
        self._recipient_name = recipient_name
        self._result = None
        self.set_frame("""
Dear {recipient_name},

{message}

--
iConnect Suggestions Workflow Notification""")

    def set_frame(self, frame_message: str = '{message}') -> None:
        """Set the framing message."""
        template_copy = self._template.model_copy()
        template_copy.message = frame_message.format(
            recipient_name=self._recipient_name,
            message=self._template.message).strip()
        self._result = template_copy

    def __str__(self) -> str:
        return f'{self.__class__.__name__}({self._result})'

    def get_result(self) -> ErrorParseResult:
        """Get error parse result."""
        if self._result is None:
            msg = 'No frame was set!'
            raise RuntimeError(msg)
        return self._result


class SFNMalformedResultError(MessageBase):
    """Message about a malformed step function result."""

    def __init__(self, event: Any, ex: Exception) -> None:
        template = ErrorParseResult(
            subject='Malformed error information',
            message=(f'Input event: {_format_json(event)}\n'
                     f'Exception: {ex!s}\n'),
        )
        super().__init__(template, {}, StepFunctionStartInfo().user_name)


class MessageWithRecipient(MessageBase):
    """Base class for messages with recipients."""

    def __init__(self, template: ErrorParseResult, tags: dict[str, str],
                 user_info: StepFunctionStartInfo,
                 err_input: StepFunctionErrorParserParameters) -> None:
        if user_info.user_email is not None:
            tags.setdefault('recipient_mail', user_info.user_email)
        self.workflow_name = err_input.workflow_name
        self.execution_start_time = err_input.execution_start_time
        super().__init__(template=template,
                         tags=tags,
                         recipient_name=user_info.user_name)


class SFNErrorAnalysisFailed(MessageWithRecipient):
    """Message about an incomprehensible step function result."""

    def __init__(self, err_input: StepFunctionErrorParserParameters,
                 user_info: StepFunctionStartInfo, ex: Exception) -> None:
        template = ErrorParseResult(
            subject=f"""
{err_input.workflow_name}: Step Function error analysis failed""",
            message=f"""
{err_input.describe()} was unable to parse the step function result!
This should never happen. Please inform the platform team!

{ex!s}
{_format_json(err_input.sfn_result)}""",
        )
        super().__init__(template, {}, user_info, err_input)


class SFNSuccessful(MessageWithRecipient):
    """Message about a successful step function."""

    def __init__(self, err_input: StepFunctionErrorParserParameters,
                 user_info: StepFunctionStartInfo) -> None:
        template = ErrorParseResult(
            subject=f'{err_input.workflow_name}: Successful run',
            message=f"""{err_input.describe()} has successfully completed.

{self._get_additional_infos(err_input.sfn_result)}""",
            notify=False,
            success=True,
        )
        super().__init__(template, {}, user_info, err_input)

    def _get_additional_infos(self, sfn_result: Any) -> str:
        """Get additional information from the input event."""
        if 'use_case_name_list' in sfn_result:
            workflow_info = WorkflowSettings.model_validate(sfn_result)
            return ('The following use cases were processed: ' +
                    ','.join(sorted(workflow_info.use_case_name_list)))
        return ''


class SFNFailed(MessageWithRecipient):
    """Message about a failing step function."""

    def __init__(self, log: Logger,
                 err_input: StepFunctionErrorParserParameters,
                 user_info: StepFunctionStartInfo, err_details: Any) -> None:
        self._log = log
        self._tags: dict[str, str] = {}
        self._aws_region = err_input.execution_arn.split(':')[3]
        self._execution_history = self._get_execution_history(
            err_input.execution_arn)
        self.create_bug_tickets = self._get_create_bug_tickets_param()
        execution_log_url = _get_sfn_execution_url(self._aws_region,
                                                   err_input.execution_arn)
        template = ErrorParseResult(
            subject=f'{err_input.workflow_name}: Failed',
            message=f"""{err_input.describe()} has failed.

[Execution log]({execution_log_url})

{self._get_additional_infos(err_details)}""",
        )
        super().__init__(template, self._tags, user_info, err_input)

    def _get_additional_infos(self, err_details: Any) -> str:
        if 'error_summary' in err_details:
            err_iter = self._parse_collected_errors(
                err_details['error_summary'])
            return ''.join(entry + '\n' for entry in err_iter).strip()
        if 'Cause' in err_details:
            return self._parse_single_error(json.loads(err_details['Cause']))
        return ''

    def _get_execution_history(self, execution_arn: str) -> list[Any]:
        try:
            return list(
                auto_paginate(BotoClientFactory.get_sfn_client(),
                              'get_execution_history',
                              'events',
                              executionArn=execution_arn,
                              reverseOrder=False,
                              includeExecutionData=False))
        except Exception:
            self._log.exception('Unable to query execution history')
            return []

    def _get_create_bug_tickets_param(self) -> bool:
        for entry in self._execution_history:
            with suppress(Exception):
                param_str = entry['taskScheduledEventDetails']['parameters']
                return bool(json.loads(param_str)['create_bug_tickets'])
        return False

    def _parse_collected_errors(self, err_summary: Any) -> Iterator[str]:
        for name, err_list in err_summary.items():
            yield ''
            yield f'# **{name.title()}**'
            yield ''
            for err_info in err_list:
                yield f'*{err_info["item"]}*'
                yield ''
                yield self._parse_single_error(err_info['error'])
                yield ''

    def _parse_single_error(self, err_cause: Any) -> str:
        if 'GlueVersion' in err_cause:
            return self._parse_glue_error(err_cause)
        if 'stackTrace' in err_cause:
            return self._parse_lambda_error(err_cause)
        return _format_json(err_cause)

    def _get_first_failing_lambda(self) -> tuple[Optional[str], Optional[str]]:
        # Build execution graph
        id_to_entry_map = {}
        for entry in self._execution_history:
            id_to_entry_map[entry['id']] = entry
        # Find first failing entry - and trace back to the scheduling event
        for entry in self._execution_history:
            if 'Failed' in entry['type']:
                while 'Scheduled' not in entry['type']:
                    entry = id_to_entry_map[entry['previousEventId']]
                param_json = entry['taskScheduledEventDetails']['parameters']
                # Parse ARN
                name = json.loads(param_json)['FunctionName'].split(':')[-1]
                # Determine step name
                while 'Entered' not in entry['type']:
                    entry = id_to_entry_map[entry['previousEventId']]
                state_name = entry['stateEnteredEventDetails']['name']
                return f'{name!r}', f'step {state_name!r} -'
        return None, None

    def _parse_lambda_error(self, err_cause: Any) -> str:
        err_cause['errorMessage'] = self._parse_msg(err_cause['errorMessage'])
        lambda_fun_name, state_name = None, None
        if self._execution_history is not None:
            lambda_fun_name, state_name = self._get_first_failing_lambda()
        result = ' '.join(
            entry for entry in
            ['Error in', state_name, 'lambda function', lambda_fun_name]
            if entry)
        result += ':\n\n'
        result += f'  {err_cause["errorType"]}: {err_cause["errorMessage"]}\n'
        result += '\n' + ''.join(err_cause['stackTrace'])
        return result

    def _parse_glue_error_stacktrace(self, log_group: str,
                                     log_stream: str) -> Optional[str]:
        client = BotoClientFactory.get_cloudwatch_logs_client()
        for entry in auto_paginate(client,
                                   'filter_log_events',
                                   'events',
                                   logGroupName=log_group,
                                   logStreamNames=[log_stream]):
            message = entry['message']
            if 'GlueETLJobExceptionEvent' in message:
                try:
                    error_json = message.split('[Glue Exception Analysis]')[1]
                    result = json.loads(error_json)
                    return result['Failure Reason']
                except Exception:
                    self._log.exception('Unexpected exception analysis format')
        return None

    def _parse_glue_error(self, err_cause: Any) -> str:
        err_cause['ErrorMessage'] = self._parse_msg(err_cause['ErrorMessage'])
        full_error_message = self._parse_glue_error_stacktrace(
            err_cause['LogGroupName'] + '/error', err_cause['Id'])
        full_error_message = full_error_message or ''
        full_error_message = ''.join(
            [f'    {line}\n\n' for line in full_error_message.splitlines()])
        err_cause['DetailedErrorMessage'] = full_error_message
        err_cause['glue_job_url'] = _get_glue_job_run_url(
            self._aws_region, err_cause['JobName'], err_cause['Id'])
        err_cause['glue_job_log_url_output'] = _get_log_stream_url(
            self._aws_region, err_cause['LogGroupName'] + '/output',
            err_cause['Id'])
        err_cause['glue_job_log_url_error'] = _get_log_stream_url(
            self._aws_region, err_cause['LogGroupName'] + '/error',
            err_cause['Id'])
        err_cause['ExecutionTimeStr'] = str(
            timedelta(seconds=err_cause['ExecutionTime']))
        template = """
Error in glue job {JobName!r} after {ExecutionTimeStr} runtime:

    **{ErrorMessage}**

{DetailedErrorMessage}

   - [Run overview]( {glue_job_url} )
   - [Output log]( {glue_job_log_url_output} )
   - [Runtime log]( {glue_job_log_url_error} )
""".strip()
        return template.format(**err_cause)

    def _parse_msg(self, err_msg: str) -> str:
        """Process exception message."""
        if err_msg.startswith('AthenaQueryError'):
            # Reduce clutter in Athena exceptions
            marker = 'You may need to manually clean the data at location'
            return err_msg.split(marker, 1)[0].strip() + '"'
        return err_msg


def _get_sfn_user(
    current_execution_arn: StepFunctionExecutionArn,
    execution_start_time: datetime,
) -> StepFunctionStartInfo:
    """This method queries CloudTrail about the Step Function with the given
    execution ID.

    It returns the user / email of the user who started the workflow and
    the time when the Step Function was started.
    """
    sfn_events = CloudTrailIterator([{
        'AttributeKey': 'EventName',
        'AttributeValue': 'StartExecution'
    }])
    start_time = execution_start_time - timedelta(minutes=1)
    for event in sfn_events.iter_unique_events(timeout=timedelta(minutes=10),
                                               start_time=start_time):
        execution_arn = event['responseElements']['executionArn']
        if execution_arn == current_execution_arn:
            principal_id = event['userIdentity']['principalId'].lower()
            principal_id = principal_id.replace('sadm-', '')
            user_email = principal_id.split(':')[-1]
            return StepFunctionStartInfo(user_name=user_email.split('@')[0],
                                         user_email=user_email,
                                         start_time=event['eventTime'])
    return StepFunctionStartInfo()


def _handle_event(log: Logger, event: dict[str, Any]) -> MessageBase:
    """Main error parser."""
    # Parse lambda input
    try:
        err_input = StepFunctionErrorParserParameters.model_validate(event)
    except Exception as ex:
        result: MessageBase = SFNMalformedResultError(event, ex)
        log.exception(result.get_result().subject)
        return result

    # Find out who started the step function
    user_info = StepFunctionStartInfo()
    if err_input.enable_user_discovery:
        try:
            user_info = _get_sfn_user(err_input.execution_arn,
                                      err_input.execution_start_time)
        except Exception:
            log.exception('Error while reading user information!')

    # Analyze step function result
    try:
        if 'error' in err_input.sfn_result:
            return SFNFailed(log, err_input, user_info,
                             err_input.sfn_result.pop('error'))
        return SFNSuccessful(err_input, user_info)
    except Exception as ex:
        result = SFNErrorAnalysisFailed(err_input, user_info, ex)
        log.exception(result.get_result().subject)
        return result


def _notify_teams(log: Logger, message: MessageBase,
                  teams_secret_arn: SecretArn, teams_channel: str) -> None:
    """Try to notify teams."""
    # Remove framing message from result
    message = copy.deepcopy(message)
    message.set_frame()
    result = message.get_result()
    if result.success:
        template_file = 'adaptive_card_success.json'
    else:
        template_file = 'adaptive_card_error.json'
    result.message = json.dumps(result.message)[1:-1]
    try:
        send_templated_adaptive_card(teams_secret_arn, teams_channel,
                                     template_file, result.dict())
    except Exception:
        log.exception('Unable to send message to teams')
    if not result.success:
        try:
            send_templated_adaptive_card(teams_secret_arn, 'failures',
                                         template_file, result.dict())
        except Exception:
            log.exception('Unable to send error message to teams')


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Parse the results from the Step Function."""
    del context
    log = ics_lambda.lambda_logging('workflow_error_parser', event)
    message = _handle_event(log, event)
    # TODO(platform): Move into separate message dispatch function
    # 4409
    if event.get('teams_secret_arn') and event.get('teams_channel'):
        _notify_teams(log, message, event['teams_secret_arn'],
                      event['teams_channel'])

    return ics_lambda.finish(log, message.get_result())


if __name__ == '__main__':
    ics_lambda.run_local(lambda_handler)
