###################################
 CDP: Access to the CDP Repository
###################################

************
 Role Setup
************

First, the AWS CLI tools need to be installed. The following AWS roles
should be created in the AWS CLI config file.

.. code::

   [profile cdp_login]
   aws_access_key_id = <... insert key here ...>
   aws_secret_access_key = <... insert secret here ...>

   [profile cdp_developer]
   source_profile = cdp_login
   region = eu-central-1
   role_arn = arn:aws:iam::006266547701:role/cdp-developer-role

   [profile cdp_commit]
   source_profile = cdp_developer
   region = eu-central-1
   role_arn = arn:aws:iam::006266547701:role/devops/cdp/cdp-commit-role

The login profile details are taken from the login web page. The
configuration above uses the login role to assume the CDP developer role
in the staging account, which can be used for data access in that
account. The dev / staging / prod accounts have dedicated developer
roles, which differ in the numeric account id:

   -  543803411794 for dev
   -  006266547701 for staging
   -  906496560353 for prod

The three CDP developer roles for de different accounts can all be used
to assume the CDP commit role that can write to the CDP repository. The
repository is hosted in the staging account, so this profile should NOT
be changed!

************************
 Cloning the Repository
************************

Use the following commands to install the AWS CodeCommit helper and to
clone the CDP repository with the cdp_commit profile that was configured
above:

.. code:: bash

   pip install git-remote-codecommit
   git clone codecommit::eu-central-1://cdp_commit@merck-cdp

***********************
 Steps to check access
***********************

In order to check access, you can use the following commands to see that
the role access is working:

.. code:: bash

   aws sts get-caller-identity --profile cdp_login
   aws sts get-caller-identity --profile cdp_developer
   aws sts get-caller-identity --profile cdp_commit
