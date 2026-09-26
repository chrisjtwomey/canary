// The dock's status LED: a look for each state the server can set, and the
// update's own pulse.
#include <unity.h>
#include <cstdint>

#include "dock/StatusLed.h"

void setUp() {}
void tearDown() {}

void test_each_state_is_named_as_the_server_names_its_trigger() {
    const char* const names[] = {"booting", "error", "poor_air_quality", "calibrating",
                                 "running", "updating", "dark"};
    for (int st = StatusLed::BOOTING; st <= StatusLed::DARK; ++st) {
        TEST_ASSERT_EQUAL_STRING(names[st], StatusLed::stateName((StatusLed::State)st));
    }
}

void test_it_starts_in_the_booting_state() {
    StatusLed led;
    TEST_ASSERT_EQUAL_INT(StatusLed::BOOTING, led.state());
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
    for (int s = StatusLed::BOOTING; s <= StatusLed::UPDATING; ++s) {
        led.look((StatusLed::State)s, StatusLed::SOLID, 1000);
        led.state((StatusLed::State)s, 0);
        for (uint32_t t = 0; t < 3000; t += 50) {
            TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
        }
    }
}

void test_the_defaults_are_the_servers() {
    StatusLed led;
    const StatusLed::Pattern patterns[] = {StatusLed::PULSE, StatusLed::FLASH,
                                           StatusLed::DOUBLE_FLASH, StatusLed::SWELL,
                                           StatusLed::PULSE};
    const uint32_t lengths[] = {500, 1000, 2000, 4000, 1000};
    for (uint8_t s = 0; s < StatusLed::kLooks; ++s) {
        TEST_ASSERT_EQUAL_INT(patterns[s], led.pattern((StatusLed::State)s));
        TEST_ASSERT_EQUAL_UINT32(lengths[s], led.lengthMs((StatusLed::State)s));
    }
}

void test_booting_pulses_twice_a_second() {
    StatusLed led;
    led.state(StatusLed::BOOTING, 0);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(250));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(500));
    // A quarter turn each side of the peak gives the same light.
    TEST_ASSERT_EQUAL_UINT16(led.dutyAt(125), led.dutyAt(375));
}

void test_running_pulses_once_a_second() {
    StatusLed led;
    led.state(StatusLed::RUNNING, 0);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(500));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(1000));
}

// The levels a running pulse climbs through from dark to full.
static int levelsClimbed(StatusLed& led) {
    led.state(StatusLed::RUNNING, 0);
    uint16_t last = 0;
    int levels = 1;
    for (uint32_t ms = 1; ms <= 500; ++ms) {
        const uint16_t duty = led.dutyAt(ms);
        TEST_ASSERT_TRUE(duty >= last);
        if (duty != last) ++levels;
        last = duty;
    }
    return levels;
}

void test_a_pulse_climbs_in_sixteen_steps() {
    StatusLed led;
    TEST_ASSERT_EQUAL_INT(16, led.steps());
    TEST_ASSERT_EQUAL_INT(16, levelsClimbed(led));
}

void test_each_stop_of_the_smoothness_doubles_the_steps_to_smooth() {
    StatusLed led;
    // At full light, so the dimmest steps do not share an LEDC duty.
    led.brightness(100);
    const int steps[] = {4, 8, 16, 32, 64};
    for (uint8_t stop = 1; stop <= 5; ++stop) {
        led.smoothness(stop);
        TEST_ASSERT_EQUAL_INT(steps[stop - 1], levelsClimbed(led));
    }
    led.smoothness(6);
    TEST_ASSERT_EQUAL_INT(0, led.steps());
    TEST_ASSERT_TRUE(levelsClimbed(led) > 100);
}

void test_a_smoothness_out_of_range_changes_nothing() {
    StatusLed led;
    led.smoothness(0);
    led.smoothness(7);
    TEST_ASSERT_EQUAL_INT(16, led.steps());
}

void test_the_smoothness_leaves_the_full_light_where_it_is() {
    StatusLed led;
    const uint16_t peak = led.peakDuty();
    for (uint8_t stop = 1; stop <= 6; ++stop) {
        led.smoothness(stop);
        TEST_ASSERT_EQUAL_UINT16(peak, led.peakDuty());
    }
}

void test_a_blip_lights_briefly_at_the_start_of_each_cycle() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::BLIP, 5000);
    led.state(StatusLed::RUNNING, 0);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(StatusLed::kBlipMs - 1));
    for (uint32_t t = StatusLed::kBlipMs; t < 5000; t += 10) TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(5000));
}

void test_a_swell_fades_up_holds_and_fades_down_in_thirds() {
    StatusLed led;
    led.look(StatusLed::CALIBRATING, StatusLed::SWELL, 3000);
    led.state(StatusLed::CALIBRATING, 0);
    const uint16_t peak = led.peakDuty();
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_TRUE(led.dutyAt(500) > 0 && led.dutyAt(500) < peak);
    for (uint32_t t = 1000; t < 2000; t += 10) TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(t));
    TEST_ASSERT_TRUE(led.dutyAt(2500) > 0 && led.dutyAt(2500) < peak);
    TEST_ASSERT_EQUAL_UINT16(led.dutyAt(500), led.dutyAt(2500));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(3000));
}

void test_a_ramp_fades_up_over_its_cycle_then_goes_dark_at_once() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::RAMP, 2000);
    led.state(StatusLed::RUNNING, 0);
    uint16_t last = 0;
    for (uint32_t t = 0; t < 2000; t += 10) {
        TEST_ASSERT_TRUE(led.dutyAt(t) >= last);
        last = led.dutyAt(t);
    }
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(1999));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(2000));
}

void test_repeating_a_state_does_not_restart_its_pattern() {
    StatusLed led;
    led.state(StatusLed::RUNNING, 0);
    led.state(StatusLed::RUNNING, 500);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(500));
}

void test_changing_state_starts_the_new_pattern_from_its_beginning() {
    StatusLed led;
    led.state(StatusLed::RUNNING, 0);
    led.state(StatusLed::BOOTING, 500);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(500));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(750));
}

void test_a_flash_lights_the_start_of_each_cycle() {
    StatusLed led;
    led.state(StatusLed::ERROR, 0);
    const uint16_t peak = led.peakDuty();
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(StatusLed::kFlashMs - 1));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(StatusLed::kFlashMs));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(999));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(1000));
}

void test_a_short_cycle_flashes_for_half_of_it() {
    StatusLed led;
    led.look(StatusLed::ERROR, StatusLed::FLASH, 250);
    led.state(StatusLed::ERROR, 0);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(124));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(125));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(250));
}

void test_solid_and_off_hold_one_level() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::SOLID, 1000);
    led.look(StatusLed::CALIBRATING, StatusLed::OFF, 1000);
    led.state(StatusLed::RUNNING, 0);
    for (uint32_t t = 0; t < 2000; t += 10) TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(t));
    led.state(StatusLed::CALIBRATING, 0);
    for (uint32_t t = 0; t < 2000; t += 10) TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
}

void test_a_pulse_follows_its_length() {
    StatusLed led;
    led.look(StatusLed::BOOTING, StatusLed::PULSE, 4000);
    led.state(StatusLed::BOOTING, 0);
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(2000));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(4000));
}

void test_a_look_that_cannot_be_shown_is_ignored() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::FLASH, 0);
    led.look(StatusLed::RUNNING, StatusLed::kPatterns, 1000);
    led.look(StatusLed::UPDATING, StatusLed::OFF, 1000);
    TEST_ASSERT_EQUAL_INT(StatusLed::PULSE, led.pattern(StatusLed::RUNNING));
    TEST_ASSERT_EQUAL_UINT32(1000, led.lengthMs(StatusLed::RUNNING));
    led.state(StatusLed::UPDATING, 0);
    TEST_ASSERT_TRUE(led.dutyAt(500) > 0);
}

void test_a_pattern_survives_the_millis_rollover() {
    StatusLed led;
    const uint32_t start = 0xFFFFFFFF - 1000;
    led.state(StatusLed::RUNNING, start);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(start + 500));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(start + 1000));
}

void test_it_shows_the_first_state_that_holds() {
    StatusLed led;
    led.show(StatusLed::flag(StatusLed::ERROR) | StatusLed::flag(StatusLed::CALIBRATING), 0);
    TEST_ASSERT_EQUAL_INT(StatusLed::ERROR, led.state());
}

void test_a_state_without_a_look_passes_the_light_to_the_next_that_holds() {
    StatusLed led;
    led.look(StatusLed::ERROR, StatusLed::NONE, 0);
    led.show(StatusLed::flag(StatusLed::ERROR) | StatusLed::flag(StatusLed::CALIBRATING), 0);
    TEST_ASSERT_EQUAL_INT(StatusLed::CALIBRATING, led.state());
    TEST_ASSERT_EQUAL_INT(StatusLed::NONE, led.pattern(StatusLed::ERROR));
}

void test_with_no_look_among_the_states_that_hold_the_light_is_dark() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::NONE, 1000);
    led.show(StatusLed::flag(StatusLed::RUNNING), 0);
    TEST_ASSERT_EQUAL_INT(StatusLed::DARK, led.state());
    for (uint32_t t = 0; t < 2000; t += 10) TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
    led.show(0, 0);
    TEST_ASSERT_EQUAL_INT(StatusLed::DARK, led.state());
}

void test_an_update_shows_before_every_other_state() {
    StatusLed led;
    led.show(StatusLed::flag(StatusLed::BOOTING) | StatusLed::flag(StatusLed::UPDATING), 0);
    TEST_ASSERT_EQUAL_INT(StatusLed::UPDATING, led.state());
}

void test_a_look_given_back_takes_the_light_again() {
    StatusLed led;
    const uint8_t both = StatusLed::flag(StatusLed::ERROR) | StatusLed::flag(StatusLed::POOR_AIR);
    led.look(StatusLed::ERROR, StatusLed::NONE, 0);
    led.show(both, 0);
    led.look(StatusLed::ERROR, StatusLed::FLASH, 1000);
    led.show(both, 700);
    TEST_ASSERT_EQUAL_INT(StatusLed::ERROR, led.state());
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(700));
}

void test_a_triple_flash_lights_three_times_then_stays_dark_to_the_end_of_its_length() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::TRIPLE_FLASH, 1900);
    led.state(StatusLed::RUNNING, 0);
    const uint16_t peak = led.peakDuty();
    for (uint32_t start = 0; start < 900; start += 300) {
        TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(start));
        TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(start + StatusLed::kFlashMs - 1));
        TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(start + StatusLed::kFlashMs));
    }
    for (uint32_t t = 750; t < 1900; t += 10) TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(1900));
}

void test_a_double_flash_lights_twice() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::DOUBLE_FLASH, 1000);
    led.state(StatusLed::RUNNING, 0);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(300));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(600));
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(1000));
}

void test_a_double_pulse_swells_twice_then_stays_dark() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::DOUBLE_PULSE, 1600);
    led.state(StatusLed::RUNNING, 0);
    const uint16_t peak = led.peakDuty();
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(0));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(150));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(300));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(450));
    for (uint32_t t = 600; t < 1600; t += 10) TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(t));
    TEST_ASSERT_EQUAL_UINT16(peak, led.dutyAt(1750));
}

void test_a_triple_pulse_swells_three_times() {
    StatusLed led;
    led.look(StatusLed::RUNNING, StatusLed::TRIPLE_PULSE, 1900);
    led.state(StatusLed::RUNNING, 0);
    TEST_ASSERT_EQUAL_UINT16(led.peakDuty(), led.dutyAt(750));
    TEST_ASSERT_EQUAL_UINT16(0, led.dutyAt(900));
}

void test_a_double_or_triple_needs_its_group_and_a_gap_of_one_step() {
    TEST_ASSERT_EQUAL_UINT32(900, StatusLed::minLengthMs(StatusLed::DOUBLE_FLASH));
    TEST_ASSERT_EQUAL_UINT32(900, StatusLed::minLengthMs(StatusLed::DOUBLE_PULSE));
    TEST_ASSERT_EQUAL_UINT32(1200, StatusLed::minLengthMs(StatusLed::TRIPLE_FLASH));
    TEST_ASSERT_EQUAL_UINT32(1200, StatusLed::minLengthMs(StatusLed::TRIPLE_PULSE));
    TEST_ASSERT_EQUAL_UINT32(250, StatusLed::minLengthMs(StatusLed::FLASH));
    TEST_ASSERT_EQUAL_UINT32(250, StatusLed::minLengthMs(StatusLed::PULSE));
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
    RUN_TEST(test_it_starts_in_the_booting_state);
    RUN_TEST(test_each_state_is_named_as_the_server_names_its_trigger);
    RUN_TEST(test_the_peak_is_fifteen_percent_on_a_gamma_curve);
    RUN_TEST(test_the_brightness_moves_the_peak_on_the_same_curve);
    RUN_TEST(test_a_brightness_of_0_keeps_every_state_dark);
    RUN_TEST(test_the_defaults_are_the_servers);
    RUN_TEST(test_booting_pulses_twice_a_second);
    RUN_TEST(test_running_pulses_once_a_second);
    RUN_TEST(test_a_pulse_climbs_in_sixteen_steps);
    RUN_TEST(test_each_stop_of_the_smoothness_doubles_the_steps_to_smooth);
    RUN_TEST(test_a_smoothness_out_of_range_changes_nothing);
    RUN_TEST(test_the_smoothness_leaves_the_full_light_where_it_is);
    RUN_TEST(test_a_blip_lights_briefly_at_the_start_of_each_cycle);
    RUN_TEST(test_a_swell_fades_up_holds_and_fades_down_in_thirds);
    RUN_TEST(test_a_ramp_fades_up_over_its_cycle_then_goes_dark_at_once);
    RUN_TEST(test_repeating_a_state_does_not_restart_its_pattern);
    RUN_TEST(test_changing_state_starts_the_new_pattern_from_its_beginning);
    RUN_TEST(test_a_flash_lights_the_start_of_each_cycle);
    RUN_TEST(test_a_short_cycle_flashes_for_half_of_it);
    RUN_TEST(test_solid_and_off_hold_one_level);
    RUN_TEST(test_a_pulse_follows_its_length);
    RUN_TEST(test_a_look_that_cannot_be_shown_is_ignored);
    RUN_TEST(test_a_pattern_survives_the_millis_rollover);
    RUN_TEST(test_a_triple_flash_lights_three_times_then_stays_dark_to_the_end_of_its_length);
    RUN_TEST(test_a_double_flash_lights_twice);
    RUN_TEST(test_a_double_pulse_swells_twice_then_stays_dark);
    RUN_TEST(test_a_triple_pulse_swells_three_times);
    RUN_TEST(test_a_double_or_triple_needs_its_group_and_a_gap_of_one_step);
    RUN_TEST(test_it_shows_the_first_state_that_holds);
    RUN_TEST(test_a_state_without_a_look_passes_the_light_to_the_next_that_holds);
    RUN_TEST(test_with_no_look_among_the_states_that_hold_the_light_is_dark);
    RUN_TEST(test_an_update_shows_before_every_other_state);
    RUN_TEST(test_a_look_given_back_takes_the_light_again);
    RUN_TEST(test_an_update_brightens_and_quickens_as_the_image_is_written);
    RUN_TEST(test_progress_past_the_end_is_the_end);
    return UNITY_END();
}
