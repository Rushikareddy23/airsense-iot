#pragma once
#include <stdint.h>

// Exponential backoff with a cap and +/-jitter so many devices don't reconnect in lockstep
// after an outage (thundering herd).
class Backoff {
 public:
  Backoff(uint32_t base_ms = 1000, uint32_t max_ms = 60000) : base_(base_ms), max_(max_ms) {}
  // rand01 in [0,1) is passed in so the function is deterministic in tests.
  uint32_t next(float rand01) {
    uint32_t d = base_ << (attempt_ < 16 ? attempt_ : 16);
    if (d > max_ || d == 0) d = max_;
    if (attempt_ < 31) ++attempt_;
    float jitter = 0.8f + 0.4f * rand01;  // 80%..120%
    return (uint32_t)(d * jitter);
  }
  void reset() { attempt_ = 0; }
  uint32_t attempts() const { return attempt_; }

 private:
  uint32_t base_, max_, attempt_ = 0;
};
