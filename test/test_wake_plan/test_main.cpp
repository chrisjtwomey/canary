// The display's wake timing: a page at once after a real start, then on the
// server's wait, backing off across failures, and a sync between pages when
// the server names one.
#include <unity.h>
#include <cstdint>

#include "display/WakePlan.h"

static const uint32_t kNow = 1790000000;   // UTC seconds, in 2026

static uint32_t doubling(int step) { return 60u << (step - 1); }

void setUp() {}
void tearDown() {}

void test_a_real_start_fetches_a_page_at_once() {
    WakePlan p = {};
    TEST_ASSERT_TRUE(pageDue(p, kNow));
    TEST_ASSERT_FALSE(syncDue(p, kNow));
    TEST_ASSERT_EQUAL_UINT32(0, nextWake(p));
}

void test_a_page_waits_the_seconds_the_server_sent() {
    WakePlan p = {};
    pageFetched(p, kNow, 120, 300);
    TEST_ASSERT_FALSE(pageDue(p, kNow + 119));
    TEST_ASSERT_TRUE(pageDue(p, kNow + 120));
}

void test_a_page_without_a_wait_uses_the_fallback() {
    WakePlan p = {};
    pageFetched(p, kNow, 0, 300);
    TEST_ASSERT_FALSE(pageDue(p, kNow + 299));
    TEST_ASSERT_TRUE(pageDue(p, kNow + 300));
}

void test_failures_back_off_and_a_page_resets() {
    WakePlan p = {};
    TEST_ASSERT_EQUAL_UINT32(60, pageFailed(p, kNow, doubling));
    TEST_ASSERT_EQUAL_INT(1, p.step);
    TEST_ASSERT_FALSE(pageDue(p, kNow + 59));
    TEST_ASSERT_TRUE(pageDue(p, kNow + 60));
    TEST_ASSERT_EQUAL_UINT32(120, pageFailed(p, kNow + 60, doubling));
    TEST_ASSERT_EQUAL_UINT32(240, pageFailed(p, kNow + 180, doubling));
    TEST_ASSERT_EQUAL_INT(3, p.step);
    pageFetched(p, kNow + 420, 300, 300);
    TEST_ASSERT_EQUAL_INT(0, p.step);
    TEST_ASSERT_EQUAL_UINT32(60, pageFailed(p, kNow + 720, doubling));
}

void test_a_sync_before_the_page_wakes_the_head_first() {
    WakePlan p = {};
    pageFetched(p, kNow, 3600, 300);
    synced(p, kNow, 1800);
    TEST_ASSERT_EQUAL_UINT32(kNow + 1800, nextWake(p));
    TEST_ASSERT_TRUE(syncDue(p, kNow + 1800));
    TEST_ASSERT_FALSE(pageDue(p, kNow + 1800));
    TEST_ASSERT_TRUE(wakeDue(p, kNow + 1800));
}

void test_a_page_before_the_sync_wakes_the_head_first() {
    WakePlan p = {};
    pageFetched(p, kNow, 300, 300);
    synced(p, kNow, 1800);
    TEST_ASSERT_EQUAL_UINT32(kNow + 300, nextWake(p));
}

void test_a_sync_on_the_page_slot_is_one_wake() {
    WakePlan p = {};
    pageFetched(p, kNow, 300, 300);
    synced(p, kNow, 300);
    TEST_ASSERT_EQUAL_UINT32(kNow + 300, nextWake(p));
    TEST_ASSERT_TRUE(pageDue(p, kNow + 300));
    TEST_ASSERT_TRUE(syncDue(p, kNow + 300));
}

void test_without_a_sync_the_head_wakes_for_pages_only() {
    WakePlan p = {};
    pageFetched(p, kNow, 300, 300);
    synced(p, kNow, 1800);
    synced(p, kNow + 1800, 0);
    TEST_ASSERT_FALSE(syncDue(p, kNow + 99999));
    TEST_ASSERT_EQUAL_UINT32(kNow + 300, nextWake(p));
}

void test_seconds_until_floors_at_zero() {
    TEST_ASSERT_EQUAL_UINT32(120, secondsUntil(kNow + 120, kNow));
    TEST_ASSERT_EQUAL_UINT32(0, secondsUntil(kNow, kNow));
    TEST_ASSERT_EQUAL_UINT32(0, secondsUntil(kNow - 5, kNow));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_a_real_start_fetches_a_page_at_once);
    RUN_TEST(test_a_page_waits_the_seconds_the_server_sent);
    RUN_TEST(test_a_page_without_a_wait_uses_the_fallback);
    RUN_TEST(test_failures_back_off_and_a_page_resets);
    RUN_TEST(test_a_sync_before_the_page_wakes_the_head_first);
    RUN_TEST(test_a_page_before_the_sync_wakes_the_head_first);
    RUN_TEST(test_a_sync_on_the_page_slot_is_one_wake);
    RUN_TEST(test_without_a_sync_the_head_wakes_for_pages_only);
    RUN_TEST(test_seconds_until_floors_at_zero);
    return UNITY_END();
}
