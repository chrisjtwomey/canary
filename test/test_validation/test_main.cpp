// The validation pass against the same fake parts the drivers are tested on.
// What is under test is the order it drives them in and the verdict it
// reaches: that the SCD41 is never powered down, that each part ends the pass
// asleep, and that an unwired SET line warns rather than fails.
#include <unity.h>

#include <cstdio>
#include <cstring>

#include "../test_drivers/FakeParts.h"
#include "sensors/Bme688Driver.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Scd41Driver.h"
#include "sensors/SensorValidation.h"
#include "sensors/Shtc3Driver.h"

class FakeClock : public IClock {
public:
    uint32_t now = 0;
    uint32_t millis() const override { return now; }
    void waitMs(uint32_t ms) override { now += ms; }
    void advance(uint32_t ms) { now += ms; }
};

// The SET line, as the Inkplate's expander pin would be: writing it is what
// silences the module.
static FakePmsa003i* pmPart = nullptr;
static int           fanLineWrites = 0;
static void setFanLine(bool high) {
    if (pmPart) pmPart->answering = high;
    ++fanLineWrites;
}
// A wire that was never soldered: the driver drives it, the module ignores it.
static void setFanLineNotWired(bool) { ++fanLineWrites; }

static const int kMaxLines = 64;
static char      logLines[kMaxLines][120];
static int       logCount = 0;
static void      captureLine(int, const char* line) {
    if (logCount < kMaxLines) snprintf(logLines[logCount++], 120, "%s", line);
}

static int linesContaining(const char* needle) {
    int n = 0;
    for (int i = 0; i < logCount; ++i) {
        if (strstr(logLines[i], needle)) ++n;
    }
    return n;
}

static FakeI2cBus* bus;
static FakeClock*  clk;

void setUp() {
    bus = new FakeI2cBus();
    clk = new FakeClock();
    pmPart = nullptr;
    fanLineWrites = 0;
    logCount = 0;
}

void tearDown() {
    delete bus;
    delete clk;
}

// The four parts and the routine over them, wired the way the board is.
struct Bench {
    FakeShtc3    shtc3Part;
    FakeScd41    scd41Part;
    FakePmsa003i pmPart_;
    FakeBme688   bmePart;

    Shtc3Driver*    shtc3;
    Scd41Driver*    scd41;
    Pmsa003iDriver* pm;
    Bme688Driver*   bme;
    SensorValidation* validation;

    explicit Bench(Pmsa003iDriver::SetLineFn setLine = setFanLine, bool attachScd41 = true) {
        pmPart = &pmPart_;
        bmePart.loadCalibration();
        bus->attach(Shtc3Driver::kAddress, &shtc3Part);
        if (attachScd41) bus->attach(Scd41Driver::kAddress, &scd41Part);
        bus->attach(Pmsa003iDriver::kAddress, &pmPart_);
        bus->attach(Bme688Driver::kAddress, &bmePart);

        shtc3 = new Shtc3Driver(*bus, *clk);
        scd41 = new Scd41Driver(*bus, *clk);
        pm    = new Pmsa003iDriver(*bus, *clk, setLine);
        bme   = new Bme688Driver(*bus, *clk);
        validation = new SensorValidation(*clk, *bus, Pmsa003iDriver::kAddress, *shtc3,
                                          *scd41, *pm, *bme, captureLine);
    }

    ~Bench() {
        delete validation;
        delete bme;
        delete pm;
        delete scd41;
        delete shtc3;
        pmPart = nullptr;
    }

    SensorValidation::Report run() { return validation->run(1757443200); }
};

// ---------------- The pass as a whole ----------------

void test_run_reports_each_sensor_that_answered() {
    Bench b;
    SensorValidation::Report r = b.run();

    printf("LOG| failures=%u warnings=%u\n", r.failures, r.warnings);
    TEST_ASSERT_TRUE(r.shtc3.present);
    TEST_ASSERT_TRUE(r.scd41.present);
    TEST_ASSERT_TRUE(r.pm.present);
    TEST_ASSERT_TRUE(r.bme688.present);
    TEST_ASSERT_EQUAL_UINT8(0, r.failures);
}

void test_a_sensor_that_does_not_answer_is_absent_and_counts_as_a_failure() {
    Bench b;
    b.shtc3Part.id = 0x0000;   // answers the bus, but is not an SHTC3
    SensorValidation::Report r = b.run();

    TEST_ASSERT_FALSE(r.shtc3.present);
    TEST_ASSERT_EQUAL_INT(SensorValidation::FAIL, r.shtc3.normal);
    TEST_ASSERT_EQUAL_INT(SensorValidation::SKIPPED, r.shtc3.lowPower);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(1, r.failures);
    // The rest of the pass still runs.
    TEST_ASSERT_TRUE(r.scd41.present);
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.scd41.normal);
}

// ---------------- SCD41 ----------------

void test_scd41_low_power_is_idle_plus_single_shot_and_never_power_down() {
    Bench b;
    SensorValidation::Report r = b.run();

    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.scd41.lowPower);
    TEST_ASSERT_EQUAL_INT(1, b.scd41Part.singleShots);
    TEST_ASSERT_FALSE(b.scd41Part.poweredDown);
}

void test_scd41_is_back_on_periodic_measurement_for_the_gather() {
    Bench b;
    b.run();
    // The reading set came from a periodic measurement, not a second shot.
    TEST_ASSERT_EQUAL_INT(1, b.scd41Part.singleShots);
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS,
                          SensorValidation::check(b.validation->run(0).gathered.scd41));
}

// ---------------- SHTC3 ----------------

void test_shtc3_sleeps_before_its_low_power_reading() {
    Bench b;
    SensorValidation::Report r = b.run();
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.shtc3.lowPower);
    // Two normal-mode reads (the check and the gather) and one low-power read.
    TEST_ASSERT_EQUAL_INT(3, b.shtc3Part.measures);
}

// ---------------- BME688 ----------------

void test_bme688_runs_a_fresh_forced_cycle_after_an_idle_gap() {
    Bench b;
    SensorValidation::Report r = b.run();
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.bme688.normal);
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.bme688.lowPower);
}

void test_bme688_without_a_stable_heater_is_a_warning() {
    Bench b;
    b.bmePart.regs[FakeBme688::kRegGasStatus] = 0x20;   // gas valid, heater not stable
    SensorValidation::Report r = b.run();
    TEST_ASSERT_EQUAL_INT(SensorValidation::WARN, r.bme688.normal);
    TEST_ASSERT_EQUAL_UINT8(0, r.failures);
}

void test_bme688_first_cycle_after_start_is_thrown_away() {
    Bench b;
    b.bmePart.firstCycleCold = true;
    SensorValidation::Report r = b.run();
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.bme688.normal);
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.bme688.lowPower);
    TEST_ASSERT_EQUAL_UINT8(0, r.warnings);
}

// ---------------- The PM fan's SET line ----------------

void test_set_line_low_silences_the_pm_module() {
    Bench b;
    SensorValidation::Report r = b.run();

    TEST_ASSERT_TRUE(r.setLineWired);
    TEST_ASSERT_FALSE(r.pmAnsweredWithSetLow);
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.pm.lowPower);
}

void test_pm_that_answers_with_set_low_warns_and_does_not_fail() {
    Bench b(setFanLineNotWired);
    SensorValidation::Report r = b.run();

    TEST_ASSERT_TRUE(r.setLineWired);
    TEST_ASSERT_TRUE(r.pmAnsweredWithSetLow);
    TEST_ASSERT_EQUAL_INT(SensorValidation::WARN, r.pm.lowPower);
    TEST_ASSERT_EQUAL_UINT8(0, r.failures);
    TEST_ASSERT_EQUAL_INT(1, linesContaining("SET wire not connected"));
}

void test_pm_without_a_set_line_skips_the_sleep_check() {
    Bench b(nullptr);
    SensorValidation::Report r = b.run();

    TEST_ASSERT_FALSE(r.setLineWired);
    TEST_ASSERT_EQUAL_INT(SensorValidation::SKIPPED, r.pm.lowPower);
    TEST_ASSERT_EQUAL_UINT8(0, r.failures);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT8(1, r.warnings);
}

// An absent SCD41 has no conversion coming, so the gather must not spend the
// data-ready timeout waiting for one. The pass is then the fan's warm-up plus
// a little; the timeout would add another seven seconds on top.
void test_an_absent_scd41_does_not_delay_the_gather() {
    Bench b(setFanLine, false);
    SensorValidation::Report r = b.run();

    TEST_ASSERT_FALSE(r.scd41.present);
    TEST_ASSERT_LESS_THAN_UINT32(Pmsa003iDriver::kWarmupMs +
                                     SensorValidation::kScd41ReadyTimeoutMs,
                                 r.elapsedMs);
}

void test_pm_normal_read_waits_for_the_single_warm_up() {
    Bench b;
    SensorValidation::Report r = b.run();
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, r.pm.normal);
    TEST_ASSERT_GREATER_OR_EQUAL_UINT32(Pmsa003iDriver::kWarmupMs, r.elapsedMs);
    // One warm-up, not two: the fan is stopped and restarted once.
    TEST_ASSERT_LESS_THAN_UINT32(2 * Pmsa003iDriver::kWarmupMs, r.elapsedMs);
}

// ---------------- The state the pass leaves behind ----------------

void test_every_sensor_ends_the_pass_in_its_low_power_state() {
    Bench b;
    b.run();

    TEST_ASSERT_TRUE(b.shtc3Part.asleep);
    TEST_ASSERT_FALSE(b.scd41Part.periodic);
    TEST_ASSERT_FALSE(b.scd41Part.poweredDown);
    TEST_ASSERT_FALSE(b.pmPart_.answering);
}

void test_the_log_callback_gets_a_marker_for_every_phase() {
    Bench b;
    b.run();
    TEST_ASSERT_EQUAL_INT(6, linesContaining("phase "));
    TEST_ASSERT_EQUAL_INT(1, linesContaining("summary:"));
}

// ---------------- Ranges ----------------

void test_scd41_zero_co2_is_a_failure() {
    Scd41Data d = {0, 21.0f, 45.0f};
    TEST_ASSERT_EQUAL_INT(SensorValidation::FAIL, SensorValidation::check(d));
}

void test_scd41_above_five_thousand_ppm_is_a_warning() {
    Scd41Data d = {6000, 21.0f, 45.0f};
    TEST_ASSERT_EQUAL_INT(SensorValidation::WARN, SensorValidation::check(d));
}

void test_shtc3_outside_the_recommended_range_is_a_warning_not_a_failure() {
    Shtc3Data warm = {70.0f, 45.0f};
    TEST_ASSERT_EQUAL_INT(SensorValidation::WARN, SensorValidation::check(warm));
    Shtc3Data impossible = {200.0f, 45.0f};
    TEST_ASSERT_EQUAL_INT(SensorValidation::FAIL, SensorValidation::check(impossible));
}

void test_bme688_needs_gas_valid_and_a_plausible_pressure() {
    Bme688Data ok = {21.0f, 1006.0f, 45.0f, 118000.0f, true, true, 0.0f, 0};
    TEST_ASSERT_EQUAL_INT(SensorValidation::PASS, SensorValidation::check(ok));

    Bme688Data noGas = ok;
    noGas.gasValid = false;
    TEST_ASSERT_EQUAL_INT(SensorValidation::FAIL, SensorValidation::check(noGas));

    Bme688Data vacuum = ok;
    vacuum.pressureHpa = 12.0f;
    TEST_ASSERT_EQUAL_INT(SensorValidation::FAIL, SensorValidation::check(vacuum));
}

void test_pm_counts_must_not_fall_as_the_particle_size_grows() {
    PmData d = {};
    d.pm1_0 = 30; d.pm2_5 = 10; d.pm10 = 40;
    TEST_ASSERT_EQUAL_INT(SensorValidation::FAIL, SensorValidation::check(d));
}

void test_pm_above_five_hundred_micrograms_is_a_warning() {
    PmData d = {};
    d.pm1_0 = 400; d.pm2_5 = 500; d.pm10 = 600;
    TEST_ASSERT_EQUAL_INT(SensorValidation::WARN, SensorValidation::check(d));
}

int main(int argc, char** argv) {
    (void)argc; (void)argv;
    UNITY_BEGIN();

    RUN_TEST(test_run_reports_each_sensor_that_answered);
    RUN_TEST(test_a_sensor_that_does_not_answer_is_absent_and_counts_as_a_failure);

    RUN_TEST(test_scd41_low_power_is_idle_plus_single_shot_and_never_power_down);
    RUN_TEST(test_scd41_is_back_on_periodic_measurement_for_the_gather);
    RUN_TEST(test_shtc3_sleeps_before_its_low_power_reading);
    RUN_TEST(test_bme688_runs_a_fresh_forced_cycle_after_an_idle_gap);
    RUN_TEST(test_bme688_without_a_stable_heater_is_a_warning);
    RUN_TEST(test_bme688_first_cycle_after_start_is_thrown_away);

    RUN_TEST(test_set_line_low_silences_the_pm_module);
    RUN_TEST(test_pm_that_answers_with_set_low_warns_and_does_not_fail);
    RUN_TEST(test_pm_without_a_set_line_skips_the_sleep_check);
    RUN_TEST(test_an_absent_scd41_does_not_delay_the_gather);
    RUN_TEST(test_pm_normal_read_waits_for_the_single_warm_up);

    RUN_TEST(test_every_sensor_ends_the_pass_in_its_low_power_state);
    RUN_TEST(test_the_log_callback_gets_a_marker_for_every_phase);

    RUN_TEST(test_scd41_zero_co2_is_a_failure);
    RUN_TEST(test_scd41_above_five_thousand_ppm_is_a_warning);
    RUN_TEST(test_shtc3_outside_the_recommended_range_is_a_warning_not_a_failure);
    RUN_TEST(test_bme688_needs_gas_valid_and_a_plausible_pressure);
    RUN_TEST(test_pm_counts_must_not_fall_as_the_particle_size_grows);
    RUN_TEST(test_pm_above_five_hundred_micrograms_is_a_warning);

    return UNITY_END();
}
