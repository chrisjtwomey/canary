// The awake loop's fetch timing: due at once, then on the server's wait,
// backing off across failures, surviving the millis() rollover.
#include <unity.h>
#include <cstdint>

#include "net/RefreshTimer.h"

static uint32_t doubling(int step) { return 60u << (step - 1); }

void setUp() {}
void tearDown() {}

void test_first_fetch_is_due_at_once() {
    RefreshTimer t(300);
    TEST_ASSERT_TRUE(t.due(0));
    TEST_ASSERT_TRUE(t.due(123456));
}

void test_success_waits_the_seconds_the_server_sent() {
    RefreshTimer t(300);
    t.succeeded(1000, 120);
    TEST_ASSERT_FALSE(t.due(1000 + 119999));
    TEST_ASSERT_TRUE(t.due(1000 + 120000));
}

void test_success_without_a_wait_uses_the_fallback() {
    RefreshTimer t(300);
    t.succeeded(0, 0);
    TEST_ASSERT_FALSE(t.due(299999));
    TEST_ASSERT_TRUE(t.due(300000));
}

void test_failures_back_off_and_success_resets() {
    RefreshTimer t(300);
    TEST_ASSERT_EQUAL_UINT32(60, t.failed(0, doubling));
    TEST_ASSERT_EQUAL_INT(1, t.step());
    TEST_ASSERT_FALSE(t.due(59999));
    TEST_ASSERT_TRUE(t.due(60000));
    TEST_ASSERT_EQUAL_UINT32(120, t.failed(60000, doubling));
    TEST_ASSERT_EQUAL_UINT32(240, t.failed(180000, doubling));
    TEST_ASSERT_EQUAL_INT(3, t.step());
    t.succeeded(420000, 300);
    TEST_ASSERT_EQUAL_INT(0, t.step());
    TEST_ASSERT_EQUAL_UINT32(60, t.failed(720000, doubling));
}

void test_millis_rollover_does_not_stall_the_loop() {
    RefreshTimer t(300);
    uint32_t nearEnd = 0xFFFFFFFFu - 1000;
    t.succeeded(nearEnd, 10);           // due 9 s after the wrap
    TEST_ASSERT_FALSE(t.due(nearEnd + 500));
    TEST_ASSERT_FALSE(t.due(5000));     // wrapped, 6 s past zero
    TEST_ASSERT_TRUE(t.due(9000));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_first_fetch_is_due_at_once);
    RUN_TEST(test_success_waits_the_seconds_the_server_sent);
    RUN_TEST(test_success_without_a_wait_uses_the_fallback);
    RUN_TEST(test_failures_back_off_and_success_resets);
    RUN_TEST(test_millis_rollover_does_not_stall_the_loop);
    return UNITY_END();
}
