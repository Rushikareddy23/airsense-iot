// Copy to include/secrets.h (git-ignored) and fill in. The certificate and key come from
// `terraform output` (see README). Never commit the real file.
#pragma once

#define WIFI_SSID "your-wifi"
#define WIFI_PASSWORD "your-password"
#define DEVICE_ID "airsense-01"                     // must equal the AWS IoT thing name
#define AWS_IOT_ENDPOINT "xxxxxxxxxxxx-ats.iot.us-east-1.amazonaws.com"

// Amazon Root CA 1: https://www.amazontrust.com/repository/AmazonRootCA1.pem
static const char AWS_ROOT_CA[] = R"EOF(
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)EOF";

static const char DEVICE_CERT[] = R"EOF(
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)EOF";

static const char DEVICE_PRIVATE_KEY[] = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----
)EOF";
