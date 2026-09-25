// The dock's settings from GET /board-settings, held to the dock's own limits.
#include <unity.h>
#include <cstdio>
#include <cstring>

#include "net/BoardSettings.h"

static const char kFull[] =
    "{\"version\":\"3f2a9c1e\",\"pm\":{\"warmup_s\":0},"
    "\"scd41\":{\"temperature_offset_c\":2.5,\"self_calibration\":false},"
    "\"shtc3\":{\"low_power\":true},\"led\":{\"brightness_pct\":40,\"dark\":true,\"looks\":["
    "{\"trigger\":\"starting\",\"pattern\":\"solid\",\"length_s\":0.25},"
    "{\"trigger\":\"no_wifi\",\"pattern\":\"off\",\"length_s\":4},"
    "{\"trigger\":\"post_failed\",\"pattern\":\"pulse\",\"length_s\":2.5},"
    "{\"trigger\":\"sensor_missing\",\"pattern\":\"flash\",\"length_s\":10},"
    "{\"trigger\":\"well\",\"pattern\":\"off\",\"length_s\":1}]},"
    "\"log\":{\"level\":\"info\"},\"bsec\":{\"sample_s\":3},"
    "\"recalibrate\":{\"id\":1758650400,\"ppm\":420}}";

static bool parse(const char* json, SettingsAnswer& out,
                  const BoardSettings& current = defaultBoardSettings()) {
    return parseBoardSettings(json, strlen(json), current, out);
}

void setUp() {}
void tearDown() {}

void test_the_defaults_are_the_servers() {
    BoardSettings s = defaultBoardSettings();
    TEST_ASSERT_EQUAL_STRING("", s.version);
    TEST_ASSERT_EQUAL_UINT16(35, s.pmWarmupS);
    TEST_ASSERT_EQUAL_FLOAT(4.0f, s.scd41OffsetC);
    TEST_ASSERT_TRUE(s.scd41SelfCalibration);
    TEST_ASSERT_FALSE(s.shtc3LowPower);
    TEST_ASSERT_EQUAL_UINT8(15, s.ledBrightnessPct);
    TEST_ASSERT_EQUAL_UINT8(5, s.logLevel);
    TEST_ASSERT_EQUAL_UINT16(300, s.bsecSampleS);
    const uint8_t patterns[kLedTriggers] = {2, 3, 3, 3, 2};   // pulse, flash, flash, flash, pulse
    const uint16_t lengths[kLedTriggers] = {500, 1000, 2000, 3000, 1000};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(patterns, s.ledPattern, kLedTriggers);
    TEST_ASSERT_EQUAL_UINT16_ARRAY(lengths, s.ledLengthMs, kLedTriggers);
}

void test_it_reads_every_key() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse(kFull, a));
    TEST_ASSERT_EQUAL_STRING("3f2a9c1e", a.settings.version);
    TEST_ASSERT_EQUAL_UINT16(0, a.settings.pmWarmupS);
    TEST_ASSERT_EQUAL_FLOAT(2.5f, a.settings.scd41OffsetC);
    TEST_ASSERT_FALSE(a.settings.scd41SelfCalibration);
    TEST_ASSERT_TRUE(a.settings.shtc3LowPower);
    TEST_ASSERT_EQUAL_UINT8(40, a.settings.ledBrightnessPct);
    TEST_ASSERT_EQUAL_UINT8(4, a.settings.logLevel);
    TEST_ASSERT_EQUAL_UINT16(3, a.settings.bsecSampleS);
    const uint8_t patterns[kLedTriggers] = {1, 0, 2, 3, 0};   // solid, off, pulse, flash, off
    const uint16_t lengths[kLedTriggers] = {250, 4000, 2500, 10000, 1000};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(patterns, a.settings.ledPattern, kLedTriggers);
    TEST_ASSERT_EQUAL_UINT16_ARRAY(lengths, a.settings.ledLengthMs, kLedTriggers);
    TEST_ASSERT_TRUE(a.dark);
    TEST_ASSERT_EQUAL_UINT32(1758650400, a.recalibrateId);
    TEST_ASSERT_EQUAL_UINT16(420, a.recalibratePpm);
    TEST_ASSERT_EQUAL_UINT32(0, a.refused);
}

void test_a_whole_number_offset_is_a_number_too() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"scd41\":{\"temperature_offset_c\":4}}", a));
    TEST_ASSERT_EQUAL_FLOAT(4.0f, a.settings.scd41OffsetC);
    TEST_ASSERT_EQUAL_UINT32(0, a.refused);
}

void test_a_key_the_answer_lacks_keeps_the_current_value() {
    BoardSettings current = defaultBoardSettings();
    current.ledBrightnessPct = 80;
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\"}", a, current));
    TEST_ASSERT_EQUAL_UINT8(80, a.settings.ledBrightnessPct);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(current.ledPattern, a.settings.ledPattern, kLedTriggers);
    TEST_ASSERT_FALSE(a.dark);
    TEST_ASSERT_EQUAL_UINT32(0, a.recalibrateId);
}

void test_a_value_out_of_the_docks_limits_is_refused_and_the_current_kept() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"pm\":{\"warmup_s\":10},"
                           "\"scd41\":{\"temperature_offset_c\":25,\"self_calibration\":1},"
                           "\"shtc3\":{\"low_power\":\"yes\"},\"led\":{\"brightness_pct\":101,"
                           "\"looks\":{\"well\":{\"pattern\":\"off\",\"length_s\":1}}},"
                           "\"log\":{\"level\":\"verbose\"},\"bsec\":{\"sample_s\":60}}", a));
    TEST_ASSERT_EQUAL_UINT32((1u << kSettingKeys) - 1, a.refused);
    BoardSettings d = defaultBoardSettings();
    TEST_ASSERT_EQUAL_UINT16(d.pmWarmupS, a.settings.pmWarmupS);
    TEST_ASSERT_EQUAL_FLOAT(d.scd41OffsetC, a.settings.scd41OffsetC);
    TEST_ASSERT_EQUAL(d.scd41SelfCalibration, a.settings.scd41SelfCalibration);
    TEST_ASSERT_EQUAL(d.shtc3LowPower, a.settings.shtc3LowPower);
    TEST_ASSERT_EQUAL_UINT8(d.ledBrightnessPct, a.settings.ledBrightnessPct);
    TEST_ASSERT_EQUAL_UINT8(d.logLevel, a.settings.logLevel);
    TEST_ASSERT_EQUAL_UINT16(d.bsecSampleS, a.settings.bsecSampleS);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(d.ledPattern, a.settings.ledPattern, kLedTriggers);
    TEST_ASSERT_EQUAL_UINT16_ARRAY(d.ledLengthMs, a.settings.ledLengthMs, kLedTriggers);
}

void test_a_trigger_the_looks_leave_out_has_none() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"led\":{\"looks\":["
                           "{\"trigger\":\"well\",\"pattern\":\"solid\",\"length_s\":3}]}}", a));
    const uint8_t patterns[kLedTriggers] = {kLedNoLook, kLedNoLook, kLedNoLook, kLedNoLook, 1};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(patterns, a.settings.ledPattern, kLedTriggers);
    TEST_ASSERT_EQUAL_UINT16(3000, a.settings.ledLengthMs[4]);
    TEST_ASSERT_EQUAL_UINT32(0, a.refused);
}

void test_no_looks_leave_every_trigger_without_one() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"led\":{\"looks\":[]}}", a));
    for (uint8_t t = 0; t < kLedTriggers; ++t) TEST_ASSERT_EQUAL_UINT8(kLedNoLook, a.settings.ledPattern[t]);
    TEST_ASSERT_EQUAL_UINT32(0, a.refused);
}

void test_it_reads_the_doubles_and_triples() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"led\":{\"looks\":["
                           "{\"trigger\":\"no_wifi\",\"pattern\":\"double_flash\",\"length_s\":0.9},"
                           "{\"trigger\":\"post_failed\",\"pattern\":\"triple_flash\",\"length_s\":1.9},"
                           "{\"trigger\":\"sensor_missing\",\"pattern\":\"double_pulse\",\"length_s\":2},"
                           "{\"trigger\":\"well\",\"pattern\":\"triple_pulse\",\"length_s\":1.2}]}}", a));
    const uint8_t patterns[kLedTriggers] = {kLedNoLook, 4, 5, 6, 7};
    const uint16_t lengths[kLedTriggers] = {500, 900, 1900, 2000, 1200};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(patterns, a.settings.ledPattern, kLedTriggers);
    TEST_ASSERT_EQUAL_UINT16_ARRAY(lengths, a.settings.ledLengthMs, kLedTriggers);
    TEST_ASSERT_EQUAL_UINT32(0, a.refused);
}

void test_looks_the_dock_cannot_use_are_refused_whole() {
    const char* const bad[] = {
        "{\"trigger\":\"well\",\"pattern\":\"blink\",\"length_s\":1}",
        "{\"trigger\":\"Well\",\"pattern\":\"solid\",\"length_s\":1}",
        "{\"trigger\":\"well\",\"pattern\":\"solid\",\"length_s\":0.2}",
        "{\"trigger\":\"well\",\"pattern\":\"solid\",\"length_s\":10.5}",
        "{\"trigger\":\"well\",\"pattern\":\"solid\",\"length_s\":\"1\"}",
        "{\"trigger\":\"well\",\"pattern\":\"solid\"}",
        "{\"trigger\":\"well\",\"pattern\":\"solid\",\"length_s\":1},"
        "{\"trigger\":\"well\",\"pattern\":\"pulse\",\"length_s\":1}",
        "{\"pattern\":\"solid\",\"length_s\":1}",
        "{\"trigger\":\"well\",\"pattern\":\"double_flash\",\"length_s\":0.8}",
        "{\"trigger\":\"well\",\"pattern\":\"triple_pulse\",\"length_s\":1.1}",
    };
    char json[256];
    SettingsAnswer a;
    const BoardSettings d = defaultBoardSettings();
    for (const char* look : bad) {
        snprintf(json, sizeof(json),
                 "{\"version\":\"a\",\"led\":{\"looks\":[{\"trigger\":\"starting\",\"pattern\":"
                 "\"solid\",\"length_s\":1},%s]}}", look);
        TEST_ASSERT_TRUE(parse(json, a));
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(1u << kLedLooks, a.refused, look);
        TEST_ASSERT_EQUAL_UINT8_ARRAY_MESSAGE(d.ledPattern, a.settings.ledPattern, kLedTriggers, look);
        TEST_ASSERT_EQUAL_UINT16_ARRAY_MESSAGE(d.ledLengthMs, a.settings.ledLengthMs,
                                               kLedTriggers, look);
    }
}

void test_the_warm_up_limits_are_0_or_30_to_600() {
    const char* const good[] = {"0", "30", "600"};
    const char* const bad[] = {"29", "601", "-1", "35.5"};
    char json[80];
    SettingsAnswer a;
    for (const char* v : good) {
        snprintf(json, sizeof(json), "{\"version\":\"a\",\"pm\":{\"warmup_s\":%s}}", v);
        TEST_ASSERT_TRUE(parse(json, a));
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(0, a.refused, v);
    }
    for (const char* v : bad) {
        snprintf(json, sizeof(json), "{\"version\":\"a\",\"pm\":{\"warmup_s\":%s}}", v);
        TEST_ASSERT_TRUE(parse(json, a));
        TEST_ASSERT_EQUAL_UINT32_MESSAGE(1u << kPmWarmup, a.refused, v);
    }
}

void test_a_recalibration_out_of_range_is_not_run() {
    SettingsAnswer a;
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"recalibrate\":{\"id\":5,\"ppm\":3000}}", a));
    TEST_ASSERT_EQUAL_UINT32(0, a.recalibrateId);
    TEST_ASSERT_TRUE(parse("{\"version\":\"a\",\"recalibrate\":{\"id\":0,\"ppm\":420}}", a));
    TEST_ASSERT_EQUAL_UINT32(0, a.recalibrateId);
}

void test_an_answer_without_a_version_or_not_json_is_not_taken() {
    SettingsAnswer a;
    TEST_ASSERT_FALSE(parse("{\"pm\":{\"warmup_s\":0}}", a));
    TEST_ASSERT_FALSE(parse("{\"version\":\"\"}", a));
    TEST_ASSERT_FALSE(parse("{\"version\":\"0123456789abc\"}", a));
    TEST_ASSERT_FALSE(parse("[1]", a));
    TEST_ASSERT_FALSE(parse("<html>", a));
}

void test_refused_keys_are_named_as_the_server_names_them() {
    char buf[128];
    TEST_ASSERT_EQUAL_UINT(2, refusedJson(0, buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_STRING("[]", buf);
    refusedJson((1u << kScd41Offset) | (1u << kLedBrightness), buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("[\"scd41.temperature_offset_c\",\"led.brightness_pct\"]", buf);
    char every[kRefusedJsonBytes];
    TEST_ASSERT_TRUE(refusedJson((1u << kSettingKeys) - 1, every, sizeof(every)) > 0);
    char small[10];
    TEST_ASSERT_EQUAL_UINT(0, refusedJson(1u << kScd41Offset, small, sizeof(small)));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_the_defaults_are_the_servers);
    RUN_TEST(test_it_reads_every_key);
    RUN_TEST(test_a_whole_number_offset_is_a_number_too);
    RUN_TEST(test_a_key_the_answer_lacks_keeps_the_current_value);
    RUN_TEST(test_a_value_out_of_the_docks_limits_is_refused_and_the_current_kept);
    RUN_TEST(test_a_trigger_the_looks_leave_out_has_none);
    RUN_TEST(test_no_looks_leave_every_trigger_without_one);
    RUN_TEST(test_it_reads_the_doubles_and_triples);
    RUN_TEST(test_looks_the_dock_cannot_use_are_refused_whole);
    RUN_TEST(test_the_warm_up_limits_are_0_or_30_to_600);
    RUN_TEST(test_a_recalibration_out_of_range_is_not_run);
    RUN_TEST(test_an_answer_without_a_version_or_not_json_is_not_taken);
    RUN_TEST(test_refused_keys_are_named_as_the_server_names_them);
    return UNITY_END();
}
