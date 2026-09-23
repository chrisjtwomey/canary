// The client object the board posts beside its readings, and the URL it
// posts to.
#include <unity.h>
#include <cstring>

#include "net/ClientStatus.h"
#include "sensors/SensorHealth.h"
#include "net/Url.h"

static ClientStatus status() {
    ClientStatus s = {};
    s.board = "Inkplate5V2"; s.version = "v0.1.0"; s.ip = "192.168.1.42";
    s.rssi = -61; s.uptimeS = 8040;
    s.heapFree = 120000; s.heapSize = 327680; s.psramFree = 4000000; s.psramSize = 4194304;
    s.panelTempC = 27; s.width = 1280; s.height = 720; s.rotation = 0;
    s.mockSensors = true;
    s.shtc3 = true; s.scd41 = true; s.pm = false; s.bme688 = true;
    s.nextUrl = "http://h:8080/day.png"; s.nextInS = 120; s.backoffStep = 0;
    s.fetchOk = 12; s.fetchFailed = 1;
    s.backlogHeld = 7; s.backlogCapacity = 1480; s.backlogStore = "psram";
    s.bsecRunning = true; s.bsecRestored = true; s.iaqAccuracy = 2;
    s.bsecLateCalls = 3; s.bsecSavedEpoch = 1757443200;
    return s;
}

void setUp() {}
void tearDown() {}

void test_client_json_carries_every_field() {
    char buf[768];
    size_t n = clientStatusJson(status(), buf, sizeof(buf));
    TEST_ASSERT_EQUAL_UINT(strlen(buf), n);
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"board\":\"Inkplate5V2\""));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"rssi\":-61"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"uptime_s\":8040"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"heap_size\":327680"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"panel_temp_c\":27"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"mock_sensors\":true"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"sensors\":{\"shtc3\":true,\"scd41\":true,\"pmsa003i\":false,\"bme688\":true}"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"fetch\":{\"next_url\":\"http://h:8080/day.png\",\"next_in_s\":120,\"backoff_step\":0,\"ok\":12,\"failed\":1}"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"backlog\":{\"held\":7,\"capacity\":1480,\"store\":\"psram\"}"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"bsec\":{\"running\":true,\"restored\":true,\"accuracy\":2"
                                     ",\"late\":3,\"saved\":1757443200}"));
    TEST_ASSERT_EQUAL_CHAR('{', buf[0]);
    TEST_ASSERT_EQUAL_CHAR('}', buf[n - 1]);
}

void test_client_json_needs_room_or_writes_nothing() {
    char buf[64];
    TEST_ASSERT_EQUAL_UINT(0, clientStatusJson(status(), buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_STRING("", buf);
}

void test_client_object_is_spliced_before_the_closing_brace() {
    char out[128];
    size_t n = withClientStatus("{\"ts\":1,\"co2_ppm\":640}", "{\"rssi\":-61}", out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("{\"ts\":1,\"co2_ppm\":640,\"client\":{\"rssi\":-61}}", out);
    TEST_ASSERT_EQUAL_UINT(strlen(out), n);
}

void test_splice_rejects_non_objects_and_small_buffers() {
    char out[128];
    TEST_ASSERT_EQUAL_UINT(0, withClientStatus("[1]", "{}", out, sizeof(out)));
    TEST_ASSERT_EQUAL_UINT(0, withClientStatus("{\"ts\":1}", "x", out, sizeof(out)));
    char small[8];
    TEST_ASSERT_EQUAL_UINT(0, withClientStatus("{\"ts\":1}", "{}", small, sizeof(small)));
    TEST_ASSERT_EQUAL_STRING("", small);
}

void test_url_origin_keeps_scheme_host_and_port() {
    char out[64];
    TEST_ASSERT_EQUAL_UINT(24, urlOrigin("http://192.168.1.20:8080/breathe.png", out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("http://192.168.1.20:8080", out);
    urlOrigin("https://epd.local", out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("https://epd.local", out);
    TEST_ASSERT_EQUAL_UINT(0, urlOrigin("no-scheme/x.png", out, sizeof(out)));
    TEST_ASSERT_EQUAL_STRING("", out);
    TEST_ASSERT_EQUAL_UINT(0, urlOrigin("http:///x.png", out, sizeof(out)));
    char tiny[8];
    TEST_ASSERT_EQUAL_UINT(0, urlOrigin("http://host:8080/x", tiny, sizeof(tiny)));
}

// ─── The health object ───────────────────────────────────────────────────

static SensorHealth fullHealth() {
    SensorHealth h = {};
    h.restarts = 2;
    h.pmBadFrames = 5; h.shtc3CrcFailures = 1; h.scd41CrcFailures = 0;
    h.bme688Seen = true; h.gasValid = true; h.heatStable = false;
    h.scd41Read = true; h.scd41Serial = 0x9A3BC0FFEE41ull;
    h.ascKnown = true; h.asc = true;
    h.offsetKnown = true; h.offsetC = 4.0f;
    h.pressureKnown = true; h.pressurePa = 101262;
    h.bme688HeaterC = 300; h.bme688HeaterMs = 100;
    h.pmSeen = true; h.pmVersion = 0x97; h.pmError = 0;
    h.shtc3IdKnown = true; h.shtc3Id = 0x0887; h.shtc3LowPower = false;
    return h;
}

void test_health_carries_the_counts_and_each_sensors_settings() {
    char buf[448];
    TEST_ASSERT_TRUE(healthJson(fullHealth(), buf, sizeof(buf)) > 0);
    TEST_ASSERT_EQUAL_STRING(
        "{\"restarts\":2,\"checksum_failures\":{\"pmsa003i\":5,\"shtc3\":1,\"scd41\":0}"
        ",\"bme688\":{\"gas_valid\":true,\"heat_stable\":false,\"heater_c\":300,\"heater_ms\":100}"
        ",\"scd41\":{\"serial\":\"9a3bc0ffee41\",\"asc\":true,\"offset_c\":4.0,\"pressure_hpa\":1013}"
        ",\"pmsa003i\":{\"version\":151,\"error\":0}"
        ",\"shtc3\":{\"id\":\"0887\",\"low_power\":false}}", buf);
}

void test_health_leaves_out_what_is_not_known() {
    SensorHealth h = fullHealth();
    h.bme688Seen = false;
    h.ascKnown = false;
    h.offsetKnown = false;
    h.pressureKnown = false;
    h.pmSeen = false;
    h.shtc3IdKnown = false;
    char buf[448];
    healthJson(h, buf, sizeof(buf));
    TEST_ASSERT_NULL(strstr(buf, "bme688"));
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"scd41\":{\"serial\":\"9a3bc0ffee41\"}"));
    h.scd41Read = false;
    healthJson(h, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING(
        "{\"restarts\":2,\"checksum_failures\":{\"pmsa003i\":5,\"shtc3\":1,\"scd41\":0}}", buf);
}

void test_health_that_does_not_fit_writes_nothing() {
    char buf[60];
    TEST_ASSERT_EQUAL_UINT(0, healthJson(fullHealth(), buf, sizeof(buf)));
    TEST_ASSERT_EQUAL_STRING("", buf);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_client_json_carries_every_field);
    RUN_TEST(test_client_json_needs_room_or_writes_nothing);
    RUN_TEST(test_client_object_is_spliced_before_the_closing_brace);
    RUN_TEST(test_splice_rejects_non_objects_and_small_buffers);
    RUN_TEST(test_url_origin_keeps_scheme_host_and_port);
    RUN_TEST(test_health_carries_the_counts_and_each_sensors_settings);
    RUN_TEST(test_health_leaves_out_what_is_not_known);
    RUN_TEST(test_health_that_does_not_fit_writes_nothing);
    return UNITY_END();
}
