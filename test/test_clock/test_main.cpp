// delayForMs against a delay that runs short, as the ESP32's does while the
// chip light-sleeps between scheduler ticks.
#include <unity.h>
#include <cstdint>

#include "sensors/IClock.h"

void setUp() {}
void tearDown() {}

// A clock whose delay credits back less time than asked, as ticks do under
// light sleep; shortBy caps at just under the whole delay.
struct ShortClock {
    uint32_t now = 0;
    uint32_t shortBy = 0;
    int      delays = 0;

    void delay(uint32_t ms) {
        ++delays;
        const uint32_t cut = shortBy < ms ? shortBy : ms - 1;
        now += ms - cut;
    }
};

void test_a_wait_lasts_the_asked_milliseconds_even_when_each_delay_runs_short() {
    ShortClock c;
    c.shortBy = 51;   // the worst measured shortfall of a BME688 wait
    const uint32_t start = c.now;
    delayForMs(1986, [&] { return c.now; }, [&](uint32_t ms) { c.delay(ms); });
    TEST_ASSERT_GREATER_OR_EQUAL_UINT32(1986, c.now - start);
    TEST_ASSERT_GREATER_THAN_INT(1, c.delays);
}

void test_an_exact_delay_waits_once() {
    ShortClock c;
    delayForMs(1000, [&] { return c.now; }, [&](uint32_t ms) { c.delay(ms); });
    TEST_ASSERT_EQUAL_INT(1, c.delays);
    TEST_ASSERT_EQUAL_UINT32(1000, c.now);
}

void test_a_wait_of_zero_never_delays() {
    ShortClock c;
    delayForMs(0, [&] { return c.now; }, [&](uint32_t ms) { c.delay(ms); });
    TEST_ASSERT_EQUAL_INT(0, c.delays);
}

void test_a_wait_across_the_clock_rollover_still_lasts() {
    ShortClock c;
    c.now = 0xFFFFFF00u;   // rolls over 256 ms in
    c.shortBy = 30;
    const uint32_t start = c.now;
    delayForMs(1000, [&] { return c.now; }, [&](uint32_t ms) { c.delay(ms); });
    TEST_ASSERT_GREATER_OR_EQUAL_UINT32(1000, c.now - start);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_a_wait_lasts_the_asked_milliseconds_even_when_each_delay_runs_short);
    RUN_TEST(test_an_exact_delay_waits_once);
    RUN_TEST(test_a_wait_of_zero_never_delays);
    RUN_TEST(test_a_wait_across_the_clock_rollover_still_lasts);
    return UNITY_END();
}
