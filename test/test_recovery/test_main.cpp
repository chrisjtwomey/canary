// A sensor that did not start, or has stopped, is started again from the
// loop. The drivers run against the fake parts: a cable is pulled by taking a
// part off the fake bus, and a power cut puts the part back the way the real
// one comes back.
#include <unity.h>

#include "../test_drivers/FakeParts.h"
#include "sensors/Bme688Driver.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Scd41Driver.h"
#include "sensors/SensorSuite.h"
#include "sensors/Shtc3Driver.h"

class FakeClock : public IClock {
public:
    uint32_t now = 0;
    uint32_t millis() const override { return now; }
    void waitMs(uint32_t ms) override { now += ms; }
};

static bool fanLineHigh = false;
static void setFanLine(bool high) { fanLineHigh = high; }

// The main image's cadence.
static const uint32_t kSampleMs = 5000;

static FakeI2cBus* bus;
static FakeClock*  clk;

void setUp() {
    bus = new FakeI2cBus();
    clk = new FakeClock();
    fanLineHigh = false;
}

void tearDown() {
    delete bus;
    delete clk;
}

// The four parts, their drivers, and the suite over them, wired as the board is.
struct Rig {
    FakeShtc3    shtc3Part;
    FakeScd41    scd41Part;
    FakePmsa003i pmPart;
    FakeBme688   bmePart;

    Shtc3Driver    shtc3;
    Scd41Driver    scd41;
    Pmsa003iDriver pm;
    Bme688Driver   bme;
    SensorSuite    suite;
    Readings       last = {};

    Rig()
        : shtc3(*bus, *clk), scd41(*bus, *clk), pm(*bus, *clk, setFanLine), bme(*bus, *clk),
          suite(*clk, shtc3, scd41, pm, bme) {
        bmePart.loadCalibration();
        bus->attach(Shtc3Driver::kAddress, &shtc3Part);
        bus->attach(Scd41Driver::kAddress, &scd41Part);
        bus->attach(Pmsa003iDriver::kAddress, &pmPart);
        bus->attach(Bme688Driver::kAddress, &bmePart);
    }

    // The loop, as main.cpp runs it, until the clock reaches `ms`: every
    // 5 s, restart what has failed, then sample.
    void runUntil(uint32_t ms) {
        while (clk->now < ms) {
            clk->now += kSampleMs;
            suite.restartFailed();
            last = suite.sample(1757443200);
        }
    }
};

void test_a_healthy_bench_is_never_restarted() {
    Rig rig;
    TEST_ASSERT_TRUE(rig.suite.begin());
    rig.runUntil(10 * 60000);
    TEST_ASSERT_EQUAL_UINT32(0, rig.suite.restarts());
    TEST_ASSERT_TRUE(rig.last.shtc3Valid);
    TEST_ASSERT_TRUE(rig.last.scd41Valid);
    TEST_ASSERT_TRUE(rig.last.pmValid);
    TEST_ASSERT_TRUE(rig.last.bme688Valid);
}

void test_a_sensor_missing_at_start_joins_once_plugged_in() {
    Rig rig;
    bus->setPresent(Shtc3Driver::kAddress, false);
    TEST_ASSERT_FALSE(rig.suite.begin());
    TEST_ASSERT_FALSE(rig.suite.shtc3Present());

    rig.runUntil(10000);
    bus->setPresent(Shtc3Driver::kAddress, true);
    rig.runUntil(SensorSuite::kRetryFirstMs - 1000);
    TEST_ASSERT_FALSE_MESSAGE(rig.last.shtc3Valid, "not tried again before its retry is due");

    rig.runUntil(SensorSuite::kRetryFirstMs + 2 * kSampleMs);
    TEST_ASSERT_TRUE(rig.suite.shtc3Present());
    TEST_ASSERT_TRUE(rig.last.shtc3Valid);
    TEST_ASSERT_EQUAL_UINT32(1, rig.suite.restarts());
}

void test_retries_back_off_while_a_sensor_stays_away() {
    Rig rig;
    bus->setPresent(Scd41Driver::kAddress, false);
    rig.suite.begin();
    rig.runUntil(20 * 60000);
    // 30 s after the start, then 60, 120, 240 and 480 s apart: five tries in
    // twenty minutes, not one every sample.
    TEST_ASSERT_UINT32_WITHIN(1, 5, rig.suite.restarts());
    TEST_ASSERT_FALSE(rig.suite.scd41Present());
    TEST_ASSERT_TRUE_MESSAGE(rig.last.shtc3Valid, "the others carry on");
}

void test_an_scd41_back_from_a_power_cut_is_set_measuring_again() {
    Rig rig;
    rig.suite.begin();
    rig.runUntil(60000);
    TEST_ASSERT_TRUE(rig.last.scd41Valid);

    // Pulled and pushed back between two samples: the part is idle and
    // answers, but has nothing to report until it is told to measure.
    rig.scd41Part.powerCycle();
    rig.runUntil(clk->now + SensorSuite::kStoppedAfterMs + 2 * kSampleMs);

    TEST_ASSERT_EQUAL_UINT32(1, rig.suite.restarts());
    TEST_ASSERT_TRUE(rig.scd41Part.periodic);
    TEST_ASSERT_TRUE(rig.last.scd41Valid);
}

void test_a_bme688_that_lost_its_settings_is_started_again() {
    Rig rig;
    rig.suite.begin();
    rig.runUntil(60000);
    TEST_ASSERT_TRUE(rig.last.bme688Valid);

    rig.bmePart.powerCycle();
    rig.runUntil(clk->now + kSampleMs);
    TEST_ASSERT_FALSE_MESSAGE(rig.last.bme688Valid, "a cycle on the reset settings is not a reading");

    rig.runUntil(clk->now + SensorSuite::kStoppedAfterMs + kSampleMs);
    TEST_ASSERT_EQUAL_UINT32(1, rig.suite.restarts());
    TEST_ASSERT_TRUE(rig.last.bme688Valid);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(2, rig.bmePart.regs[FakeBme688::kRegCtrlMeas] >> 5,
                                    "2x temperature oversampling again");
}

void test_a_pm_module_back_from_a_power_cut_warms_up_before_it_counts() {
    Rig rig;
    rig.suite.begin();
    rig.runUntil(60000);
    TEST_ASSERT_TRUE(rig.last.pmValid);

    bus->setPresent(Pmsa003iDriver::kAddress, false);
    rig.runUntil(85000);
    TEST_ASSERT_FALSE(rig.suite.pmPresent());

    // Back in: the module answers at once, but the fan starts from rest.
    bus->setPresent(Pmsa003iDriver::kAddress, true);
    uint32_t backAt = clk->now;
    bool validTooSoon = false;
    while (clk->now < backAt + Pmsa003iDriver::kWarmupMs) {
        rig.runUntil(clk->now + kSampleMs);
        validTooSoon = validTooSoon || rig.last.pmValid;
    }
    TEST_ASSERT_FALSE_MESSAGE(validTooSoon, "warm-up counts are believable and wrong");

    rig.runUntil(backAt + 3 * 60000);
    TEST_ASSERT_TRUE(rig.last.pmValid);
    TEST_ASSERT_TRUE(fanLineHigh);
}

void test_an_shtc3_back_from_a_power_cut_needs_no_restart() {
    Rig rig;
    rig.suite.begin();
    rig.runUntil(60000);
    rig.shtc3Part.powerCycle();
    rig.runUntil(120000);
    TEST_ASSERT_TRUE(rig.last.shtc3Valid);
    TEST_ASSERT_EQUAL_UINT32(0, rig.suite.restarts());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_a_healthy_bench_is_never_restarted);
    RUN_TEST(test_a_sensor_missing_at_start_joins_once_plugged_in);
    RUN_TEST(test_retries_back_off_while_a_sensor_stays_away);
    RUN_TEST(test_an_scd41_back_from_a_power_cut_is_set_measuring_again);
    RUN_TEST(test_a_bme688_that_lost_its_settings_is_started_again);
    RUN_TEST(test_a_pm_module_back_from_a_power_cut_warms_up_before_it_counts);
    RUN_TEST(test_an_shtc3_back_from_a_power_cut_needs_no_restart);
    return UNITY_END();
}
