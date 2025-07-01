data "aws_secretsmanager_secret" "teams_secret" {
  count = var.teams_secret_name == "" ? 0 : 1
  name  = var.teams_secret_name
}

locals {
  group_type = "Parallel" # Name of stepfunction state used to just group things together

  # To simplify error handling, the main workflow is wrapped into step,
  # and the error handling is defined for the whole step at once
  # Errors are filtered and a notification is sent to an SNS topic
  workflow_definition = {
    "Comment" : var.description,
    "StartAt" : var.state_name,
    "States" : {
      (var.state_name) : {
        "Type" : local.group_type,
        "Branches" : [jsondecode(var.main_branch)]
        "Catch" : [{
          "ErrorEquals" : ["States.ALL"],
          "Next" : "State Parser",
        }],
        "OutputPath" : "$[0]",
        "ResultPath" : "$",
        "Next" : "State Parser",
      },

      "State Parser" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::lambda:invoke",
        "Parameters" : {
          "FunctionName" : var.error_parser_info["arn"],
          "Payload" : {
            "execution_arn.$" : "$$.Execution.Id",
            "execution_start_time.$" : "$$.Execution.StartTime",
            "sfn_result.$" : "$",
            "workflow_description" : var.description,
            "workflow_name" : var.name,
            "enable_user_discovery" : var.enable_user_discovery,
            "teams_secret_arn" : var.teams_secret_name == "" ? null : data.aws_secretsmanager_secret.teams_secret[0].arn,
            "teams_channel" : var.teams_channel,
          }
        }
        "OutputPath" : "$.Payload",
        "Next" : "Notification Check",
        "Catch" : [{
          "ErrorEquals" : ["States.ALL"],
          "Next" : "Exceptional Notification",
        }],
      },

      "Notification Check" : {
        "Type" : "Choice",
        "Choices" : [
          {
            "And" : [
              {
                "Variable" : "$.notify",
                "BooleanEquals" : false,
              },
              {
                "Variable" : "$.success",
                "BooleanEquals" : false,
              },
            ]
            "Next" : "Abort",
          },
          {
            "And" : [
              {
                "Variable" : "$.notify",
                "BooleanEquals" : false,
              },
              {
                "Variable" : "$.success",
                "BooleanEquals" : true,
              },
            ]
            "Next" : "Success",
          },
          {
            "And" : [
              {
                "Variable" : "$.notify",
                "BooleanEquals" : true,
              },
              {
                "Variable" : "$.success",
                "BooleanEquals" : false,
              },
            ]
            "Next" : "Error Notification",
          },
          {
            "And" : [
              {
                "Variable" : "$.notify",
                "BooleanEquals" : true,
              },
              {
                "Variable" : "$.success",
                "BooleanEquals" : true,
              },
            ]
            "Next" : "Success Notification",
          },
        ]
        "Default" : "Exceptional Notification",
      }

      "Exceptional Notification" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::sns:publish",
        "Parameters" : {
          "TopicArn" : var.notification_topic_arn,
          "Subject" : "Unexpected error",
          "Message.$" : "States.Format('Unexpected error in {}:\n{}', $$.Execution.Id, $)",
        },
        "ResultPath" : null,
        "Next" : "Abort",
      },

      "Error Notification" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::sns:publish",
        "Parameters" : {
          "TopicArn" : var.notification_topic_arn,
          "Subject.$" : "$.subject",
          "Message.$" : "$.message",
          "MessageAttributes.$" : "$.message_attributes",
        },
        "ResultPath" : null,
        "Next" : "Abort",
      },

      "Abort" : {
        "Type" : "Fail",
      }

      "Success Notification" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::sns:publish",
        "Parameters" : {
          "TopicArn" : var.notification_topic_arn,
          "Subject.$" : "$.subject",
          "Message.$" : "$.message",
          "MessageAttributes.$" : "$.message_attributes",
        },
        "ResultPath" : null,
        "Next" : "Success",
      },

      "Success" : {
        "Type" : "Pass",
        "End" : true,
      }
    }
  }
}
