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
    StatusLed led;
    TEST_ASSERT_EQUAL_UINT16(252, led.peakDuty());
}

void test_the_brightness_moves_the_peak_on_the_same_curve() {
    StatusLed led;
    led.brightness(30);
    // (0.30 / 0.15)^2.2 = 4.59 times the default peak.
    TEST_ASSERT_UINT16_WITHIN(2, 1157, led.peakDuty());
    led.brightness(150);
    TEST_ASSERT_EQUAL_UINT16(StatusLed::kMaxDuty, led.peakDuty());
}

void test_a_brightness_of_0_keeps_every_state_dark() {
    StatusLed led;
    led.brightness(0);
    const StatusLed::State states[] = {StatusLed::STARTING, StatusLed::WELL,
                                       StatusLed::TROUBLE, StatusLed::UPDATING};
    for (StatusLed::State s : states) {
        led.state(s, 0);
        for (uint32_t t = 0; t < StatusLed::kTroubleCycleMs; t += 50) {
            TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
        }
    }
}

void test_starting_pulses_twice_a_second() {
    StatusLed led;
    led.state(StatusLed::STARTING, 0);
    TEST_ASSERT_EQUAL_UINT32(500, StatusLed::kFastPulseMs);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(250));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(500));
    // A quarter turn each side of the peak gives the same light.
    TEST_ASSERT_EQUAL_UINT16(led.dutyAt(125), led.dutyAt(375));
}

void test_working_pulses_once_a_second() {
    StatusLed led;
    led.state(StatusLed::WELL, 0);
    TEST_ASSERT_EQUAL_UINT32(1000, StatusLed::kSlowPulseMs);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(500));
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
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(500));
}

void test_changing_state_starts_the_new_pattern_from_its_beginning() {
    StatusLed led;
    led.state(StatusLed::WELL, 0);
    led.state(StatusLed::STARTING, 500);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(500));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(750));
}

void test_trouble_is_three_flashes_and_then_a_steady_glow() {
    StatusLed led;
    led.state(StatusLed::TROUBLE, 0);
    const uint16_t peak = led.peakDuty();
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
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(start + 500));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(start + 1000));
}

// The brightest duty over one period of the current pattern.
static uint16_t peakOver(StatusLed& led, uint32_t fromMs, uint32_t periodMs) {
    uint16_t top = 0;
    for (uint32_t t = fromMs; t < fromMs + periodMs; ++t) {
        const uint16_t d = led.dutyAt(t);
        if (d > top) top = d;
    }
    return top;
}

void test_an_update_brightens_and_quickens_as_the_image_is_written() {
    StatusLed led;
    led.state(StatusLed::UPDATING, 0);
    // At the start: the working pulse's rate, at a quarter of the light.
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_TRUE(led.dutyAt(500) > 0 && led.dutyAt(500) < led.peakDuty() / 4);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(1000));
    const uint16_t dim = peakOver(led, 0, 1000);

    led.progress(1000);
    // At the end: four pulses a second, at full light.
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(125));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(250));
    TEST_ASSERT_TRUE(dim < led.peakDuty());

    led.progress(500);
    const uint16_t half = peakOver(led, 0, 625);
    TEST_ASSERT_TRUE(half > dim && half < led.peakDuty());
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(625));
}

void test_progress_past_the_end_is_the_end() {
    StatusLed led;
    led.state(StatusLed::UPDATING, 0);
    led.progress(4000);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(125));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_it_starts_in_the_starting_state);
    RUN_TEST(test_the_peak_is_fifteen_percent_on_a_gamma_curve);
    RUN_TEST(test_the_brightness_moves_the_peak_on_the_same_curve);
    RUN_TEST(test_a_brightness_of_0_keeps_every_state_dark);
    RUN_TEST(test_starting_pulses_twice_a_second);
    RUN_TEST(test_working_pulses_once_a_second);
    RUN_TEST(test_a_pulse_climbs_in_sixteen_steps);
    RUN_TEST(test_repeating_a_state_does_not_restart_its_pattern);
    RUN_TEST(test_changing_state_starts_the_new_pattern_from_its_beginning);
    RUN_TEST(test_trouble_is_three_flashes_and_then_a_steady_glow);
    RUN_TEST(test_a_pattern_survives_the_millis_rollover);
    RUN_TEST(test_an_update_brightens_and_quickens_as_the_image_is_written);
    RUN_TEST(test_progress_past_the_end_is_the_end);
    return UNITY_END();
}
