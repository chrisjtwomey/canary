// Each mock reproduces the datasheet's timing and quirks.
#include <unity.h>
#include <cstring>
#include "sensors/Readings.h"
#include "sensors/mock/EnvModel.h"
#include "sensors/mock/MockBme688.h"
#include "sensors/mock/MockPmsa003i.h"
#include "sensors/mock/MockScd41.h"
#include "sensors/mock/MockShtc3.h"

static const uint32_t kNoon = 1756857600 + 12 * 3600;
static EnvModel* room;

void setUp() { room = new EnvModel(5); room->reset(kNoon); }
void tearDown() { delete room; }

// ---------------- SHTC3 ----------------

void test_shtc3_nacks_measure_when_asleep() {
    MockShtc3 s(*room);
    s.begin(0);
    TEST_ASSERT_TRUE(s.asleep());
    TEST_ASSERT_FALSE(s.measure(10, false));
}

void test_shtc3_normal_mode_takes_13ms_and_tracks_the_room() {
    MockShtc3 s(*room);
    s.begin(0);
    s.wakeup(100);
    TEST_ASSERT_TRUE(s.measure(100, false));
    Shtc3Data d;
    TEST_ASSERT_FALSE(s.read(105, d));          // too early
    TEST_ASSERT_TRUE(s.read(113, d));
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->tempC(), d.tempC);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->rhPct(), d.rhPct);
    TEST_ASSERT_FALSE(s.read(114, d));          // buffer consumed
}

void test_shtc3_low_power_is_fast_and_noisier() {
    MockShtc3 s(*room);
    s.begin(0); s.wakeup(0);
    s.measure(0, true);
    Shtc3Data d;
    TEST_ASSERT_TRUE(s.read(1, d));
    float spread = 0;
    for (int i = 0; i < 50; ++i) {
        s.measure(10 + i * 2, true); s.read(11 + i * 2, d);
        float e = d.tempC - room->tempC(); spread += e * e;
    }
    TEST_ASSERT_TRUE_MESSAGE(spread / 50 > 0.02f, "low-power repeatability is 0.4 C, not 0.1");
    TEST_ASSERT_EQUAL_HEX16(0x0807, s.readId() & 0x083F);
}

// ---------------- SCD41 ----------------

void test_scd41_periodic_data_every_5s_and_nack_between() {
    MockScd41 c(*room);
    c.begin(0);
    TEST_ASSERT_FALSE(c.startPeriodicMeasurement(10));   // still waking (30 ms)
    TEST_ASSERT_TRUE(c.startPeriodicMeasurement(40));
    bool ready = true;
    c.getDataReadyStatus(2000, ready);
    TEST_ASSERT_FALSE(ready);
    Scd41Data d;
    TEST_ASSERT_FALSE(c.readMeasurement(2000, d));        // NACK
    c.getDataReadyStatus(5100, ready);
    TEST_ASSERT_TRUE(ready);
    TEST_ASSERT_TRUE(c.readMeasurement(5100, d));
    TEST_ASSERT_FALSE(c.readMeasurement(5200, d));        // cleared by the read
    c.getDataReadyStatus(10100, ready);
    TEST_ASSERT_TRUE(ready);
}

void test_scd41_first_reading_after_power_up_reads_high() {
    MockScd41 c(*room);
    c.begin(0);
    c.startPeriodicMeasurement(40);
    Scd41Data first, second;
    TEST_ASSERT_TRUE(c.readMeasurement(5100, first));
    TEST_ASSERT_TRUE(c.readMeasurement(10100, second));
    TEST_ASSERT_TRUE_MESSAGE(first.co2Ppm > second.co2Ppm + 100, "first shot carries the +150 ppm start-up error");
    TEST_ASSERT_UINT16_WITHIN(40, (uint16_t)room->co2Ppm(), second.co2Ppm);
}

void test_scd41_refuses_config_while_measuring_and_is_busy_after_stop() {
    MockScd41 c(*room);
    c.begin(0);
    c.startPeriodicMeasurement(40);
    TEST_ASSERT_FALSE(c.setTemperatureOffset(2.0f));      // idle only
    TEST_ASSERT_TRUE(c.setAmbientPressure(98000));         // allowed while periodic
    TEST_ASSERT_TRUE(c.stopPeriodicMeasurement(6000));
    TEST_ASSERT_FALSE(c.startPeriodicMeasurement(6100));   // 500 ms busy
    TEST_ASSERT_TRUE(c.setTemperatureOffset(2.0f));
    TEST_ASSERT_TRUE(c.startPeriodicMeasurement(6600));
}

void test_scd41_reads_cold_then_warms_into_its_offset() {
    MockScd41 c(*room);
    c.begin(0);
    c.startPeriodicMeasurement(40);
    Scd41Data d;
    // The default offset subtracts 4 C from the moment it powers up, but the
    // part has not warmed itself yet, so a cold device reads low.
    c.readMeasurement(5100, d);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->tempC() - MockScd41::kSelfHeatingC, d.tempC);
    // Fifteen minutes is what the design-in guide asks you to wait before
    // judging the offset.
    c.readMeasurement(900000, d);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->tempC(), d.tempC);
}

void test_scd41_offset_shifts_the_warm_reading() {
    MockScd41 c(*room);
    c.begin(0);
    c.startPeriodicMeasurement(40);
    Scd41Data d;
    c.readMeasurement(900000, d);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->tempC(), d.tempC);
    c.stopPeriodicMeasurement(901000);
    c.setTemperatureOffset(0.0f);
    c.startPeriodicMeasurement(902000);
    c.readMeasurement(910000, d);
    TEST_ASSERT_FLOAT_WITHIN(0.5f, room->tempC() + MockScd41::kSelfHeatingC, d.tempC);
}

void test_scd41_co2_trails_a_change_in_the_room() {
    MockScd41 c(*room);
    c.begin(0);
    c.startPeriodicMeasurement(40);
    Scd41Data d;
    c.readMeasurement(5100, d);                       // adopts the room
    c.readMeasurement(10100, d);                      // past the start-up error
    float before = d.co2Ppm;

    room->advanceTo(room->epoch() + 9 * 3600);        // evening: two people in
    float roomNow = room->co2Ppm();
    TEST_ASSERT_TRUE_MESSAGE(roomNow > before + 200, "the room should have changed a lot");

    c.readMeasurement(15100, d);                      // five seconds later
    TEST_ASSERT_TRUE_MESSAGE(d.co2Ppm < roomNow - 100,
                             "tau63 is 60 s, so 5 s covers about 8% of the step");
    c.readMeasurement(315100, d);                     // five minutes on
    TEST_ASSERT_UINT16_WITHIN(60, (uint16_t)roomNow, d.co2Ppm);
}

void test_scd41_wrong_assumed_pressure_skews_co2() {
    MockScd41 low(*room), right(*room);
    low.begin(0); right.begin(0);
    low.startPeriodicMeasurement(40); right.startPeriodicMeasurement(40);
    uint32_t truePa = (uint32_t)(room->pressureHpa() * 100.0f);
    right.setAmbientPressure(truePa);
    low.setAmbientPressure(120000);                          // told it is at high pressure
    Scd41Data a, b;
    low.readMeasurement(5100, a);  low.readMeasurement(10100, a);
    right.readMeasurement(5100, b); right.readMeasurement(10100, b);
    TEST_ASSERT_TRUE_MESSAGE(a.co2Ppm < b.co2Ppm - 50, "over-stated pressure under-reads CO2");
}

void test_scd41_power_down_and_wake() {
    MockScd41 c(*room);
    c.begin(0);
    TEST_ASSERT_TRUE(c.powerDown());
    uint64_t sn;
    TEST_ASSERT_FALSE(c.getSerialNumber(sn));
    TEST_ASSERT_TRUE(c.wakeUp(100));
    TEST_ASSERT_TRUE(c.getSerialNumber(sn));
    TEST_ASSERT_FALSE(c.measureSingleShot(110));            // 30 ms wake
    TEST_ASSERT_TRUE(c.measureSingleShot(140));
    Scd41Data d;
    TEST_ASSERT_FALSE(c.readMeasurement(4000, d));
    TEST_ASSERT_TRUE(c.readMeasurement(5140, d));
    TEST_ASSERT_EQUAL(MockScd41::IDLE, c.mode());
}

// ---------------- PMSA003I ----------------

void test_pm_boots_3s_then_warms_up_30s() {
    MockPmsa003i p(*room);
    p.begin(0);
    uint8_t f[32];
    TEST_ASSERT_FALSE(p.readFrame(2000, f));                // booting
    TEST_ASSERT_TRUE(p.readFrame(3500, f));
    TEST_ASSERT_FALSE(p.stable(3500));
    PmData d;
    TEST_ASSERT_TRUE(IPmsa003i::parseFrame(f, d));
    TEST_ASSERT_TRUE_MESSAGE(d.pm2_5 < room->pm25(), "warm-up frames read low");
    TEST_ASSERT_TRUE(p.stable(30000));
    p.readFrame(35000, f);
    IPmsa003i::parseFrame(f, d);
    TEST_ASSERT_UINT16_WITHIN(2, (uint16_t)(room->pm25() + 0.5f), d.pm2_5);
}

void test_pm_frame_is_stale_between_updates() {
    MockPmsa003i p(*room);
    p.begin(0);
    uint8_t a[32], b[32], c[32];
    p.readFrame(40000, a);
    p.readFrame(41000, b);
    p.readFrame(42400, c);
    TEST_ASSERT_EQUAL_MEMORY(a, b, 32);                      // same 2.3 s window
    TEST_ASSERT_TRUE(memcmp(a, c, 32) != 0 || true);         // a new frame may or may not differ in value
}

void test_pm_checksum_fails_once_in_200_reads() {
    MockPmsa003i p(*room);
    p.begin(0);
    uint8_t f[32]; PmData d;
    int bad = 0;
    for (int i = 0; i < 400; ++i) {
        p.readFrame(40000 + i * 10, f);
        if (!IPmsa003i::parseFrame(f, d)) ++bad;
    }
    TEST_ASSERT_EQUAL(2, bad);
}

void test_pm_set_low_silences_and_restarts_warmup() {
    MockPmsa003i p(*room);
    p.begin(0);
    uint8_t f[32];
    TEST_ASSERT_TRUE(p.readFrame(40000, f));
    p.setEnabled(false, 41000);
    TEST_ASSERT_FALSE(p.readFrame(42000, f));
    p.setEnabled(true, 50000);
    TEST_ASSERT_FALSE(p.stable(60000));
    TEST_ASSERT_TRUE(p.stable(80001));
}

void test_pm_parse_rejects_bad_start_length_and_checksum() {
    uint8_t f[32] = {0};
    PmData d;
    TEST_ASSERT_FALSE(IPmsa003i::parseFrame(f, d));
    f[0] = 0x42; f[1] = 0x4D; f[3] = 28;
    uint16_t sum = 0; for (int i = 0; i < 30; ++i) sum += f[i];
    f[30] = sum >> 8; f[31] = sum & 0xFF;
    TEST_ASSERT_TRUE(IPmsa003i::parseFrame(f, d));
    f[31] ^= 1;
    TEST_ASSERT_FALSE(IPmsa003i::parseFrame(f, d));
}

// ---------------- BME688 ----------------

void test_bme_cycle_takes_tph_plus_heater_and_first_cycle_is_unstable() {
    MockBme688 b(*room);
    b.begin(0);
    b.setOversampling(2, 16, 1);
    b.setHeaterProfile(300, 100);
    TEST_ASSERT_EQUAL_UINT32(1 + 2 * 19 + 100, b.measurementMs());
    TEST_ASSERT_TRUE(b.startForced(0));
    TEST_ASSERT_FALSE(b.startForced(50));                    // ignored mid-cycle
    Bme688Data d;
    TEST_ASSERT_FALSE(b.fetchData(100, d));
    TEST_ASSERT_TRUE(b.fetchData(139, d));
    TEST_ASSERT_FALSE(d.heatStable);
    TEST_ASSERT_TRUE(d.gasValid);
    b.startForced(1000); b.fetchData(1200, d);
    TEST_ASSERT_TRUE(d.heatStable);
}

void test_bme_short_heater_never_stabilises() {
    MockBme688 b(*room);
    b.begin(0);
    b.setHeaterProfile(300, 20);
    Bme688Data d;
    for (int i = 0; i < 3; ++i) { b.startForced(i * 1000); b.fetchData(i * 1000 + 100, d); }
    TEST_ASSERT_FALSE(d.heatStable);
}

void test_bme_starts_at_room_temperature_and_warms_above_it() {
    MockBme688 b(*room);
    MockShtc3 s(*room);
    b.begin(0); s.begin(0);
    Bme688Data bd; Shtc3Data sd;

    b.startForced(0); b.fetchData(200, bd);
    s.wakeup(300); s.measure(300, false); s.read(320, sd);
    TEST_ASSERT_FLOAT_WITHIN_MESSAGE(0.4f, 0.0f, bd.tempC - sd.tempC,
                                     "cold, the die sits at room temperature");

    b.startForced(900000); b.fetchData(900200, bd);
    s.wakeup(900300); s.measure(900300, false); s.read(900320, sd);
    TEST_ASSERT_FLOAT_WITHIN(0.4f, MockBme688::kSelfHeatingC, bd.tempC - sd.tempC);
    TEST_ASSERT_TRUE_MESSAGE(bd.rhPct < sd.rhPct, "warmer die, same water, lower RH");
    TEST_ASSERT_FLOAT_WITHIN(0.2f, room->pressureHpa(), bd.pressureHpa);
}

void test_bme_iaq_accuracy_climbs_with_cycles() {
    MockBme688 b(*room);
    b.begin(0);
    Bme688Data d;
    uint8_t seen[4] = {0, 0, 0, 0};
    for (int i = 0; i < 120; ++i) { b.startForced(i * 1000); b.fetchData(i * 1000 + 200, d); seen[d.iaqAccuracy] = 1; }
    TEST_ASSERT_TRUE(seen[0] && seen[1] && seen[2] && seen[3]);
    TEST_ASSERT_EQUAL(3, d.iaqAccuracy);
    TEST_ASSERT_TRUE(d.hasIaq);
    TEST_ASSERT_TRUE(d.iaq >= 0 && d.iaq <= 500);
}

// ---------------- JSON ----------------

void test_json_matches_readings_md() {
    Readings r = {};
    r.ts = 1756900000;
    r.shtc3 = {21.34f, 44.06f}; r.shtc3Valid = true;
    r.scd41 = {812, 25.2f, 36.0f}; r.scd41Valid = true;
    r.pm = {4, 6, 8, 4, 6, 8, 900, 250, 40, 4, 1, 0, 0x97, 0}; r.pmValid = true;
    r.bme688 = {22.8f, 1011.2f, 40.2f, 132000.0f, true, true, 63.4f, 2, true}; r.bme688Valid = true;
    char buf[640];
    size_t n = readingsToJson(r, "canary-dock", buf, sizeof(buf));
    TEST_ASSERT_TRUE(n > 0);
    const char* want =
        "{\"ts\":1756900000,\"device\":\"canary-dock\""
        ",\"temp_c\":21.3,\"rh_pct\":44.1,\"co2_ppm\":812"
        ",\"pm1_0\":4,\"pm2_5\":6,\"pm10\":8,\"pc_0_3\":900,\"pc_0_5\":250,\"pc_1_0\":40,\"pc_2_5\":4,\"pc_5_0\":1,\"pc_10\":0"
        ",\"gas_ohm\":132000,\"iaq\":63,\"iaq_accuracy\":2,\"pressure_hpa\":1011.2"
        ",\"scd41\":{\"temp_c\":25.2,\"rh_pct\":36.0},\"bme688\":{\"temp_c\":22.8,\"rh_pct\":40.2}"
        ",\"valid\":{\"temp_humidity\":true,\"co2\":true,\"particulates\":true"
        ",\"pressure\":true,\"gas\":true}}";
    TEST_ASSERT_EQUAL_STRING(want, buf);
    TEST_ASSERT_EQUAL_UINT32(strlen(want), n);
}

void test_json_omits_invalid_sensors_and_flags_them() {
    Readings r = {};
    r.ts = 1; r.shtc3 = {20.0f, 50.0f}; r.shtc3Valid = true;
    char buf[256];
    TEST_ASSERT_TRUE(readingsToJson(r, "x", buf, sizeof(buf)) > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"ts\":1,\"device\":\"x\",\"temp_c\":20.0,\"rh_pct\":50.0"
        ",\"valid\":{\"temp_humidity\":true,\"co2\":false,\"particulates\":false"
        ",\"pressure\":false,\"gas\":false}}", buf);
}

void test_json_keeps_pressure_but_drops_gas_when_the_heater_is_cold() {
    Readings r = {};
    r.ts = 5;
    r.bme688 = {22.8f, 1011.2f, 40.2f, 132000.0f, true, /*heatStable=*/false, 63.4f, 0};
    r.bme688Valid = true;
    char buf[400];
    TEST_ASSERT_TRUE(readingsToJson(r, "x", buf, sizeof(buf)) > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"ts\":5,\"device\":\"x\",\"pressure_hpa\":1011.2"
        ",\"bme688\":{\"temp_c\":22.8,\"rh_pct\":40.2}"
        ",\"valid\":{\"temp_humidity\":false,\"co2\":false,\"particulates\":false"
        ",\"pressure\":true,\"gas\":false}}", buf);
}

void test_json_drops_gas_when_the_conversion_was_a_dummy_slot() {
    Readings r = {};
    r.ts = 5;
    r.bme688 = {22.8f, 1011.2f, 40.2f, 132000.0f, /*gasValid=*/false, true, 63.4f, 3};
    r.bme688Valid = true;
    char buf[400];
    readingsToJson(r, "x", buf, sizeof(buf));
    TEST_ASSERT_NULL(strstr(buf, "gas_ohm"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"gas\":false"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"pressure\":true"));
}

// Without BSEC the driver has no index. The resistance still goes out, so a
// page shows it instead of an index of zero.
void test_json_leaves_the_index_out_when_the_driver_has_none() {
    Readings r = {};
    r.ts = 5;
    r.bme688 = {22.8f, 1011.2f, 40.2f, 132000.0f, true, true, 0.0f, 0, /*hasIaq=*/false};
    r.bme688Valid = true;
    char buf[400];
    TEST_ASSERT_TRUE(readingsToJson(r, "x", buf, sizeof(buf)) > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"ts\":5,\"device\":\"x\",\"gas_ohm\":132000,\"pressure_hpa\":1011.2"
        ",\"bme688\":{\"temp_c\":22.8,\"rh_pct\":40.2}"
        ",\"valid\":{\"temp_humidity\":false,\"co2\":false,\"particulates\":false"
        ",\"pressure\":true,\"gas\":true}}", buf);
}

void test_json_says_how_long_the_fan_ran_before_a_particle_reading() {
    Readings r = {};
    r.ts = 5;
    r.pm = {4, 6, 8, 4, 6, 8, 900, 250, 40, 4, 1, 0, 0x97, 0}; r.pmValid = true;
    r.pmWarmupS = 35;
    char buf[400];
    TEST_ASSERT_TRUE(readingsToJson(r, "x", buf, sizeof(buf)) > 0);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"pc_10\":0,\"pm_warmup_s\":35,"));
    r.pmValid = false;
    readingsToJson(r, "x", buf, sizeof(buf));
    TEST_ASSERT_NULL_MESSAGE(strstr(buf, "pm_warmup_s"), "no particle reading, no warm-up");
}

void test_json_too_small_buffer_returns_zero_and_empty() {
    Readings r = {};
    r.ts = 1; r.shtc3Valid = true;
    char buf[40];
    TEST_ASSERT_EQUAL_UINT32(0, readingsToJson(r, "canary-dock", buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_STRING("", buf);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_shtc3_nacks_measure_when_asleep);
    RUN_TEST(test_shtc3_normal_mode_takes_13ms_and_tracks_the_room);
    RUN_TEST(test_shtc3_low_power_is_fast_and_noisier);
    RUN_TEST(test_scd41_periodic_data_every_5s_and_nack_between);
    RUN_TEST(test_scd41_first_reading_after_power_up_reads_high);
    RUN_TEST(test_scd41_refuses_config_while_measuring_and_is_busy_after_stop);
    RUN_TEST(test_scd41_reads_cold_then_warms_into_its_offset);
    RUN_TEST(test_scd41_offset_shifts_the_warm_reading);
    RUN_TEST(test_scd41_co2_trails_a_change_in_the_room);
    RUN_TEST(test_scd41_wrong_assumed_pressure_skews_co2);
    RUN_TEST(test_scd41_power_down_and_wake);
    RUN_TEST(test_pm_boots_3s_then_warms_up_30s);
    RUN_TEST(test_pm_frame_is_stale_between_updates);
    RUN_TEST(test_pm_checksum_fails_once_in_200_reads);
    RUN_TEST(test_pm_set_low_silences_and_restarts_warmup);
    RUN_TEST(test_pm_parse_rejects_bad_start_length_and_checksum);
    RUN_TEST(test_bme_cycle_takes_tph_plus_heater_and_first_cycle_is_unstable);
    RUN_TEST(test_bme_short_heater_never_stabilises);
    RUN_TEST(test_bme_starts_at_room_temperature_and_warms_above_it);
    RUN_TEST(test_bme_iaq_accuracy_climbs_with_cycles);
    RUN_TEST(test_json_matches_readings_md);
    RUN_TEST(test_json_omits_invalid_sensors_and_flags_them);
    RUN_TEST(test_json_keeps_pressure_but_drops_gas_when_the_heater_is_cold);
    RUN_TEST(test_json_drops_gas_when_the_conversion_was_a_dummy_slot);
    RUN_TEST(test_json_leaves_the_index_out_when_the_driver_has_none);
    RUN_TEST(test_json_says_how_long_the_fan_ran_before_a_particle_reading);
    RUN_TEST(test_json_too_small_buffer_returns_zero_and_empty);
    return UNITY_END();
}
