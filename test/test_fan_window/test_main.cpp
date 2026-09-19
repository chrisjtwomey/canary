// The PM fan's duty cycle: on for the window before each post, off after it.
#include <unity.h>
#include <cstdint>

#include "dock/FanWindow.h"

void setUp() {}
void tearDown() {}

void test_the_fan_is_off_until_the_window_before_the_post() {
    FanWindow w(35000);
    TEST_ASSERT_FALSE(w.shouldRun(300000));
    TEST_ASSERT_FALSE(w.shouldRun(35001));
}

void test_the_fan_runs_for_the_lead_before_the_post() {
    FanWindow w(35000);
    TEST_ASSERT_TRUE(w.shouldRun(35000));
    TEST_ASSERT_TRUE(w.shouldRun(1));
}

void test_a_post_that_is_due_or_late_leaves_the_fan_running() {
    TEST_ASSERT_TRUE(FanWindow(35000).shouldRun(0));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_fan_is_off_until_the_window_before_the_post);
    RUN_TEST(test_the_fan_runs_for_the_lead_before_the_post);
    RUN_TEST(test_a_post_that_is_due_or_late_leaves_the_fan_running);
    UNITY_END();
    return 0;
}
