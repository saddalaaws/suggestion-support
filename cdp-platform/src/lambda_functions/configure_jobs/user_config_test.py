# -*- coding: utf-8 -*-
"""Module with the tests for the user configuration."""
import json

from invoke_via_sfn import UserConfig
from user_config import UserTaskConfig


def run_example() -> None:
    """Function to run the examples."""
    user_input = {
        'check_schedule': True,
        'tasks': 'A,B,C',
        'settings': {
            'A': {
                'arguments': [1, 2, 3],
                'environment': {
                    'X': 'ABC'
                }
            },
            'D': {
                'kwargs': {
                    'param': '643'
                }
            }
        }
    }
    tmp = UserConfig.model_validate(user_input)
    print(tmp)
    print(json.dumps(UserTaskConfig().model_dump_json()))


if __name__ == '__main__':
    run_example()
