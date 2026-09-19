// The dock's clock, taken from the server, and when it next posts.
#include <unity.h>
#include <cstdint>

#include "dock/PostTimer.h"
#include "net/ServerClock.h"

void setUp() {}
void tearDown() {}

// ─── ServerClock ─────────────────────────────────────────────────────────

void test_the_clock_is_unknown_until_the_server_answers() {
    ServerClock c;
    TEST_ASSERT_FALSE(c.known());
    TEST_ASSERT_EQUAL_UINT32(0, c.epochAt(5000));
    c.sync(0, 5000);
    TEST_ASSERT_FALSE_MESSAGE(c.known(), "a response without the header says nothing");
}

void test_the_clock_runs_on_from_the_sync_and_back_before_it() {
    ServerClock c;
    c.sync(1760000000, 90000);
    TEST_ASSERT_EQUAL_UINT32(1760000000, c.epochAt(90000));
    TEST_ASSERT_EQUAL_UINT32(1760000060, c.epochAt(150000));
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(1759999910, c.epochAt(0), "a reading taken before the sync");
    TEST_ASSERT_EQUAL_UINT32(1759999999, c.epochAt(89500));
}

void test_the_clock_holds_across_the_uptime_wrapping() {
    ServerClock c;
    c.sync(1760000000, 0xFFFFF000u);
    TEST_ASSERT_EQUAL_UINT32(1760000010, c.epochAt(0xFFFFF000u + 10000));   // wrapped past zero
}

void test_each_sync_moves_the_clock() {
    ServerClock c;
    c.sync(1760000000, 0);
    c.sync(1760000302, 300000);
    TEST_ASSERT_EQUAL_UINT32(1760000302, c.epochAt(300000));
}

// ─── PostTimer ───────────────────────────────────────────────────────────

void test_the_first_post_follows_the_warm_up() {
    PostTimer t(300000);
    t.postAt(1000, 35000);
    TEST_ASSERT_FALSE(t.due(35999));
    TEST_ASSERT_EQUAL_UINT32(1, t.untilMs(35999));
    TEST_ASSERT_TRUE(t.due(36000));
    TEST_ASSERT_EQUAL_UINT32(0, t.untilMs(40000));
}

void test_the_server_moves_the_next_post_to_its_slot() {
    PostTimer t(300000);
    t.postAt(0, 35000);
    t.taken(35000);
    t.answered(35500, 265);
    TEST_ASSERT_EQUAL_UINT32(265000, t.untilMs(35500));
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(300000, t.intervalMs(),
                                     "a reading off the slots does not set the interval");
}

void test_the_gap_between_two_slots_becomes_the_interval() {
    PostTimer t(300000);
    t.answered(0, 60);            // on the slots
    t.taken(60000);               // at a slot
    t.answered(60400, 1800);      // the quiet window has begun
    TEST_ASSERT_EQUAL_UINT32(1800000, t.intervalMs());
}

void test_a_failed_post_keeps_the_last_interval() {
    PostTimer t(300000);
    t.answered(0, 60);
    t.taken(60000);
    t.answered(60400, 1800);
    t.taken(1860400);             // no answer to this one
    TEST_ASSERT_EQUAL_UINT32(1800000, t.untilMs(1860400));
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(1800000, t.intervalMs(), "only an answer changes it");
}

void test_an_answer_without_a_slot_changes_nothing() {
    PostTimer t(300000);
    t.postAt(0, 35000);
    t.answered(1000, 0);
    TEST_ASSERT_EQUAL_UINT32(34000, t.untilMs(1000));
}

void test_the_timer_holds_across_the_uptime_wrapping() {
    PostTimer t(300000);
    t.postAt(0xFFFFF000u, 10000);
    TEST_ASSERT_FALSE(t.due(0xFFFFF000u + 9999));
    TEST_ASSERT_TRUE(t.due(0xFFFFF000u + 10000));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_clock_is_unknown_until_the_server_answers);
    RUN_TEST(test_the_clock_runs_on_from_the_sync_and_back_before_it);
    RUN_TEST(test_the_clock_holds_across_the_uptime_wrapping);
    RUN_TEST(test_each_sync_moves_the_clock);
    RUN_TEST(test_the_first_post_follows_the_warm_up);
    RUN_TEST(test_the_server_moves_the_next_post_to_its_slot);
    RUN_TEST(test_the_gap_between_two_slots_becomes_the_interval);
    RUN_TEST(test_a_failed_post_keeps_the_last_interval);
    RUN_TEST(test_an_answer_without_a_slot_changes_nothing);
    RUN_TEST(test_the_timer_holds_across_the_uptime_wrapping);
    UNITY_END();
    return 0;
}
