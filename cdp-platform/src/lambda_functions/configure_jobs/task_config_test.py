# -*- coding: utf-8 -*-
"""Module with the tests for the task configuration."""
from typing import Any

from task_config import TaskConfig


def run_example() -> None:
    """Function to run the examples."""
    user_input: dict[str, Any] = {}
    tmp = TaskConfig.model_validate(user_input)
    print(tmp)


if __name__ == '__main__':
    run_example()
