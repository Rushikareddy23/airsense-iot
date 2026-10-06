#pragma once

// Exponential moving average: smooths sensor noise using O(1) memory.
class Ema {
 public:
  explicit Ema(float alpha) : alpha_(alpha) {}
  float update(float x) {
    value_ = has_ ? alpha_ * x + (1 - alpha_) * value_ : x;
    has_ = true;
    return value_;
  }
  float value() const { return value_; }
  bool ready() const { return has_; }

 private:
  float alpha_, value_ = 0;
  bool has_ = false;
};
