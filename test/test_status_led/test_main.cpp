// The dock's status LED: 120 pulses a minute while it starts, 60 while it
// works, and three flashes over a steady glow while something is wrong.
#include <unity.h>
#include <cstdint>

#include "dock/StatusLed.h"

void setUp() {}
void tearDown() {}

void test_it_starts_in_the_starting_state() {
    StatusLed led;
    TEST_ASSERT_EQUAL_INT(StatusLed::STARTING, led.state());
}

void test_the_peak_is_fifteen_percent_on_a_gamma_curve() {
    TEST_ASSERT_EQUAL_UINT16(252, StatusLed::peakDuty());
}

void test_starting_pulses_twice_a_second() {
    StatusLed led;
    led.state(StatusLed::STARTING, 0);
    TEST_ASSERT_EQUAL_UINT32(500, StatusLed::kFastPulseMs);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(StatusLed::peakDuty(), led.dutyAt(250));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(500));
    // A quarter turn each side of the peak gives the same light.
    TEST_ASSERT_EQUAL_UINT16(led.dutyAt(125), led.dutyAt(375));
}

void test_working_pulses_once_a_second() {
    StatusLed led;
    led.state(StatusLed::WELL, 0);
    TEST_ASSERT_EQUAL_UINT32(1000, StatusLed::kSlowPulseMs);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(StatusLed::peakDuty(), led.dutyAt(500));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(1000));
}

void test_a_pulse_climbs_in_sixteen_steps() {
    StatusLed led;
    led.state(StatusLed::WELL, 0);
    uint16_t last = 0;
    int levels = 1;
    for (uint32_t ms = 1; ms <= StatusLed::kSlowPulseMs / 2; ++ms) {
        const uint16_t duty = led.dutyAt(ms);
        TEST_ASSERT_TRUE(duty >= last);
        if (duty != last) ++levels;
        last = duty;
    }
    TEST_ASSERT_EQUAL_INT(StatusLed::kSteps, levels);
}

void test_repeating_a_state_does_not_restart_its_pattern() {
    StatusLed led;
    led.state(StatusLed::WELL, 0);
    led.state(StatusLed::WELL, 500);
    TEST_ASSERT_EQUAL_UINT16(StatusLed::peakDuty(), led.dutyAt(500));
}

void test_changing_state_starts_the_new_pattern_from_its_beginning() {
    StatusLed led;
    led.state(StatusLed::WELL, 0);
    led.state(StatusLed::STARTING, 500);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(500));
    TEST_ASSERT_EQUAL_UINT16(StatusLed::peakDuty(), led.dutyAt(750));
}

void test_trouble_is_three_flashes_and_then_a_steady_glow() {
    StatusLed led;
    led.state(StatusLed::TROUBLE, 0);
    const uint16_t peak = StatusLed::peakDuty();
    const uint32_t slot = StatusLed::kTroubleFlashMs;
    for (uint32_t flash = 0; flash < StatusLed::kTroubleFlashes; ++flash) {
        TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(2 * flash * slot));
        TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt((2 * flash + 1) * slot));
    }
    // Steady from the end of the last gap to the end of the six-second cycle.
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(6 * slot));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(3000));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(StatusLed::kTroubleCycleMs - 1));
    // And then it flashes again.
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(StatusLed::kTroubleCycleMs + slot));
}

void test_a_pattern_survives_the_millis_rollover() {
    StatusLed led;
    const uint32_t start = 0xFFFFFFFF - 1000;
    led.state(StatusLed::WELL, start);
    TEST_ASSERT_EQUAL_UINT16(StatusLed::peakDuty(), led.dutyAt(start + 500));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(start + 1000));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_it_starts_in_the_starting_state);
    RUN_TEST(test_the_peak_is_fifteen_percent_on_a_gamma_curve);
    RUN_TEST(test_starting_pulses_twice_a_second);
    RUN_TEST(test_working_pulses_once_a_second);
    RUN_TEST(test_a_pulse_climbs_in_sixteen_steps);
    RUN_TEST(test_repeating_a_state_does_not_restart_its_pattern);
    RUN_TEST(test_changing_state_starts_the_new_pattern_from_its_beginning);
    RUN_TEST(test_trouble_is_three_flashes_and_then_a_steady_glow);
    RUN_TEST(test_a_pattern_survives_the_millis_rollover);
    return UNITY_END();
}
