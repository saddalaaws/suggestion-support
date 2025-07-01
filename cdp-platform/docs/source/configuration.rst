###############
 CDP: Overview
###############

The custom data processing (CDP) allows to run data processing tasks
within AWS. Currently only python processing tasks are supported. The
python code can be provided in the form of python source code files or
Jupyter Notebooks written in python.

There are three different AWS accounts that are completely separated
from each other:

   -  dev
   -  testing
   -  staging
   -  prod

In each account, the CDP is split into different parts, which currently
orient themselves along country lines.

The tasks that run on top of each country infrastructure have access to
the input buckets of the underlying ICS infrastructure (eg.
merck-ics-staging-tw-input) There is also a storage location for CDP
output / processing data (eg. merck-cdp-staging-tw-storage).

The execution of the custom data processing tasks is orchestrated by a
step function The step function can be provided with a list of
parameters that are described in the section :ref:`CDP: Step Function
Parameters`. The configuration of the tasks themselves is described in
:ref:`CDP: Task Configuration`.

########################
 CDP: Technical Details
########################

The runtime environment is provided by AWS Glue 4.0.

The code for the data processing task are stored in folders of the
"merck-cdp" git repository that is available via CodeCommit in the
eu-central-1 region. Every push to this repository triggers the
deployment of the task code.

The CDP platform itself is defined in the "merck-cdp-platform" repository
and works on top of the base infrastructure provided by the iConnect
Suggestion Platform (merck-ics). Every commit to this repository
triggers the deployment of the platform infrastructure and the task
code.

The step function consists of a Lambda function which configures the
subsequent execution of Glue jobs.

#########################
 CDP: Task Configuration
#########################

*Please note that new tasks first needs to be enabled in the
merck-cdp-platform repository!*

Tasks are configured in subfolders of the merck-cdp repository. A
template configuration for tasks is given in the folder "template".

The branch "main" in this repository has a special function, since it is
the branch where the deployment configuration is taken from.

**************************
 Deployment Configuration
**************************

FIXME: Please note that the deployment process was updated!

The JSON file with the deployment configuration is named
"cdp_deploy.json" and has the following structure:

.. code:: javascript

   {
       "comments": "Only the configuration content from the 'main' branch is used!",
       "environment_git_ref": {
           "dev": "main",
           "prod": null,
           "staging": null
       }
   }

It contains a git references for the available AWS accounts
(dev/staging/prod), where the task can be deployed to. These git
references can be arbitrary branches, tags, git commit hashes or null.
The value "null" means that the task is not deployed into the account.

This gives the developer of the custom data processing task full control
of the deployed versions.

All other config files that are described below are taken from the git
revision that are given in "cdp_deploy.json"!

*******************
 Run Configuration
*******************

The run configuration is specified in the JSON file "cdp_config.json".
Here is an example for a typical run configuration:

.. code:: javascript

   {
       "entry_point": "script:main",
       "run": {
           "default": false,
           "frequency": {
               "plugin": "ics_frequency.Always"
           }
       }
   }

The config file contains the following parameters:

   -  entry_point - this is a string which is either the name of a
      script or jupyter notebook or the name of a script followed by a
      colon and the name of the method that should be executed. The
      method will be called without arguments. If the name of the script
      does not end in ".py", the extension will be added automatically.
      The script path is relative to the configured working directory.

      Examples:

         -  "script:main" - run method "main" from script.py
         -  "script.py:main" - run method "main" from script.py
         -  "script" - run script.py
         -  "script.ipynb" - run code contained in the jupyter notebook
            script.ipynb

   -  cwd - this contains the path (relative to the task directory) that
      should be used as working directory of the job If the directory
      doesn't exist, it will be created.

      Examples:

         -  "." - this is the default
         -  "workspace/123" - change into the directory
            "workspace/example" before executing the script

   -  arguments - this contains the arguments that are given to the
      script. Depending on the type of entry point, this are either
      command line arguments or parameters for the specified method.

      Examples:

         -  [] - this is the default
         -  ["run", "model1"] - provides the script with two positional
            arguments

   -  kwargs - this contains keyword arguments that can be given to a
      method-based entry point.

      Examples:

         -  {"key": "value"} - this sets the parameter "key" to "value"

   -  environment - this contains the dictionary with environment
      variables that are given to the script

      Examples:

         -  {} - this is the default
         -  {"mode": "debug"} - the script runs with the environment
            variable mode=debug
         -  {"MODEL": "test", "": ""} -

   -  python_lib_dirs - this contains a list of directories that are
      added to the python library search path

   -  run.enabled_account_names - this is an optional list of strings with the
      names of the accounts (dev, testing, staging, prod) in which the task
      should run when scheduled

   -  run.enabled_scopes - this is an optional list of strings with the
      scopes in which the task should run when scheduled

   -  run.default - this is a boolean parameter that determines if the
      script should be run by default. If it is set to false, the script
      can only be executed manually by specifying the name in the
      "tasks" parameter of the step function.

   -  run.frequency - this contains the plugin configuration of an ICS
      Frequency Plugin. Please refer to the ICS documentation for a
      complete list of plugins that are available!

###############################
 CDP: Step Function Parameters
###############################

These are the main parameters that determine which tasks are run

   -  tasks - a string with a comma separated list of tasks that should
      be processed. If this variable is not specified, the list will
      contain all the tasks which have "default" set to true. (It is
      only possible to specify tasks which have been whitelisted in the
      merck-cdp-platform repository!)

   -  settings - a dictionary with task names as keys. The values can be
      used to override the arguments, kwargs and environment of the job.

      Example: "settings": {"template": {"arguments": [1, 2, 3]}}

   -  check_schedule - a boolean value which determines if the
      scheduling configuration of the task should be taken into account.
      If this variable is not specified, the default is to not check the
      schedule. Manually started step functions do not define this by
      default, while automatically started step functions (triggered by
      time or file uploads), will set this variable to true.

################################
 CDP: Job Environment Variables
################################

CDP makes several environment variables available to the job. All
environment variables are JSON encoded.

This is a list of all the variables:

   -  CDP_RUN: Flag that can be checked to see if the job is running on
      AWS (value is empty for local jobs and non-empty when runnon on
      AWS)

   -  CDP_ENV_ACCOUNT_NAME: Name of the account (eg. dev, staging, prod)

   -  CDP_ENV_DATABASE_NAME: Name of the glue database for CDP data
      products

   -  CDP_ENV_INPUT_BUCKET_NAME_MAP: Dictionary with franchises as keys
      and S3 bucket names as values

   -  CDP_ENV_INPUT_DATABASE_MAP: Dictionary with franchises as keys and
      Glue input bucket databases as values

   -  CDP_ENV_PREFIX: Name of the prefix (eg. cdp-staging-de for the
      german staging environment)

   -  CDP_ENV_SCOPE: Name of the scope / country (eg. de for germany)

   -  CDP_ENV_STORAGE_PREFIX: S3 Path prefix for storing files (eg.
      s3://merck-cdp-staging-de-storage)

   -  CDP_ENV_WORKSPACE_NAME: Name of the athena workspace for SQL
      queries (eg. cdp-staging-de-workgroup)
