# -*- coding: utf-8 -*-
"""Module to test the lambda function invocation via the Glue job."""
import json
import logging
from typing import Any

from invoke_via_glue import DeployedGluePayload
from lambda_config import LambdaConfig
from utils_test import set_test_env


def _run_event_test(event: Any) -> None:
    """Function to run a single example."""
    event = DeployedGluePayload.model_validate(event)
    lambda_config = LambdaConfig()
    result = event.process(logging.getLogger(), lambda_config)
    logging.warning(json.dumps(result, indent=2))


def run_example() -> None:
    """Function to run the examples."""
    set_test_env()
    _run_event_test({
        'mode': 'get-deployed-glue-config',
        'task_name': 'version_info',
        'user_task_config': {
            'arguments': None,
            'environment': None,
            'kwargs': None
        }
    })


if __name__ == '__main__':
    run_example()
