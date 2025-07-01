# This file will be automatically deleted by the codebuild project

AWS_DEVOPS_REGION          = "eu-central-1"
AWS_DEPLOY_PARAMETERS_PATH = "/devops/cdp/deploy/cdp-deploy-platform"

LOCAL_AWS_DEVOPS_PROFILE    = "ics_devops"
LOCAL_AWS_DEPLOY_PROFILE    = "ics_$${terraform.workspace|nosuffix}"
LOCAL_AWS_DEPLOY_FORCE_ROLE = false
