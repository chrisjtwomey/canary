// When an image on trial is given up: three failures in a row.
#include <unity.h>

#include "dock/Trial.h"

void setUp() {}
void tearDown() {}

void test_the_third_failure_in_a_row_rolls_back() {
    Trial t;
    t.begin(true);
    TEST_ASSERT_FALSE(t.failed());
    TEST_ASSERT_FALSE(t.failed());
    TEST_ASSERT_TRUE(t.failed());
}

void test_a_success_starts_the_count_again() {
    Trial t;
    t.begin(true);
    t.failed();
    t.failed();
    t.succeeded();
    TEST_ASSERT_FALSE(t.failed());
    TEST_ASSERT_FALSE(t.failed());
    TEST_ASSERT_TRUE(t.failed());
    TEST_ASSERT_TRUE(t.pending());
}

void test_an_image_not_on_trial_never_rolls_back() {
    Trial t;
    t.begin(false);
    for (int i = 0; i < 10; i++) TEST_ASSERT_FALSE(t.failed());
}

void test_a_passed_trial_ignores_later_failures() {
    Trial t;
    t.begin(true);
    t.failed();
    t.failed();
    t.passed();
    TEST_ASSERT_FALSE(t.pending());
    for (int i = 0; i < 10; i++) TEST_ASSERT_FALSE(t.failed());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_third_failure_in_a_row_rolls_back);
    RUN_TEST(test_a_success_starts_the_count_again);
    RUN_TEST(test_an_image_not_on_trial_never_rolls_back);
    RUN_TEST(test_a_passed_trial_ignores_later_failures);
    UNITY_END();
    return 0;
}
