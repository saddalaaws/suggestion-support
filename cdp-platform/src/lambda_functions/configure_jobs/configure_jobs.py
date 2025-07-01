# -*- coding: utf-8 -*-
"""Lambda function to configure the custom data processing."""

from typing import Any, Union

from ics_lambda import finish, lambda_logging
from invoke_via_glue import BasicGluePayload, DeployedGluePayload
from invoke_via_sfn import SFNPayload
from lambda_config import LambdaConfig
from pydantic import TypeAdapter


def lambda_handler(raw_event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Parse the specified config files."""
    del context
    log = lambda_logging('configure_custom_processing', raw_event, [])
    lambda_config = LambdaConfig()
    event: Any = TypeAdapter(
        Union[SFNPayload, BasicGluePayload,
              DeployedGluePayload]).validate_python(raw_event)
    if isinstance(event, (SFNPayload, BasicGluePayload, DeployedGluePayload)):
        result = event.process(log, lambda_config)
        return finish(log, result)
    return finish(log, {'error': repr(event)})
