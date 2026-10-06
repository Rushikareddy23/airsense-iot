resource "aws_dynamodb_table" "readings" {
  name         = "airsense-readings"
  billing_mode = "PAY_PER_REQUEST" # no idle cost
  hash_key     = "device_id"
  range_key    = "ts"
  attribute {
    name = "device_id"
    type = "S"
  }
  attribute {
    name = "ts"
    type = "N"
  }
  ttl {
    attribute_name = "expires_at" # old readings are deleted automatically
    enabled        = true
  }
  point_in_time_recovery { enabled = true }
}

resource "aws_dynamodb_table" "devices" {
  name         = "airsense-devices"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  attribute {
    name = "device_id"
    type = "S"
  }
}

resource "aws_sns_topic" "alerts" {
  name = "airsense-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
