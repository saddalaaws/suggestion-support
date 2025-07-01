locals {
  # Tasks enabled everywhere
  tasks_common = [
    "DCP",
    "ab_testing",
    "automated_email_tagging",
    "channel_segmentation",
    "impact_analysis",
    "mc_mlr_extraction",
    "snooze_based_on_segment",
    "sprinklr_ingestion",
    "sprinklr_matching",
    "version_info",
  ]

  # Tasks enabled in all countries for the given environment
  tasks_dev_common = [
    "sanitization"
  ]
  tasks_testing_common = [
    "sf_ingestion"
  ]
  tasks_staging_common = [
    "ics_json_automation",
    "sanitization",
  ]
  tasks_prod_common = [
  ]

  # Tasks enabled in all environments for the given scope
  tasks_by_country = {
    "tw" : ["exp_salesalert"],
  }

  account_scope_tasks_map = {
    dev = {
      for scope in local.scope_list :
      scope => distinct(concat(local.tasks_common, local.tasks_dev_common, lookup(local.tasks_by_country, scope, []), []))
    }
    testing = {
      for scope in local.scope_list :
      scope => distinct(concat(local.tasks_common, local.tasks_testing_common, lookup(local.tasks_by_country, scope, []), []))
    }
    staging = {
      for scope in local.scope_list :
      scope => distinct(concat(local.tasks_common, local.tasks_staging_common, lookup(local.tasks_by_country, scope, []), []))
    }
    prod = {
      for scope in local.scope_list :
      scope => distinct(concat(local.tasks_common, local.tasks_prod_common, lookup(local.tasks_by_country, scope, []), []))
    }
  }
}
