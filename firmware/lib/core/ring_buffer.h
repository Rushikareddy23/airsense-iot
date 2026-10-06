// Fixed-size ring buffer: keeps the newest readings while Wi-Fi/MQTT is down.
// No heap allocation, so it is safe to use on a microcontroller.
#pragma once
#include <stddef.h>

template <typename T, size_t N>
class RingBuffer {
 public:
  // Adds an item. When full, the oldest item is overwritten. Returns false if one was dropped.
  bool push(const T& item) {
    bool dropped = full();
    buf_[head_] = item;
    head_ = (head_ + 1) % N;
    if (dropped) {
      tail_ = (tail_ + 1) % N;
      ++dropped_;
    } else {
      ++count_;
    }
    return !dropped;
  }
  // Oldest item without removing it.
  bool peek(T& out) const {
    if (empty()) return false;
    out = buf_[tail_];
    return true;
  }
  bool pop(T& out) {
    if (!peek(out)) return false;
    tail_ = (tail_ + 1) % N;
    --count_;
    return true;
  }
  size_t size() const { return count_; }
  bool empty() const { return count_ == 0; }
  bool full() const { return count_ == N; }
  size_t dropped() const { return dropped_; }
  static constexpr size_t capacity() { return N; }

 private:
  T buf_[N];
  size_t head_ = 0, tail_ = 0, count_ = 0, dropped_ = 0;
};
