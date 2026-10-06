# One thing + X.509 certificate per device. The policy uses the connection's thing name,
# so a device can only connect as itself and only publish to its own topic.
resource "aws_iot_thing" "device" {
  for_each = toset(var.devices)
  name     = each.value
}

resource "aws_iot_certificate" "device" {
  for_each = toset(var.devices)
  active   = true
}

resource "aws_iot_thing_principal_attachment" "device" {
  for_each  = toset(var.devices)
  thing     = aws_iot_thing.device[each.value].name
  principal = aws_iot_certificate.device[each.value].arn
}

resource "aws_iot_policy" "device" {
  name = "airsense-device"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect   = "Allow", Action = "iot:Connect",
        Resource = "${local.prefix}:client/$${iot:Connection.Thing.ThingName}",
      Condition = { Bool = { "iot:Connection.Thing.IsAttached" = "true" } } },
      { Effect = "Allow", Action = "iot:Publish", Resource = [
        "${local.prefix}:topic/airsense/$${iot:Connection.Thing.ThingName}/telemetry",
        "${local.prefix}:topic/$aws/things/$${iot:Connection.Thing.ThingName}/shadow/update",
      ] },
      { Effect = "Allow", Action = "iot:Subscribe", Resource = [
        "${local.prefix}:topicfilter/$aws/things/$${iot:Connection.Thing.ThingName}/shadow/update/delta",
      ] },
      { Effect = "Allow", Action = "iot:Receive", Resource = [
        "${local.prefix}:topic/$aws/things/$${iot:Connection.Thing.ThingName}/shadow/update/delta",
      ] },
    ]
  })
}

resource "aws_iot_policy_attachment" "device" {
  for_each = toset(var.devices)
  policy   = aws_iot_policy.device.name
  target   = aws_iot_certificate.device[each.value].arn
}

resource "aws_cloudwatch_log_group" "iot_errors" {
  name              = "/airsense/iot-rule-errors"
  retention_in_days = 14
}

resource "aws_iam_role" "iot_rule" {
  name = "airsense-iot-rule"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "iot.amazonaws.com" }
  }] })
}

resource "aws_iam_role_policy" "iot_rule" {
  role = aws_iam_role.iot_rule.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
    Resource = "${aws_cloudwatch_log_group.iot_errors.arn}:*"
  }] })
}

# topic(2) is the device ID from the MQTT topic; the Lambda checks it matches the payload.
resource "aws_iot_topic_rule" "telemetry" {
  name        = "airsense_telemetry"
  enabled     = true
  sql         = "SELECT *, topic(2) AS topic_device FROM 'airsense/+/telemetry'"
  sql_version = "2016-03-23"
  lambda {
    function_arn = aws_lambda_function.ingest.arn
  }
  error_action {
    cloudwatch_logs {
      log_group_name = aws_cloudwatch_log_group.iot_errors.name
      role_arn       = aws_iam_role.iot_rule.arn
    }
  }
}
