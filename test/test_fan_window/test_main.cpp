// The PM fan's duty cycle: on for the window before each post, off after it.
#include <unity.h>
#include <cstdint>

#include "dock/FanWindow.h"

void setUp() {}
void tearDown() {}

void test_the_fan_is_off_for_the_first_part_of_the_period() {
    FanWindow w(60000, 35000);
    TEST_ASSERT_FALSE(w.shouldRun(0));
    TEST_ASSERT_FALSE(w.shouldRun(24999));
}

void test_the_fan_runs_for_the_lead_before_the_post() {
    FanWindow w(60000, 35000);
    TEST_ASSERT_TRUE(w.shouldRun(25000));
    TEST_ASSERT_TRUE(w.shouldRun(60000));
}

void test_a_late_post_leaves_the_fan_running() {
    FanWindow w(60000, 35000);
    TEST_ASSERT_TRUE(w.shouldRun(90000));
}

void test_a_lead_as_long_as_the_period_never_stops_the_fan() {
    FanWindow w(60000, 60000);
    TEST_ASSERT_TRUE(w.shouldRun(0));
    TEST_ASSERT_EQUAL_UINT32(100, w.dutyPercent());
}

void test_a_lead_longer_than_the_period_does_not_wrap() {
    FanWindow w(60000, 90000);
    TEST_ASSERT_TRUE(w.shouldRun(0));
    TEST_ASSERT_EQUAL_UINT32(100, w.dutyPercent());
}

void test_the_duty_is_the_lead_over_the_period() {
    TEST_ASSERT_EQUAL_UINT32(58, FanWindow(60000, 35000).dutyPercent());
    TEST_ASSERT_EQUAL_UINT32(50, FanWindow(60000, 30000).dutyPercent());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_fan_is_off_for_the_first_part_of_the_period);
    RUN_TEST(test_the_fan_runs_for_the_lead_before_the_post);
    RUN_TEST(test_a_late_post_leaves_the_fan_running);
    RUN_TEST(test_a_lead_as_long_as_the_period_never_stops_the_fan);
    RUN_TEST(test_a_lead_longer_than_the_period_does_not_wrap);
    RUN_TEST(test_the_duty_is_the_lead_over_the_period);
    UNITY_END();
    return 0;
}
