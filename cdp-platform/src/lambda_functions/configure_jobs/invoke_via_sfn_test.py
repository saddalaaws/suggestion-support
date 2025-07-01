# -*- coding: utf-8 -*-
"""Module to test the lambda function invocation via the Step Function."""
import logging
from typing import Any

from invoke_via_sfn import SFNPayload
from lambda_config import LambdaConfig
from utils_test import set_test_env


def _run_event_test(event: Any) -> None:
    """Function to run a single example."""
    event = SFNPayload.model_validate(event)
    lambda_config = LambdaConfig()
    result = event.process(logging.getLogger(), lambda_config)
    logging.warning(result.model_dump_json(indent=2))


def run_example() -> None:
    """Function to run the examples."""
    set_test_env()
    _run_event_test({
        'mode': 'get-sfn-jobs',
        'job_name_map': {
            'python': 'cdp-dev-br-custom_data_processing'
        },
        'user_config': {}
    })
    _run_event_test({
        'mode': 'get-sfn-jobs',
        'job_name_map': {
            'python': 'cdp-dev-br-custom_data_processing'
        },
        'user_config': {
            'check_schedule': 'False',
            'tasks': 'impact_analysis,version_info',
            'settings': {
                'ab_testing': {}
            }
        }
    })


if __name__ == '__main__':
    run_example()
