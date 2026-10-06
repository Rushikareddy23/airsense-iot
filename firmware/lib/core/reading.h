#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

struct Reading {
  uint32_t epoch_s;     // Unix time from NTP
  float temp_c;
  float humidity_pct;
  float pressure_hpa;
  uint16_t co2_ppm;     // equivalent CO2 from the SGP30
  uint16_t tvoc_ppb;
};

enum class AirQuality { Good, Moderate, Poor };

// CO2 bands commonly used for indoor air (ASHRAE guidance ~1000-1200 ppm).
inline AirQuality classify_co2(uint16_t ppm, uint16_t moderate = 800, uint16_t poor = 1200) {
  if (ppm >= poor) return AirQuality::Poor;
  if (ppm >= moderate) return AirQuality::Moderate;
  return AirQuality::Good;
}

inline const char* to_string(AirQuality q) {
  switch (q) {
    case AirQuality::Good: return "good";
    case AirQuality::Moderate: return "moderate";
    default: return "poor";
  }
}

// Serialises a reading to JSON without a JSON library. Returns bytes written, or 0 if
// the buffer is too small (never writes a truncated message).
inline size_t to_json(const Reading& r, const char* device_id, uint32_t seq, char* out, size_t len) {
  int n = snprintf(out, len,
                   "{\"device_id\":\"%s\",\"seq\":%lu,\"ts\":%lu,\"temp_c\":%.2f,\"humidity_pct\":%.1f,"
                   "\"pressure_hpa\":%.1f,\"co2_ppm\":%u,\"tvoc_ppb\":%u,\"air_quality\":\"%s\"}",
                   device_id, (unsigned long)seq, (unsigned long)r.epoch_s, r.temp_c, r.humidity_pct,
                   r.pressure_hpa, r.co2_ppm, r.tvoc_ppb, to_string(classify_co2(r.co2_ppm)));
  if (n < 0 || (size_t)n >= len) return 0;
  return (size_t)n;
}

// Rejects physically impossible values (loose sensor wire, I2C glitch) before publishing.
inline bool plausible(const Reading& r) {
  return r.temp_c > -40 && r.temp_c < 85 && r.humidity_pct >= 0 && r.humidity_pct <= 100 &&
         r.pressure_hpa > 300 && r.pressure_hpa < 1100 && r.co2_ppm >= 400 && r.co2_ppm <= 60000;
}
