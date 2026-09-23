// A sensor that did not start, or has stopped, is started again before the
// next slot. The drivers run against the fake parts: a cable is pulled by
// taking a part off the fake bus, and a power cut puts the part back the way
// the real one comes back.
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

// The dock's cadence: a reading on each slot, and the PM fan, with any
// restart, 35 s before it.
static const uint32_t kSlotMs = 300000;
static const uint32_t kLeadMs = 35000;

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
    uint32_t       slotAt = 0;

    Rig()
        : shtc3(*bus, *clk), scd41(*bus, *clk), pm(*bus, *clk, setFanLine), bme(*bus, *clk),
          suite(*clk, shtc3, scd41, pm, bme) {
        bmePart.loadCalibration();
        bus->attach(Shtc3Driver::kAddress, &shtc3Part);
        bus->attach(Scd41Driver::kAddress, &scd41Part);
        bus->attach(Pmsa003iDriver::kAddress, &pmPart);
        bus->attach(Bme688Driver::kAddress, &bmePart);
    }

    // `n` slots as the dock runs them: restart what has stopped and start the
    // fan, then 35 s later take the reading and stop the fan.
    void runSlots(int n) {
        for (int i = 0; i < n; ++i) {
            slotAt += kSlotMs;
            clk->now = slotAt - kLeadMs;
            suite.restartFailed();
            suite.setFanEnabled(true);
            clk->now = slotAt;
            last = suite.sample(1757443200);
            suite.setFanEnabled(false);
        }
    }
};

void test_a_healthy_bench_is_never_restarted() {
    Rig rig;
    TEST_ASSERT_TRUE(rig.suite.begin());
    rig.runSlots(12);
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
    rig.runSlots(1);
    TEST_ASSERT_FALSE(rig.last.shtc3Valid);

    bus->setPresent(Shtc3Driver::kAddress, true);
    rig.runSlots(1);
    TEST_ASSERT_TRUE(rig.suite.shtc3Present());
    TEST_ASSERT_TRUE_MESSAGE(rig.last.shtc3Valid, "started before the slot, read at it");
}

void test_retries_back_off_while_a_sensor_stays_away() {
    Rig rig;
    bus->setPresent(Scd41Driver::kAddress, false);
    rig.suite.begin();
    rig.runSlots(20);
    TEST_ASSERT_GREATER_THAN_UINT32(1, rig.suite.restarts());
    TEST_ASSERT_LESS_THAN_UINT32_MESSAGE(20, rig.suite.restarts(), "not one every slot");
    TEST_ASSERT_FALSE(rig.suite.scd41Present());
    TEST_ASSERT_TRUE_MESSAGE(rig.last.shtc3Valid, "the others carry on");
}

void test_an_scd41_back_from_a_power_cut_is_set_measuring_again() {
    Rig rig;
    rig.suite.begin();
    rig.runSlots(2);
    TEST_ASSERT_TRUE(rig.last.scd41Valid);

    // Pulled and pushed back between two slots: the part is idle and answers,
    // but has nothing to report until it is told to measure.
    rig.scd41Part.powerCycle();
    rig.runSlots(1);
    TEST_ASSERT_FALSE(rig.last.scd41Valid);
    TEST_ASSERT_FALSE_MESSAGE(rig.suite.scd41Present(), "one slot with nothing marks it stopped");

    rig.runSlots(1);
    TEST_ASSERT_EQUAL_UINT32(1, rig.suite.restarts());
    TEST_ASSERT_TRUE(rig.scd41Part.periodic);
    TEST_ASSERT_TRUE_MESSAGE(rig.last.scd41Valid, "measuring again by the slot after");
}

void test_a_bme688_that_lost_its_settings_is_started_again() {
    Rig rig;
    rig.suite.begin();
    rig.runSlots(2);
    TEST_ASSERT_TRUE(rig.last.bme688Valid);

    rig.bmePart.powerCycle();
    rig.runSlots(1);
    TEST_ASSERT_FALSE_MESSAGE(rig.last.bme688Valid, "a cycle on the reset settings is not a reading");

    rig.runSlots(1);
    TEST_ASSERT_EQUAL_UINT32(1, rig.suite.restarts());
    TEST_ASSERT_TRUE(rig.last.bme688Valid);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(2, rig.bmePart.regs[FakeBme688::kRegCtrlMeas] >> 5,
                                    "2x temperature oversampling again");
}

void test_a_pm_module_back_from_a_power_cut_reads_at_the_next_slot() {
    Rig rig;
    rig.suite.begin();
    rig.runSlots(2);
    TEST_ASSERT_TRUE(rig.last.pmValid);

    bus->setPresent(Pmsa003iDriver::kAddress, false);
    rig.runSlots(1);
    TEST_ASSERT_FALSE(rig.suite.pmPresent());

    // Back in: started with the fan 35 s before the slot, so its 30 s
    // warm-up is over when the slot reads it.
    bus->setPresent(Pmsa003iDriver::kAddress, true);
    rig.runSlots(1);
    TEST_ASSERT_TRUE(rig.suite.pmPresent());
    TEST_ASSERT_TRUE(rig.last.pmValid);
}

void test_an_shtc3_back_from_a_power_cut_needs_no_restart() {
    Rig rig;
    rig.suite.begin();
    rig.runSlots(2);
    rig.shtc3Part.powerCycle();
    rig.runSlots(1);
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
    RUN_TEST(test_a_pm_module_back_from_a_power_cut_reads_at_the_next_slot);
    RUN_TEST(test_an_shtc3_back_from_a_power_cut_needs_no_restart);
    return UNITY_END();
}
