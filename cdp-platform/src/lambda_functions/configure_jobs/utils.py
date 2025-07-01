# -*- coding: utf-8 -*-
"""Module with utilities for the lambda function."""
import json
from typing import Any, TypeAlias

from cdp_tools import open_file_path

AnyPath: TypeAlias = str


def load_config(config_file_name: AnyPath) -> dict[str, Any]:
    """Load JSON config from the specified location."""
    with open_file_path(config_file_name) as file_obj:
        config_str = file_obj.read().decode('utf-8')
        return json.loads(config_str)


def split_csl(value: str) -> list[str]:
    """Split a comma separated list."""
    return [item.strip() for item in value.split(',') if item.strip()]
