output "iot_endpoint" {
  value = data.aws_iot_endpoint.ats.endpoint_address
}

output "api_url" {
  value = aws_apigatewayv2_stage.default.invoke_url
}

output "dashboard_url" {
  value = "https://${aws_cloudfront_distribution.web.domain_name}"
}

output "web_bucket" {
  value = aws_s3_bucket.web.bucket
}

output "admin_token" {
  value     = random_password.admin_token.result
  sensitive = true
}

output "device_certificates" {
  description = "Per-device certificate and private key. Write them to files; never commit them."
  value = { for d in var.devices : d => {
    certificate_pem = aws_iot_certificate.device[d].certificate_pem
    private_key     = aws_iot_certificate.device[d].private_key
  } }
  sensitive = true
}
