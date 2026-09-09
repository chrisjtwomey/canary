// The four drivers against parts that answer the bus the way their
// datasheets say they do. What is under test is the command sequence, the
// CRCs, the conversions and how each driver reads a NACK — everything the
// bench cannot tell apart from a bad sensor.
#include <unity.h>

#include "FakeParts.h"
#include "sensors/Bme688Driver.h"
#include "sensors/Pmsa003iDriver.h"
#include "sensors/Scd41Driver.h"
#include "sensors/Shtc3Driver.h"

// A clock the test drives. waitMs moves it, so the parts see time pass
// exactly as they would on the device.
class FakeClock : public IClock {
public:
    uint32_t now = 0;
    uint32_t millis() const override { return now; }
    void waitMs(uint32_t ms) override { now += ms; }
    void advance(uint32_t ms) { now += ms; }
};

static FakeI2cBus* bus;
static FakeClock*  clk;

// The PM fan's SET line, as a plain function: the driver takes one because
// on this board the pin belongs to the Inkplate's IO expander.
static bool fanLineHigh = false;
static int  fanLineWrites = 0;
static void setFanLine(bool high) {
    fanLineHigh = high;
    ++fanLineWrites;
}

void setUp() {
    bus = new FakeI2cBus();
    clk = new FakeClock();
    fanLineHigh = false;
    fanLineWrites = 0;
}

void tearDown() {
    delete bus;
    delete clk;
}

// ---------------- The CRC both Sensirion parts use ----------------

void test_sensirion_crc_matches_the_datasheet_vector() {
    const uint8_t beef[2] = {0xBE, 0xEF};
    TEST_ASSERT_EQUAL_HEX8(0x92, sensirion::crc8(beef, 2));
}

// ---------------- SHTC3 ----------------

void test_shtc3_begin_checks_the_part_number_and_leaves_it_asleep() {
    FakeShtc3 part;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);

    TEST_ASSERT_TRUE(drv.begin(0));
    TEST_ASSERT_TRUE_MESSAGE(part.asleep, "a soft reset ends in sleep");
    TEST_ASSERT_TRUE(drv.asleep());
}

void test_shtc3_begin_rejects_a_part_that_answers_the_wrong_id() {
    FakeShtc3 part;
    part.id = 0x0000;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);

    TEST_ASSERT_FALSE(drv.begin(0));
}

void test_shtc3_begin_fails_when_nothing_answers() {
    Shtc3Driver drv(*bus, *clk);   // no part on the bus
    TEST_ASSERT_FALSE(drv.begin(0));
}

void test_shtc3_refuses_to_measure_while_asleep() {
    FakeShtc3 part;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);
    drv.begin(0);

    int writesBefore = bus->writes;
    TEST_ASSERT_FALSE(drv.measure(clk->now, false));
    TEST_ASSERT_EQUAL_INT_MESSAGE(writesBefore, bus->writes,
                                  "a sleeping part is not worth a transfer");
}

void test_shtc3_normal_mode_takes_13ms_and_converts_the_words() {
    FakeShtc3 part;
    part.tempC = 21.5f;
    part.rhPct = 47.0f;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);
    drv.begin(0);

    uint32_t t = clk->now;
    TEST_ASSERT_TRUE(drv.wakeup(t));
    t = clk->now;
    TEST_ASSERT_TRUE(drv.measure(t, false));

    Shtc3Data d;
    TEST_ASSERT_FALSE_MESSAGE(drv.read(t + 12, d), "12.1 ms is the datasheet maximum");
    TEST_ASSERT_TRUE(drv.read(t + Shtc3Driver::kNormalMs, d));
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 21.5f, d.tempC);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 47.0f, d.rhPct);
    TEST_ASSERT_FALSE_MESSAGE(drv.read(t + 20, d), "the result was consumed");
}

void test_shtc3_low_power_is_ready_in_one_millisecond() {
    FakeShtc3 part;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);
    drv.begin(0);
    drv.wakeup(clk->now);

    uint32_t t = clk->now;
    TEST_ASSERT_TRUE(drv.measure(t, true));
    Shtc3Data d;
    TEST_ASSERT_TRUE(drv.read(t + Shtc3Driver::kLowPowerMs, d));
}

void test_shtc3_rejects_a_corrupt_answer() {
    FakeShtc3 part;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);
    drv.begin(0);
    drv.wakeup(clk->now);

    uint32_t t = clk->now;
    part.corruptNextAnswer();
    drv.measure(t, false);
    Shtc3Data d;
    TEST_ASSERT_FALSE(drv.read(t + Shtc3Driver::kNormalMs, d));
}

void test_shtc3_sleep_and_wake_track_the_part() {
    FakeShtc3 part;
    bus->attach(Shtc3Driver::kAddress, &part);
    Shtc3Driver drv(*bus, *clk);
    drv.begin(0);

    TEST_ASSERT_TRUE(drv.wakeup(clk->now));
    TEST_ASSERT_FALSE(part.asleep);
    TEST_ASSERT_TRUE(drv.sleep());
    TEST_ASSERT_TRUE(part.asleep);
    TEST_ASSERT_TRUE_MESSAGE(drv.sleep(), "a second sleep is not an error");
}

// ---------------- SCD41 ----------------

static Scd41Driver* startedScd41(FakeScd41& part) {
    bus->attach(Scd41Driver::kAddress, &part);
    Scd41Driver* drv = new Scd41Driver(*bus, *clk);
    drv->begin(clk->now);
    drv->startPeriodicMeasurement(clk->now);
    return drv;
}

void test_scd41_begin_stops_a_part_left_measuring_by_a_warm_reset() {
    FakeScd41 part;
    part.periodic = true;   // the last boot left it running
    bus->attach(Scd41Driver::kAddress, &part);
    Scd41Driver drv(*bus, *clk);

    TEST_ASSERT_TRUE(drv.begin(0));
    TEST_ASSERT_EQUAL_INT(1, part.stopsAccepted);
    TEST_ASSERT_FALSE(part.periodic);
    TEST_ASSERT_EQUAL_INT(Scd41Driver::IDLE, drv.mode());
}

void test_scd41_begin_tolerates_the_stop_a_cold_part_refuses() {
    FakeScd41 part;   // already idle, so it NACKs the stop
    bus->attach(Scd41Driver::kAddress, &part);
    Scd41Driver drv(*bus, *clk);

    TEST_ASSERT_TRUE(drv.begin(0));
    TEST_ASSERT_EQUAL_INT(1, part.stopsRefused);
}

void test_scd41_begin_fails_when_nothing_answers() {
    Scd41Driver drv(*bus, *clk);
    TEST_ASSERT_FALSE(drv.begin(0));
    TEST_ASSERT_EQUAL_INT(Scd41Driver::POWERED_DOWN, drv.mode());
}

void test_scd41_periodic_read_converts_the_words() {
    FakeScd41 part;
    part.co2Ppm = 812;
    part.tempC = 25.2f;
    part.rhPct = 36.0f;
    Scd41Driver* drv = startedScd41(part);
    TEST_ASSERT_EQUAL_INT(Scd41Driver::PERIODIC, drv->mode());

    part.dataReady = true;
    bool ready = false;
    TEST_ASSERT_TRUE(drv->getDataReadyStatus(clk->now, ready));
    TEST_ASSERT_TRUE(ready);

    Scd41Data d;
    TEST_ASSERT_TRUE(drv->readMeasurement(clk->now, d));
    TEST_ASSERT_EQUAL_UINT16(812, d.co2Ppm);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 25.2f, d.tempC);
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 36.0f, d.rhPct);
    delete drv;
}

void test_scd41_data_ready_reads_only_the_low_eleven_bits() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);

    // The fake sets the reserved top bit either way; unmasked it reads as
    // data that is not there.
    part.dataReady = false;
    bool ready = true;
    TEST_ASSERT_TRUE(drv->getDataReadyStatus(clk->now, ready));
    TEST_ASSERT_FALSE(ready);
    delete drv;
}

void test_scd41_read_measurement_fails_when_the_part_nacks_it() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);

    part.dataReady = false;
    Scd41Data d;
    TEST_ASSERT_FALSE(drv->readMeasurement(clk->now, d));
    delete drv;
}

void test_scd41_pressure_goes_out_in_hectopascals_and_is_range_checked() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);

    TEST_ASSERT_TRUE(drv->setAmbientPressure(101120));
    TEST_ASSERT_EQUAL_UINT32(101100, part.lastPressurePa);   // the word is Pa/100

    TEST_ASSERT_FALSE(drv->setAmbientPressure(69999));
    TEST_ASSERT_FALSE(drv->setAmbientPressure(120001));
    TEST_ASSERT_EQUAL_UINT32(101100, part.lastPressurePa);
    delete drv;
}

void test_scd41_temperature_offset_is_refused_while_measuring() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);

    TEST_ASSERT_FALSE(drv->setTemperatureOffset(4.0f));
    TEST_ASSERT_TRUE(drv->stopPeriodicMeasurement(clk->now));
    clk->advance(Scd41Driver::kStopBusyMs);
    TEST_ASSERT_TRUE(drv->setTemperatureOffset(4.0f));
    // 4 C as the part stores it: degrees x 65535/175.
    TEST_ASSERT_EQUAL_UINT16(1498, part.lastOffsetWord);
    delete drv;
}

void test_scd41_stop_leaves_the_part_busy_for_half_a_second() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);

    uint32_t t = clk->now;
    TEST_ASSERT_TRUE(drv->stopPeriodicMeasurement(t));
    TEST_ASSERT_FALSE(drv->startPeriodicMeasurement(t + Scd41Driver::kStopBusyMs - 1));
    TEST_ASSERT_TRUE(drv->startPeriodicMeasurement(t + Scd41Driver::kStopBusyMs));
    delete drv;
}

void test_scd41_single_shot_is_refused_while_periodic_runs() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);
    TEST_ASSERT_FALSE(drv->measureSingleShot(clk->now));
    delete drv;
}

// The low-power reading the validation routine takes: idle, one shot, and a
// five-second wait the caller may not shorten.
void test_scd41_single_shot_yields_one_measurement_after_five_seconds() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);
    TEST_ASSERT_TRUE(drv->stopPeriodicMeasurement(clk->now));
    clk->advance(Scd41Driver::kStopBusyMs);

    uint32_t t = clk->now;
    TEST_ASSERT_TRUE(drv->measureSingleShot(t));
    TEST_ASSERT_EQUAL_INT(1, part.singleShots);

    Scd41Data data = {};
    TEST_ASSERT_FALSE(drv->readMeasurement(t + Scd41Driver::kSingleShotMs - 1, data));

    clk->advance(Scd41Driver::kSingleShotMs);
    TEST_ASSERT_TRUE(drv->readMeasurement(clk->now, data));
    TEST_ASSERT_EQUAL_UINT16(800, data.co2Ppm);
    delete drv;
}

void test_scd41_wake_up_is_never_acked_so_the_serial_number_proves_it() {
    FakeScd41 part;
    part.poweredDown = true;
    bus->attach(Scd41Driver::kAddress, &part);
    Scd41Driver drv(*bus, *clk);   // starts in the powered-down state

    TEST_ASSERT_TRUE(drv.wakeUp(clk->now));
    TEST_ASSERT_EQUAL_INT(1, part.wakeUps);
    TEST_ASSERT_EQUAL_INT(Scd41Driver::IDLE, drv.mode());

    uint64_t serial = 0;
    TEST_ASSERT_TRUE(drv.getSerialNumber(serial));
    TEST_ASSERT_EQUAL_UINT64(0xC0FFEE41ull, serial);
}

void test_scd41_power_down_is_refused_while_measuring() {
    FakeScd41 part;
    Scd41Driver* drv = startedScd41(part);
    TEST_ASSERT_FALSE(drv->powerDown());
    TEST_ASSERT_TRUE(drv->stopPeriodicMeasurement(clk->now));
    clk->advance(Scd41Driver::kStopBusyMs);
    TEST_ASSERT_TRUE(drv->powerDown());
    TEST_ASSERT_TRUE(part.poweredDown);
    delete drv;
}

// ---------------- PMSA003I ----------------

void test_pm_begin_waits_out_the_boot_and_proves_the_module_with_a_frame() {
    FakePmsa003i part;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk);

    TEST_ASSERT_TRUE(drv.begin(0));
    TEST_ASSERT_UINT32_WITHIN_MESSAGE(1, Pmsa003iDriver::kBootMs, clk->now,
                                      "the module answers nothing for 3 s");
}

void test_pm_begin_fails_when_the_module_does_not_answer() {
    FakePmsa003i part;
    part.answering = false;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk);

    TEST_ASSERT_FALSE(drv.begin(0));
}

void test_pm_begin_retries_a_corrupt_checksum() {
    FakePmsa003i part;
    part.corruptFrames = 2;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk);

    TEST_ASSERT_TRUE(drv.begin(0));
    TEST_ASSERT_EQUAL_INT(3, part.frameReads);
}

void test_pm_frame_parses_into_the_atmospheric_values() {
    FakePmsa003i part;
    part.pm1 = 4; part.pm25 = 6; part.pm10 = 8;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk);
    drv.begin(0);

    uint8_t frame[32];
    TEST_ASSERT_TRUE(drv.readFrame(clk->now, frame));
    PmData d;
    TEST_ASSERT_TRUE(IPmsa003i::parseFrame(frame, d));
    TEST_ASSERT_EQUAL_UINT16(4, d.pm1_0);
    TEST_ASSERT_EQUAL_UINT16(6, d.pm2_5);
    TEST_ASSERT_EQUAL_UINT16(8, d.pm10);
}

void test_pm_without_a_set_line_the_fan_has_run_since_power_on() {
    FakePmsa003i part;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk);

    TEST_ASSERT_FALSE(drv.setLineWired());
    TEST_ASSERT_TRUE(drv.enabled());
    TEST_ASSERT_FALSE(drv.stable(Pmsa003iDriver::kWarmupMs - 1));
    TEST_ASSERT_TRUE(drv.stable(Pmsa003iDriver::kWarmupMs));

    // There is no line to pull down, so the fan keeps running.
    drv.setEnabled(false, clk->now);
    TEST_ASSERT_TRUE(drv.enabled());
}

void test_pm_set_line_stops_the_fan_and_restarts_the_warm_up() {
    FakePmsa003i part;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk, setFanLine);

    TEST_ASSERT_TRUE(drv.setLineWired());
    TEST_ASSERT_FALSE_MESSAGE(drv.enabled(), "the driver holds SET low until it starts the fan");

    clk->now = 1000;
    TEST_ASSERT_TRUE(drv.begin(clk->now));
    TEST_ASSERT_TRUE(fanLineHigh);

    uint32_t started = 1000;
    TEST_ASSERT_FALSE(drv.stable(started + Pmsa003iDriver::kWarmupMs - 1));
    TEST_ASSERT_TRUE(drv.stable(started + Pmsa003iDriver::kWarmupMs));

    drv.setEnabled(false, started + Pmsa003iDriver::kWarmupMs);
    TEST_ASSERT_FALSE(fanLineHigh);
    TEST_ASSERT_FALSE(drv.stable(started + Pmsa003iDriver::kWarmupMs));

    uint32_t restarted = started + 60000;
    drv.setEnabled(true, restarted);
    TEST_ASSERT_FALSE_MESSAGE(drv.stable(restarted + Pmsa003iDriver::kWarmupMs - 1),
                              "the warm-up runs again from the fan restart");
    TEST_ASSERT_TRUE(drv.stable(restarted + Pmsa003iDriver::kWarmupMs));
}

void test_pm_reports_nothing_while_the_module_boots() {
    FakePmsa003i part;
    bus->attach(Pmsa003iDriver::kAddress, &part);
    Pmsa003iDriver drv(*bus, *clk, setFanLine);

    drv.setEnabled(true, 5000);
    uint8_t frame[32];
    TEST_ASSERT_FALSE(drv.readFrame(5000 + Pmsa003iDriver::kBootMs - 1, frame));
    TEST_ASSERT_TRUE(drv.readFrame(5000 + Pmsa003iDriver::kBootMs, frame));
}

// ---------------- BME688 ----------------

void test_bme_begin_rejects_a_wrong_chip_id() {
    FakeBme688 part;
    part.regs[FakeBme688::kRegChipId] = 0x58;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);

    TEST_ASSERT_FALSE(drv.begin(0));
}

void test_bme_begin_rejects_a_bme680() {
    FakeBme688 part;
    part.regs[FakeBme688::kRegVariantId] = 0x00;   // the low-gas variant
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);

    TEST_ASSERT_FALSE(drv.begin(0));
}

void test_bme_begin_fails_when_nothing_answers() {
    Bme688Driver drv(*bus, *clk);
    TEST_ASSERT_FALSE(drv.begin(0));
}

void test_bme_applies_the_oversampling_and_the_heater_profile() {
    FakeBme688 part;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);
    TEST_ASSERT_TRUE(drv.begin(0));

    drv.setOversampling(2, 16, 1);
    drv.setHeaterProfile(300, 100);

    // ctrl_meas carries temperature oversampling in bits 7:5 and pressure in
    // 4:2; Bosch's codes count the doublings, so 2x is 2 and 16x is 5.
    uint8_t ctrlMeas = part.regs[FakeBme688::kRegCtrlMeas];
    TEST_ASSERT_EQUAL_UINT8(2, ctrlMeas >> 5);
    TEST_ASSERT_EQUAL_UINT8(5, (ctrlMeas >> 2) & 0x07);
    TEST_ASSERT_EQUAL_UINT8(1, part.regs[FakeBme688::kRegCtrlHum] & 0x07);

    TEST_ASSERT_NOT_EQUAL_MESSAGE(0, part.regs[FakeBme688::kRegResHeat0],
                                  "the heater target becomes a plate resistance");
    TEST_ASSERT_NOT_EQUAL_MESSAGE(0, part.regs[FakeBme688::kRegGasWait0],
                                  "the heater duration becomes a gas-wait code");
    TEST_ASSERT_BITS_HIGH_MESSAGE(0x20, part.regs[FakeBme688::kRegCtrlGas1], "run_gas");
}

void test_bme_measurement_time_covers_the_conversion_and_the_heater() {
    FakeBme688 part;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);
    drv.begin(0);
    drv.setOversampling(2, 16, 1);
    drv.setHeaterProfile(300, 100);

    // 43 ms of conversion at these oversampling rates, then 100 ms of heater.
    TEST_ASSERT_EQUAL_UINT32(143, drv.measurementMs());

    drv.setHeaterProfile(300, 150);
    TEST_ASSERT_EQUAL_UINT32(193, drv.measurementMs());
}

void test_bme_forced_cycle_is_not_ready_until_the_measurement_time() {
    FakeBme688 part;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);
    drv.begin(0);
    drv.setOversampling(2, 16, 1);
    drv.setHeaterProfile(300, 100);

    Bme688Data d;
    TEST_ASSERT_FALSE_MESSAGE(drv.fetchData(clk->now, d), "no cycle has been started");

    uint32_t t = clk->now;
    TEST_ASSERT_TRUE(drv.startForced(t));
    TEST_ASSERT_FALSE(drv.fetchData(t + drv.measurementMs() - 1, d));
    TEST_ASSERT_TRUE(drv.fetchData(t + drv.measurementMs(), d));
}

void test_bme_refuses_a_second_cycle_while_one_runs() {
    FakeBme688 part;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);
    drv.begin(0);

    uint32_t t = clk->now;
    TEST_ASSERT_TRUE(drv.startForced(t));
    TEST_ASSERT_FALSE(drv.startForced(t + 1));
    TEST_ASSERT_TRUE(drv.startForced(t + drv.measurementMs()));
}

void test_bme_carries_the_gas_and_heater_status_bits() {
    FakeBme688 part;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);
    drv.begin(0);

    uint32_t t = clk->now;
    drv.startForced(t);
    Bme688Data d;
    TEST_ASSERT_TRUE(drv.fetchData(t + drv.measurementMs(), d));
    TEST_ASSERT_TRUE(d.gasValid);
    TEST_ASSERT_TRUE(d.heatStable);
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, d.iaqAccuracy, "IAQ needs BSEC, which is not integrated");

    // A plate that has not reached its target: the resistance is still there
    // and still meaningless.
    part.regs[FakeBme688::kRegGasStatus] = 0x20;
    t = clk->now;
    drv.startForced(t);
    TEST_ASSERT_TRUE(drv.fetchData(t + drv.measurementMs(), d));
    TEST_ASSERT_TRUE(d.gasValid);
    TEST_ASSERT_FALSE(d.heatStable);
}

void test_bme_reports_nothing_when_the_part_has_no_new_data() {
    FakeBme688 part;
    bus->attach(Bme688Driver::kAddress, &part);
    Bme688Driver drv(*bus, *clk);
    drv.begin(0);

    part.regs[FakeBme688::kRegField0] = 0x00;   // new_data clear
    uint32_t t = clk->now;
    drv.startForced(t);
    Bme688Data d;
    TEST_ASSERT_FALSE(drv.fetchData(t + drv.measurementMs(), d));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_sensirion_crc_matches_the_datasheet_vector);

    RUN_TEST(test_shtc3_begin_checks_the_part_number_and_leaves_it_asleep);
    RUN_TEST(test_shtc3_begin_rejects_a_part_that_answers_the_wrong_id);
    RUN_TEST(test_shtc3_begin_fails_when_nothing_answers);
    RUN_TEST(test_shtc3_refuses_to_measure_while_asleep);
    RUN_TEST(test_shtc3_normal_mode_takes_13ms_and_converts_the_words);
    RUN_TEST(test_shtc3_low_power_is_ready_in_one_millisecond);
    RUN_TEST(test_shtc3_rejects_a_corrupt_answer);
    RUN_TEST(test_shtc3_sleep_and_wake_track_the_part);

    RUN_TEST(test_scd41_begin_stops_a_part_left_measuring_by_a_warm_reset);
    RUN_TEST(test_scd41_begin_tolerates_the_stop_a_cold_part_refuses);
    RUN_TEST(test_scd41_begin_fails_when_nothing_answers);
    RUN_TEST(test_scd41_periodic_read_converts_the_words);
    RUN_TEST(test_scd41_data_ready_reads_only_the_low_eleven_bits);
    RUN_TEST(test_scd41_read_measurement_fails_when_the_part_nacks_it);
    RUN_TEST(test_scd41_pressure_goes_out_in_hectopascals_and_is_range_checked);
    RUN_TEST(test_scd41_temperature_offset_is_refused_while_measuring);
    RUN_TEST(test_scd41_stop_leaves_the_part_busy_for_half_a_second);
    RUN_TEST(test_scd41_single_shot_is_refused_while_periodic_runs);
    RUN_TEST(test_scd41_single_shot_yields_one_measurement_after_five_seconds);
    RUN_TEST(test_scd41_wake_up_is_never_acked_so_the_serial_number_proves_it);
    RUN_TEST(test_scd41_power_down_is_refused_while_measuring);

    RUN_TEST(test_pm_begin_waits_out_the_boot_and_proves_the_module_with_a_frame);
    RUN_TEST(test_pm_begin_fails_when_the_module_does_not_answer);
    RUN_TEST(test_pm_begin_retries_a_corrupt_checksum);
    RUN_TEST(test_pm_frame_parses_into_the_atmospheric_values);
    RUN_TEST(test_pm_without_a_set_line_the_fan_has_run_since_power_on);
    RUN_TEST(test_pm_set_line_stops_the_fan_and_restarts_the_warm_up);
    RUN_TEST(test_pm_reports_nothing_while_the_module_boots);

    RUN_TEST(test_bme_begin_rejects_a_wrong_chip_id);
    RUN_TEST(test_bme_begin_rejects_a_bme680);
    RUN_TEST(test_bme_begin_fails_when_nothing_answers);
    RUN_TEST(test_bme_applies_the_oversampling_and_the_heater_profile);
    RUN_TEST(test_bme_measurement_time_covers_the_conversion_and_the_heater);
    RUN_TEST(test_bme_forced_cycle_is_not_ready_until_the_measurement_time);
    RUN_TEST(test_bme_refuses_a_second_cycle_while_one_runs);
    RUN_TEST(test_bme_carries_the_gas_and_heater_status_bits);
    RUN_TEST(test_bme_reports_nothing_when_the_part_has_no_new_data);
    return UNITY_END();
}
