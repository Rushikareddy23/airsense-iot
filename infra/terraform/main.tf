terraform {
  required_version = ">= 1.6"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.60" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "airsense", ManagedBy = "terraform" } }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "alert_email" {
  description = "Receives air-quality alerts and infrastructure alarms (confirm the AWS email once)."
  type        = string
}

variable "devices" {
  description = "Device IDs = AWS IoT thing names. One certificate is created per device."
  type        = list(string)
  default     = ["airsense-01"]
}

variable "retention_days" {
  type    = number
  default = 30
}

data "aws_caller_identity" "me" {}
data "aws_region" "current" {}

data "aws_iot_endpoint" "ats" {
  endpoint_type = "iot:Data-ATS"
}

locals {
  prefix = "arn:aws:iot:${var.region}:${data.aws_caller_identity.me.account_id}"
}
