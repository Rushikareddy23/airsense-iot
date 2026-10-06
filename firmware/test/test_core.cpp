// Native unit tests for the hardware-independent firmware logic.
// Run on any computer:  g++ -std=c++17 -I lib/core test/test_core.cpp -o t && ./t
// (or `pio test -e native` with PlatformIO)
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>

#include "backoff.h"
#include "reading.h"
#include "ring_buffer.h"
#include "smoothing.h"

static int passed = 0;
#define CHECK(x) do { if (!(x)) { printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #x); return 1; } } while (0)

int test_ring_buffer() {
  RingBuffer<int, 3> rb;
  int v;
  CHECK(rb.empty() && !rb.pop(v));
  CHECK(rb.push(1) && rb.push(2) && rb.push(3));
  CHECK(rb.full());
  CHECK(!rb.push(4));               // overwrites oldest (1)
  CHECK(rb.dropped() == 1 && rb.size() == 3);
  CHECK(rb.pop(v) && v == 2);
  CHECK(rb.pop(v) && v == 3);
  CHECK(rb.peek(v) && v == 4);
  CHECK(rb.pop(v) && v == 4 && rb.empty());
  for (int i = 0; i < 100; ++i) rb.push(i);  // wrap-around many times
  CHECK(rb.pop(v) && v == 97);
  ++passed; return 0;
}

int test_json() {
  Reading r{1760000000, 22.456f, 41.2f, 1013.4f, 650, 12};
  char buf[256];
  size_t n = to_json(r, "esp32-01", 7, buf, sizeof buf);
  CHECK(n > 0 && n == strlen(buf));
  CHECK(strcmp(buf, "{\"device_id\":\"esp32-01\",\"seq\":7,\"ts\":1760000000,\"temp_c\":22.46,"
                    "\"humidity_pct\":41.2,\"pressure_hpa\":1013.4,\"co2_ppm\":650,\"tvoc_ppb\":12,"
                    "\"air_quality\":\"good\"}") == 0);
  char tiny[20];
  CHECK(to_json(r, "esp32-01", 7, tiny, sizeof tiny) == 0);  // refuses to truncate
  ++passed; return 0;
}

int test_classify_and_plausible() {
  CHECK(classify_co2(450) == AirQuality::Good);
  CHECK(classify_co2(800) == AirQuality::Moderate);
  CHECK(classify_co2(1500) == AirQuality::Poor);
  CHECK(classify_co2(900, 1000, 2000) == AirQuality::Good);  // thresholds configurable
  Reading ok{0, 21, 40, 1000, 600, 5};
  Reading bad_temp{0, 150, 40, 1000, 600, 5};
  Reading bad_co2{0, 21, 40, 1000, 0, 5};
  CHECK(plausible(ok) && !plausible(bad_temp) && !plausible(bad_co2));
  ++passed; return 0;
}

int test_backoff() {
  Backoff b(1000, 30000);
  CHECK(b.next(0.5f) == 1000);
  CHECK(b.next(0.5f) == 2000);
  CHECK(b.next(0.5f) == 4000);
  for (int i = 0; i < 40; ++i) b.next(0.5f);
  CHECK(b.next(0.5f) == 30000);           // capped
  CHECK(b.next(0.0f) == 24000);           // -20% jitter
  CHECK(b.next(0.999f) >= 35000);         // ~+20% jitter
  b.reset();
  CHECK(b.next(0.5f) == 1000);
  ++passed; return 0;
}

int test_ema() {
  Ema e(0.5f);
  CHECK(!e.ready());
  CHECK(e.update(10) == 10);
  CHECK(e.update(20) == 15);
  CHECK(std::fabs(e.update(20) - 17.5f) < 1e-6);
  ++passed; return 0;
}

int main() {
  int fails = test_ring_buffer() + test_json() + test_classify_and_plausible() + test_backoff() + test_ema();
  printf("%d passed, %d failed\n", passed, fails);
  return fails;
}
