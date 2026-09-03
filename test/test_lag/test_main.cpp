// First-order lag: the shape every mock's response time is built from.
#include <unity.h>
#include <cmath>
#include "sensors/mock/LaggedValue.h"

void setUp() {}
void tearDown() {}

void test_first_update_adopts_its_target() {
    LaggedValue v(60.0f);
    TEST_ASSERT_FALSE(v.primed());
    TEST_ASSERT_EQUAL_FLOAT(20.0f, v.update(20.0f, 1000));
    TEST_ASSERT_TRUE(v.primed());
}

void test_covers_63_percent_of_a_step_in_one_tau() {
    LaggedValue v(60.0f);
    v.update(0.0f, 0);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 63.2f, v.update(100.0f, 60000));
}

void test_covers_95_percent_in_three_tau() {
    LaggedValue v(10.0f);
    v.update(0.0f, 0);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 95.0f, v.update(100.0f, 30000));
}

void test_many_small_steps_match_one_big_one() {
    LaggedValue coarse(30.0f), fine(30.0f);
    coarse.update(0.0f, 0);
    fine.update(0.0f, 0);
    coarse.update(100.0f, 30000);
    for (uint32_t t = 100; t <= 30000; t += 100) fine.update(100.0f, t);
    TEST_ASSERT_FLOAT_WITHIN(0.2f, coarse.value(), fine.value());
}

void test_prime_at_starts_somewhere_other_than_the_target() {
    LaggedValue v(300.0f);
    v.primeAt(0.0f, 0);
    TEST_ASSERT_EQUAL_FLOAT(0.0f, v.value());
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 2.53f, v.update(4.0f, 300000));   // 63% of 4
}

void test_repeated_reads_at_the_same_instant_do_not_advance() {
    LaggedValue v(10.0f);
    v.update(0.0f, 0);
    float a = v.update(100.0f, 5000);
    TEST_ASSERT_EQUAL_FLOAT(a, v.update(100.0f, 5000));
}

void test_settles_on_a_constant_target() {
    LaggedValue v(5.0f);
    v.update(0.0f, 0);
    for (uint32_t t = 1000; t <= 60000; t += 1000) v.update(21.0f, t);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 21.0f, v.value());
}

void test_survives_a_millis_rollover() {
    LaggedValue v(10.0f);
    uint32_t before = 0xFFFFFFFFu - 2000;
    v.update(0.0f, before);
    float after = v.update(100.0f, before + 10000);   // wraps past zero
    TEST_ASSERT_FLOAT_WITHIN(0.5f, 63.2f, after);
}

void test_reset_makes_it_adopt_again() {
    LaggedValue v(60.0f);
    v.update(0.0f, 0);
    v.update(100.0f, 1000);
    v.reset();
    TEST_ASSERT_EQUAL_FLOAT(50.0f, v.update(50.0f, 2000));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_first_update_adopts_its_target);
    RUN_TEST(test_covers_63_percent_of_a_step_in_one_tau);
    RUN_TEST(test_covers_95_percent_in_three_tau);
    RUN_TEST(test_many_small_steps_match_one_big_one);
    RUN_TEST(test_prime_at_starts_somewhere_other_than_the_target);
    RUN_TEST(test_repeated_reads_at_the_same_instant_do_not_advance);
    RUN_TEST(test_settles_on_a_constant_target);
    RUN_TEST(test_survives_a_millis_rollover);
    RUN_TEST(test_reset_makes_it_adopt_again);
    return UNITY_END();
}
