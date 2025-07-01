# -*- coding: utf-8 -*-
"""Module to provide utilities to the tests."""
import json
import logging
import os


def set_test_env():
    """Setup the test environment variables."""
    logging.basicConfig(level=logging.INFO)
    s3_path = 's3://merck-cdp-dev-code-storage'
    cdp_tools_file = 'cdp_tools-22.4.21-py3-none-any.whl'
    cdp_tools_path = f'{s3_path}/cdp_platform/{cdp_tools_file}'
    config_file_dir = f'{s3_path}/tasks'
    task_list = [
        'ab_testing',
        'automated_email_tagging',
        'channel_segmentation',
        'impact_analysis',
        'mc_mlr_extraction',
        'sprinklr_ingestion',
        'sprinklr_matching',
        'snooze_based_on_segment',
        'version_info',
        'sanitization',
    ]
    input_bucket_map = {
        'cme': 'merck-ics-dev-br-input-cme',
        'shared': 'merck-ics-dev-br-input',
    }
    input_database_map = {
        'cme': 'ics_dev_br_00_input_cme_database',
        'shared': 'ics_dev_br_00_input_database',
    }
    storage_key_arn = (
        'arn:aws:kms:eu-central-1:543803411794:alias/cdp/dev/br/cdp-dev-br-key'
    )
    task_env = {
        'CDP_ENV_ACCOUNT_NAME': 'dev',
        'CDP_ENV_DATABASE_NAME': 'cdp_dev_br_database',
        'CDP_ENV_INPUT_BUCKET_NAME_MAP': json.dumps(input_bucket_map),
        'CDP_ENV_INPUT_DATABASE_MAP': json.dumps(input_database_map),
        'CDP_ENV_PREFIX': 'cdp-dev-br',
        'CDP_ENV_SCOPE': 'br',
        'CDP_ENV_STORAGE_BUCKET_NAME': 'merck-cdp-dev-br-storage',
        'CDP_ENV_STORAGE_KEY_ARN': storage_key_arn,
        'CDP_ENV_STORAGE_PREFIX': 's3://merck-cdp-dev-br-storage',
        'CDP_ENV_WORKSPACE_NAME': 'cdp-dev-br-workgroup',
    }
    settings = {
        'ALLOWED_TASKS': json.dumps(task_list),
        'CDP_TOOLS_WHEEL': cdp_tools_path,
        'CONFIG_FILE_DIR': config_file_dir,
        'INPUT_DATABASE_MAP': json.dumps(input_database_map),
        'RUN_DB_KEY': 'cdp-dev-br',
        'RUN_DB_TABLE': 'ics-dev-eu_central_1-run-db',
        'TASK_ENV': json.dumps(task_env)
    }
    for key, value in settings.items():
        os.environ[key] = value
