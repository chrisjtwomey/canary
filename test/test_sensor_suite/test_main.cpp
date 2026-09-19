// SensorSuite runs the sampling protocol against interfaces. These tests
// drive it with the mocks, and with hand-written stubs that are not the
// mocks, which is what proves the seam is real: the production sequence is
// the code under test, not a copy of it.
#include <unity.h>

#include "sensors/SensorSuite.h"
#include "sensors/mock/EnvModel.h"
#include "sensors/mock/MockBme688.h"
#include "sensors/mock/MockPmsa003i.h"
#include "sensors/mock/MockScd41.h"
#include "sensors/mock/MockShtc3.h"

static const uint32_t kNoon = 1756857600 + 12 * 3600;

// A clock the test drives. waitMs moves it, so the sensors see time pass
// exactly as they would on the device.
class FakeClock : public IClock {
public:
    uint32_t now = 0;
    uint32_t waited = 0;
    uint32_t millis() const override { return now; }
    void waitMs(uint32_t ms) override { now += ms; waited += ms; }
    void advance(uint32_t ms) { now += ms; }
};

// Records the pressure the suite feeds forward from the BME688.
class SpyScd41 : public MockScd41 {
public:
    explicit SpyScd41(EnvModel& room) : MockScd41(room) {}
    uint32_t lastPressurePa = 0;
    int pressureCalls = 0;
    bool setAmbientPressure(uint32_t pa) override {
        lastPressurePa = pa;
        ++pressureCalls;
        return MockScd41::setAmbientPressure(pa);
    }
    bool getAutomaticSelfCalibration(bool& on) override { on = true; return true; }
    bool getTemperatureOffset(float& degC) override { degC = 4.0f; return true; }
};

// Not a mock of the real part: just enough of the interface to prove the
// suite copes with a sensor that never starts.
class DeadShtc3 : public IShtc3 {
public:
    bool begin(uint32_t) override { return false; }
    bool wakeup(uint32_t) override { TEST_FAIL_MESSAGE("must not talk to a sensor that failed to start"); return false; }
    bool sleep() override { TEST_FAIL_MESSAGE("must not talk to a sensor that failed to start"); return false; }
    bool measure(uint32_t, bool) override { return false; }
    bool read(uint32_t, Shtc3Data&) override { return false; }
    uint16_t readId() override { return 0; }
};

// Fails the first frame read of every sample, succeeds on the retry.
class FlakyPm : public IPmsa003i {
public:
    int reads = 0;
    bool begin(uint32_t) override { return true; }
    void setEnabled(bool, uint32_t) override {}
    bool stable(uint32_t) const override { return true; }
    bool setLineWired() const override { return true; }
    bool readFrame(uint32_t, uint8_t out[32]) override {
        ++reads;
        for (int i = 0; i < 32; ++i) out[i] = 0;
        out[0] = 0x42; out[1] = 0x4D; out[3] = 28;
        out[13] = 7;                                   // pm2_5 atmospheric
        uint16_t sum = 0;
        for (int i = 0; i < 30; ++i) sum += out[i];
        out[30] = sum >> 8; out[31] = sum & 0xFF;
        if (reads % 2 == 1) out[31] ^= 0x5A;           // first attempt is corrupt
        return true;
    }
};

static EnvModel*    room;
static FakeClock*   clk;
static MockShtc3*   shtc3;
static SpyScd41*    scd41;
static MockPmsa003i* pm;
static MockBme688*  bme;
static SensorSuite* suite;

void setUp() {
    room = new EnvModel(5);
    room->reset(kNoon);
    clk = new FakeClock();
    shtc3 = new MockShtc3(*room);
    scd41 = new SpyScd41(*room);
    pm = new MockPmsa003i(*room);
    bme = new MockBme688(*room);
    suite = new SensorSuite(*clk, *shtc3, *scd41, *pm, *bme);
}

void tearDown() {
    delete suite; delete bme; delete pm; delete scd41; delete shtc3; delete clk; delete room;
}

// Move past the PM warm-up and the SCD41's first conversion.
static void settle() { clk->advance(35000); }

// ---------------- begin ----------------

void test_begin_starts_all_four() {
    TEST_ASSERT_TRUE(suite->begin());
    TEST_ASSERT_TRUE(suite->shtc3Present());
    TEST_ASSERT_TRUE(suite->scd41Present());
    TEST_ASSERT_TRUE(suite->pmPresent());
    TEST_ASSERT_TRUE(suite->bme688Present());
}

void test_begin_waits_the_scd41_power_up_before_starting_it() {
    // The part refuses commands for 30 ms after power-up. Without the wait
    // startPeriodicMeasurement would be rejected and there would be no data.
    suite->begin();
    TEST_ASSERT_TRUE(clk->waited >= SensorSuite::kScd41WakeMs);
    TEST_ASSERT_EQUAL(MockScd41::PERIODIC, scd41->mode());
}

void test_begin_applies_the_bme_heater_profile() {
    suite->begin();
    // 1 + 2*(2+16+1) TPH + 100 ms heater
    TEST_ASSERT_EQUAL_UINT32(1 + 2 * 19 + SensorSuite::kBmeHeaterMs, bme->measurementMs());
}

void test_begin_reports_a_sensor_that_will_not_start() {
    DeadShtc3 dead;
    SensorSuite s(*clk, dead, *scd41, *pm, *bme);
    TEST_ASSERT_FALSE(s.begin());
    TEST_ASSERT_FALSE(s.shtc3Present());
    TEST_ASSERT_TRUE(s.scd41Present());
}

// ---------------- sample ----------------

void test_sample_fills_every_sensor_once_settled() {
    suite->begin();
    settle();
    Readings r = suite->sample(room->epoch());

    TEST_ASSERT_EQUAL_UINT32(room->epoch(), r.ts);
    TEST_ASSERT_TRUE(r.shtc3Valid);
    TEST_ASSERT_TRUE(r.scd41Valid);
    TEST_ASSERT_TRUE(r.pmValid);
    TEST_ASSERT_TRUE(r.bme688Valid);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->tempC(), r.shtc3.tempC);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->pressureHpa(), r.bme688.pressureHpa);
    TEST_ASSERT_TRUE(r.scd41.co2Ppm > 0);
}

void test_sample_leaves_the_shtc3_asleep() {
    suite->begin();
    settle();
    suite->sample(room->epoch());
    TEST_ASSERT_TRUE_MESSAGE(shtc3->asleep(), "the part draws 45 uA idle vs 0.3 uA asleep");
}

void test_sample_feeds_bme_pressure_to_the_scd41() {
    suite->begin();
    settle();
    Readings r = suite->sample(room->epoch());
    TEST_ASSERT_TRUE(r.bme688Valid);
    TEST_ASSERT_EQUAL(1, scd41->pressureCalls);
    TEST_ASSERT_UINT32_WITHIN(50, (uint32_t)(r.bme688.pressureHpa * 100.0f), scd41->lastPressurePa);
}

void test_sample_skips_pm_during_the_fan_warm_up() {
    suite->begin();
    clk->advance(10000);                    // 10 s: booted, fan still spinning up
    Readings r = suite->sample(room->epoch());
    TEST_ASSERT_FALSE_MESSAGE(r.pmValid, "warm-up counts are believable and wrong");
    TEST_ASSERT_TRUE(r.shtc3Valid);         // the others are unaffected
    settle();
    TEST_ASSERT_TRUE(suite->sample(room->epoch()).pmValid);
}

void test_sample_retries_a_corrupt_pm_frame() {
    FlakyPm flaky;
    SensorSuite s(*clk, *shtc3, *scd41, flaky, *bme);
    s.begin();
    settle();
    Readings r = s.sample(room->epoch());
    TEST_ASSERT_EQUAL_MESSAGE(2, flaky.reads, "one retry after a checksum failure");
    TEST_ASSERT_TRUE(r.pmValid);
    TEST_ASSERT_EQUAL_UINT16(7, r.pm.pm2_5);
}

void test_health_counts_a_bad_pm_frame() {
    FlakyPm flaky;
    SensorSuite s(*clk, *shtc3, *scd41, flaky, *bme);
    s.begin();
    settle();
    s.sample(room->epoch());
    TEST_ASSERT_EQUAL_UINT32(1, s.health().pmBadFrames);
    s.sample(room->epoch());
    TEST_ASSERT_EQUAL_UINT32(2, s.health().pmBadFrames);
}

void test_health_holds_the_scd41_settings_from_its_start_and_the_bme688s_last_state() {
    suite->begin();
    SensorHealth h = suite->health();
    TEST_ASSERT_TRUE(h.scd41Read);
    TEST_ASSERT_TRUE(h.ascKnown && h.asc);
    TEST_ASSERT_TRUE(h.offsetKnown);
    TEST_ASSERT_FLOAT_WITHIN(0.01f, 4.0f, h.offsetC);
    TEST_ASSERT_FALSE_MESSAGE(h.bme688Seen, "no sample yet");
    settle();
    Readings r = suite->sample(room->epoch());
    h = suite->health();
    TEST_ASSERT_TRUE(h.bme688Seen);
    TEST_ASSERT_EQUAL(r.bme688.gasValid, h.gasValid);
    TEST_ASSERT_EQUAL(r.bme688.heatStable, h.heatStable);
    TEST_ASSERT_EQUAL_UINT32(0, h.restarts);
}

void test_sample_reports_nothing_for_a_dead_sensor_and_still_reads_the_rest() {
    DeadShtc3 dead;
    SensorSuite s(*clk, dead, *scd41, *pm, *bme);
    s.begin();
    settle();
    Readings r = s.sample(room->epoch());
    TEST_ASSERT_FALSE(r.shtc3Valid);
    TEST_ASSERT_TRUE(r.scd41Valid);
    TEST_ASSERT_TRUE(r.pmValid);
    TEST_ASSERT_TRUE(r.bme688Valid);
}

void test_scd41_reports_only_when_the_5s_conversion_is_ready() {
    suite->begin();
    settle();
    suite->sample(room->epoch());                       // consumes the ready reading
    Readings soon = suite->sample(room->epoch());       // ~150 ms later
    TEST_ASSERT_FALSE_MESSAGE(soon.scd41Valid, "periodic mode yields one reading per 5 s");
    clk->advance(5000);
    TEST_ASSERT_TRUE(suite->sample(room->epoch()).scd41Valid);
}

void test_fan_can_be_stopped_and_restarts_its_warm_up() {
    suite->begin();
    settle();
    TEST_ASSERT_TRUE(suite->sample(room->epoch()).pmValid);

    suite->setFanEnabled(false);
    TEST_ASSERT_FALSE(suite->sample(room->epoch()).pmValid);

    suite->setFanEnabled(true);
    clk->advance(10000);
    TEST_ASSERT_FALSE_MESSAGE(suite->sample(room->epoch()).pmValid, "30 s warm-up starts again");
    clk->advance(25000);
    TEST_ASSERT_TRUE(suite->sample(room->epoch()).pmValid);
}

void test_a_sample_costs_about_150ms_of_wall_clock() {
    suite->begin();
    settle();
    uint32_t before = clk->now;
    suite->sample(room->epoch());
    uint32_t cost = clk->now - before;
    TEST_ASSERT_UINT32_WITHIN_MESSAGE(20, 152, cost, "13 ms SHTC3 + 139 ms BME688 cycle");
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_begin_starts_all_four);
    RUN_TEST(test_begin_waits_the_scd41_power_up_before_starting_it);
    RUN_TEST(test_begin_applies_the_bme_heater_profile);
    RUN_TEST(test_begin_reports_a_sensor_that_will_not_start);
    RUN_TEST(test_sample_fills_every_sensor_once_settled);
    RUN_TEST(test_sample_leaves_the_shtc3_asleep);
    RUN_TEST(test_sample_feeds_bme_pressure_to_the_scd41);
    RUN_TEST(test_sample_skips_pm_during_the_fan_warm_up);
    RUN_TEST(test_sample_retries_a_corrupt_pm_frame);
    RUN_TEST(test_health_counts_a_bad_pm_frame);
    RUN_TEST(test_health_holds_the_scd41_settings_from_its_start_and_the_bme688s_last_state);
    RUN_TEST(test_sample_reports_nothing_for_a_dead_sensor_and_still_reads_the_rest);
    RUN_TEST(test_scd41_reports_only_when_the_5s_conversion_is_ready);
    RUN_TEST(test_fan_can_be_stopped_and_restarts_its_warm_up);
    RUN_TEST(test_a_sample_costs_about_150ms_of_wall_clock);
    return UNITY_END();
}
