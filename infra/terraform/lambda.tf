data "archive_file" "lambdas" {
  type        = "zip"
  source_dir  = "${path.module}/../../cloud/lambdas"
  output_path = "${path.module}/.build/lambdas.zip"
  excludes    = ["__pycache__"]
}

resource "random_password" "admin_token" {
  length  = 32
  special = false
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- ingest -----------------------------------------------------------------------------
resource "aws_iam_role" "ingest" {
  name               = "airsense-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "ingest_logs" {
  role       = aws_iam_role.ingest.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ingest" {
  role = aws_iam_role.ingest.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:PutItem"], Resource = aws_dynamodb_table.readings.arn },
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.devices.arn },
    { Effect = "Allow", Action = ["sns:Publish"], Resource = aws_sns_topic.alerts.arn },
  ] })
}

resource "aws_lambda_function" "ingest" {
  function_name    = "airsense-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "ingest.handler"
  filename         = data.archive_file.lambdas.output_path
  source_code_hash = data.archive_file.lambdas.output_base64sha256
  timeout          = 10
  memory_size      = 256
  environment {
    variables = {
      READINGS_TABLE  = aws_dynamodb_table.readings.name
      DEVICES_TABLE   = aws_dynamodb_table.devices.name
      ALERT_TOPIC_ARN = aws_sns_topic.alerts.arn
      RETENTION_DAYS  = tostring(var.retention_days)
    }
  }
}

resource "aws_lambda_permission" "iot" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "iot.amazonaws.com"
  source_arn    = aws_iot_topic_rule.telemetry.arn
}

# --- API ----------------------------------------------------------------------------------
resource "aws_iam_role" "api" {
  name               = "airsense-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.api.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:Query"], Resource = aws_dynamodb_table.readings.arn },
    { Effect = "Allow", Action = ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.devices.arn },
    { Effect = "Allow", Action = ["iot:UpdateThingShadow"], Resource = "${local.prefix}:thing/*" },
  ] })
}

resource "aws_lambda_function" "api" {
  function_name    = "airsense-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  handler          = "api.handler"
  filename         = data.archive_file.lambdas.output_path
  source_code_hash = data.archive_file.lambdas.output_base64sha256
  timeout          = 15
  memory_size      = 512
  environment {
    variables = {
      READINGS_TABLE    = aws_dynamodb_table.readings.name
      DEVICES_TABLE     = aws_dynamodb_table.devices.name
      ADMIN_TOKEN       = random_password.admin_token.result
      IOT_DATA_ENDPOINT = data.aws_iot_endpoint.ats.endpoint_address
    }
  }
}

resource "aws_apigatewayv2_api" "http" {
  name          = "airsense"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["https://${aws_cloudfront_distribution.web.domain_name}", "http://localhost:5173"]
    allow_methods = ["GET", "PUT", "OPTIONS"]
    allow_headers = ["content-type", "x-admin-token"]
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "routes" {
  for_each  = toset(["GET /devices", "GET /devices/{id}/readings", "PUT /devices/{id}/config"])
  api_id    = aws_apigatewayv2_api.http.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_rate_limit  = 20 # protects the Lambda/DynamoDB bill from abuse
    throttling_burst_limit = 40
  }
}

resource "aws_lambda_permission" "apigw" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

resource "aws_cloudwatch_metric_alarm" "ingest_errors" {
  alarm_name          = "airsense-ingest-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.ingest.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
