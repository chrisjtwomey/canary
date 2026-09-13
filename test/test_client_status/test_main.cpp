// The client object the board posts beside its readings, and the URL it
// posts to.
#include <unity.h>
#include <cstring>

#include "net/ClientStatus.h"
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
    s.backlogHeld = 7; s.backlogStore = "psram";
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
    TEST_ASSERT_NOT_NULL(strstr(buf, "\"backlog\":{\"held\":7,\"store\":\"psram\"}"));
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

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_client_json_carries_every_field);
    RUN_TEST(test_client_json_needs_room_or_writes_nothing);
    RUN_TEST(test_client_object_is_spliced_before_the_closing_brace);
    RUN_TEST(test_splice_rejects_non_objects_and_small_buffers);
    RUN_TEST(test_url_origin_keeps_scheme_host_and_port);
    return UNITY_END();
}
