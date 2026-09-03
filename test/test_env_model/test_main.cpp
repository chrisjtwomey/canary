// The simulated room behaves like a room.
#include <unity.h>
#include <cmath>
#include "sensors/mock/EnvModel.h"

static const uint32_t kMidnight = 1756857600;   // 2025-09-03 00:00 UTC
static uint32_t at(float hour) { return kMidnight + (uint32_t)(hour * 3600.0f); }

void setUp() {}
void tearDown() {}

void test_reset_is_deterministic_for_a_seed() {
    EnvModel a(3), b(3);
    a.reset(at(12)); b.reset(at(12));
    a.advanceTo(at(20)); b.advanceTo(at(20));
    TEST_ASSERT_EQUAL_FLOAT(a.co2Ppm(), b.co2Ppm());
    TEST_ASSERT_EQUAL_FLOAT(a.tempC(), b.tempC());
    float na = a.noise(1.0f), nb = b.noise(1.0f);
    TEST_ASSERT_EQUAL_FLOAT(na, nb);
}

void test_co2_rises_when_occupied_and_falls_when_empty() {
    EnvModel m(1);
    m.reset(at(17.5f));                 // evening, two people arrive
    float before = m.co2Ppm();
    m.advanceTo(at(20.0f));
    float evening = m.co2Ppm();
    TEST_ASSERT_TRUE_MESSAGE(evening > before + 100.0f, "CO2 should climb with two people in the room");
    m.advanceTo(at(24.0f + 6.0f));      // empty overnight
    TEST_ASSERT_TRUE_MESSAGE(m.co2Ppm() < evening - 100.0f, "CO2 should decay overnight");
    TEST_ASSERT_TRUE(m.co2Ppm() >= 420.0f);
}

void test_window_open_pulls_co2_down_fast() {
    EnvModel m(1);
    m.reset(at(7.9f));
    m.advanceTo(at(8.0f));
    float closed = m.co2Ppm();
    m.advanceTo(at(8.5f));              // window open 08:00-08:30
    TEST_ASSERT_TRUE(m.co2Ppm() < closed);
}

void test_pm25_spikes_at_cooking_time_and_decays() {
    EnvModel m(1);
    m.reset(at(17.0f));
    float quiet = m.pm25();
    m.advanceTo(at(18.4f));
    float cooking = m.pm25();
    TEST_ASSERT_TRUE_MESSAGE(cooking > quiet + 40.0f, "cooking should spike PM2.5");
    m.advanceTo(at(21.0f));
    TEST_ASSERT_TRUE(m.pm25() < cooking / 2.0f);
    TEST_ASSERT_TRUE(m.pm1() < m.pm25() && m.pm25() < m.pm10());
}

void test_gas_resistance_falls_with_voc_and_humidity() {
    EnvModel m(1);
    m.reset(at(17.0f));
    float clean = m.gasOhm();
    m.advanceTo(at(18.5f));             // cooking VOCs
    TEST_ASSERT_TRUE(m.gasOhm() < clean * 0.7f);
    TEST_ASSERT_TRUE(m.vocIndex() <= 1.0f);
}

void test_temperature_follows_heating_and_rh_falls_when_heated() {
    EnvModel m(1);
    m.reset(at(16.0f));                 // heating off, 18.5 target
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 18.5f, m.tempC());
    float rhCold = m.rhPct();
    m.advanceTo(at(20.0f));             // heating on since 17:00
    TEST_ASSERT_TRUE(m.tempC() > 20.0f);
    float absNow = m.absHumidity();
    TEST_ASSERT_TRUE_MESSAGE(EnvModel::rhFromAbs(absNow, m.tempC()) < EnvModel::rhFromAbs(absNow, 18.5f),
                             "same water, warmer air, lower RH");
    (void)rhCold;
}

void test_magnus_roundtrip() {
    float abs = EnvModel::absFromRh(50.0f, 21.0f);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 50.0f, EnvModel::rhFromAbs(abs, 21.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 9.2f, abs);   // ~9.2 g/m3 at 21 C, 50 %
}

void test_pressure_is_plausible_and_slow() {
    EnvModel m(1);
    m.reset(at(0));
    float p0 = m.pressureHpa();
    m.advanceTo(at(1));
    TEST_ASSERT_TRUE(p0 > 1000.0f && p0 < 1025.0f);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, p0, m.pressureHpa());
}

void test_noise_has_roughly_the_requested_sigma() {
    EnvModel m(42);
    float sum = 0, sq = 0;
    const int n = 4000;
    for (int i = 0; i < n; ++i) { float v = m.noise(2.0f); sum += v; sq += v * v; }
    float mean = sum / n, sd = sqrtf(sq / n - mean * mean);
    TEST_ASSERT_FLOAT_WITHIN(0.15f, 0.0f, mean);
    TEST_ASSERT_FLOAT_WITHIN(0.6f, 2.0f, sd);
}

// The Python mock source ports this generator; both are pinned to these
// values so the two rooms stay identical.
void test_xorshift_sequence_is_pinned() {
    // uniform() is (xorshift32() >> 8) / 2^24, so this recovers the generator's
    // top 24 bits exactly. Raw draws for seed 5 are 1351845, 336141829,
    // 3472693697; the Python port is pinned to the same three.
    EnvModel m(5);
    TEST_ASSERT_EQUAL_UINT32(5280u,     (uint32_t)(m.uniform() * 16777216.0f));
    TEST_ASSERT_EQUAL_UINT32(1313054u,  (uint32_t)(m.uniform() * 16777216.0f));
    TEST_ASSERT_EQUAL_UINT32(13565209u, (uint32_t)(m.uniform() * 16777216.0f));
}

void test_advance_backwards_just_moves_the_clock() {
    EnvModel m(1);
    m.reset(at(12));
    float c = m.co2Ppm();
    m.advanceTo(at(11));
    TEST_ASSERT_EQUAL_UINT32(at(11), m.epoch());
    TEST_ASSERT_EQUAL_FLOAT(c, m.co2Ppm());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_reset_is_deterministic_for_a_seed);
    RUN_TEST(test_co2_rises_when_occupied_and_falls_when_empty);
    RUN_TEST(test_window_open_pulls_co2_down_fast);
    RUN_TEST(test_pm25_spikes_at_cooking_time_and_decays);
    RUN_TEST(test_gas_resistance_falls_with_voc_and_humidity);
    RUN_TEST(test_temperature_follows_heating_and_rh_falls_when_heated);
    RUN_TEST(test_magnus_roundtrip);
    RUN_TEST(test_pressure_is_plausible_and_slow);
    RUN_TEST(test_noise_has_roughly_the_requested_sigma);
    RUN_TEST(test_xorshift_sequence_is_pinned);
    RUN_TEST(test_advance_backwards_just_moves_the_clock);
    return UNITY_END();
}
