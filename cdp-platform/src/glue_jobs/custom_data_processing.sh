#!/bin/sh

python custom_data_processing.py \
    --additional-python-modules="pydantic" \
    --config_lambda_arn="arn:aws:lambda:eu-central-1:597729636079:function:cdp-testing-vn-configure-jobs" \
    --jobname A \
    --scope="vn" \
    --task_log_group="/cdp/testing/task-log" \
    --task_name="version_info" \
    --user_task_config="{\"arguments\":null,\"environment\":null,\"kwargs\":null}"
