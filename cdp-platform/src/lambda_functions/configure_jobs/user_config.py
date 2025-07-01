# -*- coding: utf-8 -*-
"""This module contains the user facing models that can be specified in the
Step Function."""
from typing import Optional

from pydantic import BaseModel


class UserTaskConfig(BaseModel, extra='forbid'):
    """Class with user specified task settings."""
    arguments: Optional[list[int | float | str]] = None
    environment: Optional[dict[str, str]] = None
    kwargs: Optional[dict[str, int | float | str]] = None

    def combine(
        self,
        default_arguments: Optional[list[int | float | str]] = None,
        default_environment: Optional[dict[str, str]] = None,
        default_kwargs: Optional[dict[str, int | float | str]] = None
    ) -> 'UserTaskConfig':
        """Combine this task config with the defaults given as arguments."""
        return UserTaskConfig(
            arguments=self.arguments or default_arguments,
            environment=self.environment or default_environment,
            kwargs=self.kwargs or default_kwargs,
        )
