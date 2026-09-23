// BSEC's state on its way to the server and back, and the rule for which of
// two saved copies BSEC runs on.
#include <unity.h>

#include <cstring>
#include <string>

#include "net/Calibration.h"

void setUp() {}
void tearDown() {}

static std::string encode(const char* text) {
    char out[64];
    base64Encode((const uint8_t*)text, strlen(text), out, sizeof(out));
    return out;
}

static std::string decode(const char* text) {
    uint8_t out[64];
    size_t n = base64Decode(text, strlen(text), out, sizeof(out));
    return std::string((const char*)out, n);
}

// ─── Base64 ──────────────────────────────────────────────────────────────

void test_base64_matches_the_rfc_4648_vectors() {
    const char* plain[] = {"", "f", "fo", "foo", "foob", "fooba", "foobar"};
    const char* coded[] = {"", "Zg==", "Zm8=", "Zm9v", "Zm9vYg==", "Zm9vYmE=", "Zm9vYmFy"};
    for (int i = 0; i < 7; ++i) {
        TEST_ASSERT_EQUAL_STRING(coded[i], encode(plain[i]).c_str());
        TEST_ASSERT_EQUAL_STRING(plain[i], decode(coded[i]).c_str());
    }
}

void test_base64_carries_a_whole_state_blob_there_and_back() {
    uint8_t blob[238];
    for (int i = 0; i < 238; ++i) blob[i] = (uint8_t)(i * 37 + 11);
    char text[400];
    const size_t n = base64Encode(blob, sizeof(blob), text, sizeof(text));
    TEST_ASSERT_EQUAL_UINT(320, n);
    uint8_t back[238];
    TEST_ASSERT_EQUAL_UINT(238, base64Decode(text, n, back, sizeof(back)));
    TEST_ASSERT_EQUAL_MEMORY(blob, back, 238);
}

void test_base64_writes_nothing_it_cannot_finish() {
    char small[4];
    TEST_ASSERT_EQUAL_UINT(0, base64Encode((const uint8_t*)"foo", 3, small, sizeof(small)));
    uint8_t out[2];
    TEST_ASSERT_EQUAL_UINT(0, base64Decode("Zm9v", 4, out, sizeof(out)));
    uint8_t any[8];
    TEST_ASSERT_EQUAL_UINT_MESSAGE(0, base64Decode("Zm9", 3, any, sizeof(any)), "not a whole quantum");
    TEST_ASSERT_EQUAL_UINT_MESSAGE(0, base64Decode("Zm!v", 4, any, sizeof(any)), "not the alphabet");
}

// ─── The block the POST carries ──────────────────────────────────────────

void test_calibration_block_matches_readings_md() {
    const uint8_t state[3] = {'f', 'o', 'o'};
    char buf[128];
    const size_t n = calibrationJson(state, 3, 3, 1757443200, 300, buf, sizeof(buf));
    TEST_ASSERT_EQUAL_STRING("{\"bme688\":{\"state\":\"Zm9v\",\"accuracy\":3,\"saved\":1757443200,\"sample_s\":300}}", buf);
    TEST_ASSERT_EQUAL_UINT(strlen(buf), n);
    char tiny[30];
    TEST_ASSERT_EQUAL_UINT(0, calibrationJson(state, 3, 3, 1757443200, 300, tiny, sizeof(tiny)));
    TEST_ASSERT_EQUAL_STRING("", tiny);
}

void test_a_member_is_spliced_before_the_closing_brace() {
    char out[96];
    const size_t n = withMember("{\"ts\":1}", "calibration", "{\"bme688\":{}}", out, sizeof(out));
    TEST_ASSERT_EQUAL_STRING("{\"ts\":1,\"calibration\":{\"bme688\":{}}}", out);
    TEST_ASSERT_EQUAL_UINT(strlen(out), n);
    TEST_ASSERT_EQUAL_UINT(0, withMember("[1]", "k", "{}", out, sizeof(out)));
    TEST_ASSERT_EQUAL_UINT(0, withMember("{\"ts\":1}", "k", "x", out, sizeof(out)));
}

// ─── The server's answer ─────────────────────────────────────────────────

void test_the_servers_answer_is_decoded() {
    uint8_t state[238];
    uint32_t len = 0, saved = 0;
    uint8_t accuracy = 0;
    uint16_t rate = 0;
    TEST_ASSERT_TRUE(parseBme688Calibration(
        "{\"bme688\": {\"accuracy\": 3, \"saved\": 1757443200, \"sample_s\": 300,"
        " \"state\": \"Zm9vYmFy\"}}",
        state, sizeof(state), len, accuracy, saved, rate));
    TEST_ASSERT_EQUAL_UINT16(300, rate);
    TEST_ASSERT_EQUAL_UINT32(6, len);
    TEST_ASSERT_EQUAL_MEMORY("foobar", state, 6);
    TEST_ASSERT_EQUAL_UINT8(3, accuracy);
    TEST_ASSERT_EQUAL_UINT32(1757443200, saved);
}

void test_an_answer_without_a_usable_bme688_entry_is_refused() {
    uint8_t state[4];
    uint32_t len = 0, saved = 0;
    uint8_t accuracy = 0;
    uint16_t rate = 0;
    TEST_ASSERT_FALSE(parseBme688Calibration("{}", state, sizeof(state), len, accuracy, saved, rate));
    TEST_ASSERT_FALSE(parseBme688Calibration("{\"scd41\":{\"offset\":1.5}}", state, sizeof(state),
                                             len, accuracy, saved, rate));
    TEST_ASSERT_FALSE_MESSAGE(
        parseBme688Calibration("{\"bme688\":{\"state\":\"Zm9vYmFy\",\"accuracy\":3,\"saved\":1,\"sample_s\":3}}",
                               state, sizeof(state), len, accuracy, saved, rate),
        "six bytes do not fit in four");
    TEST_ASSERT_FALSE_MESSAGE(
        parseBme688Calibration("{\"bme688\":{\"state\":\"Zg==\",\"accuracy\":7,\"saved\":1,\"sample_s\":3}}",
                               state, sizeof(state), len, accuracy, saved, rate),
        "accuracy runs 0 to 3");
    TEST_ASSERT_FALSE(parseBme688Calibration("{\"bme688\":{\"state\":\"Zg==\",\"saved\":1}}", state,
                                             sizeof(state), len, accuracy, saved, rate));
    TEST_ASSERT_FALSE_MESSAGE(
        parseBme688Calibration("{\"bme688\":{\"state\":\"Zg==\",\"accuracy\":3,\"saved\":1}}",
                               state, sizeof(state), len, accuracy, saved, rate),
        "a copy that does not say its rate cannot be matched to BSEC's");
}

// ─── Which copy BSEC runs on ─────────────────────────────────────────────

static const uint32_t T = 1757443200;

static bool prefer(const SavedCopy& nvs, const SavedCopy& server) {
    return chooseCopy(nvs, server).takeServer;
}

static std::string why(const SavedCopy& nvs, const SavedCopy& server) {
    char buf[80];
    const size_t n = describeChoice(nvs, server, chooseCopy(nvs, server), buf, sizeof(buf));
    return std::string(buf, n);
}

void test_the_servers_copy_wins_when_nvs_has_none() {
    TEST_ASSERT_TRUE(prefer({false, 0, 0}, {true, 1, T}));
}

void test_there_is_nothing_to_weigh_without_a_server_copy() {
    TEST_ASSERT_FALSE(prefer({false, 0, 0}, {false, 0, 0}));
}

void test_a_more_accurate_copy_wins_and_a_less_accurate_one_never_does() {
    TEST_ASSERT_TRUE(prefer({true, 2, T}, {true, 3, T - 86400}));
    TEST_ASSERT_FALSE(prefer({true, 3, T - 86400}, {true, 2, T}));
}

void test_at_the_same_accuracy_only_a_copy_over_an_hour_newer_wins() {
    TEST_ASSERT_TRUE(prefer({true, 3, T}, {true, 3, T + kNewerByS + 1}));
    TEST_ASSERT_FALSE(prefer({true, 3, T}, {true, 3, T + kNewerByS}));
    TEST_ASSERT_FALSE(prefer({true, 3, T}, {true, 3, T - 60}));
}

void test_a_copy_with_no_time_counts_as_the_older() {
    TEST_ASSERT_TRUE(prefer({true, 3, 0}, {true, 3, T}));
    TEST_ASSERT_FALSE(prefer({true, 3, T}, {true, 3, 0}));
    TEST_ASSERT_FALSE(prefer({true, 3, 0}, {true, 3, 0}));
}

void test_the_log_says_which_state_was_selected_and_why() {
    TEST_ASSERT_EQUAL_STRING("NVS selected (server state not found)", why({true, 3, T}, {false, 0, 0}).c_str());
    TEST_ASSERT_EQUAL_STRING("none selected (server state not found)", why({false, 0, 0}, {false, 0, 0}).c_str());
    TEST_ASSERT_EQUAL_STRING("server selected (no NVS state)", why({false, 0, 0}, {true, 1, T}).c_str());
    TEST_ASSERT_EQUAL_STRING("server selected (more accurate: 3 vs 1)", why({true, 1, T}, {true, 3, T}).c_str());
    TEST_ASSERT_EQUAL_STRING("NVS selected (server less accurate: 1 vs 3)", why({true, 3, T}, {true, 1, T}).c_str());
    TEST_ASSERT_EQUAL_STRING("server selected (same accuracy, 2 h newer)", why({true, 3, T}, {true, 3, T + 7200}).c_str());
    TEST_ASSERT_EQUAL_STRING("NVS selected (same accuracy, only 11 min newer)", why({true, 3, T}, {true, 3, T + 660}).c_str());
    TEST_ASSERT_EQUAL_STRING("NVS selected (same accuracy, not newer)", why({true, 3, T}, {true, 3, T - 60}).c_str());
    TEST_ASSERT_EQUAL_STRING("server selected (NVS state has no time)", why({true, 3, 0}, {true, 3, T}).c_str());
    TEST_ASSERT_EQUAL_STRING("NVS selected (server state has no time)", why({true, 3, T}, {true, 3, 0}).c_str());
}

void test_a_choice_that_does_not_fit_writes_nothing() {
    char buf[8];
    const SavedCopy nvs = {true, 3, T}, server = {true, 1, T};
    TEST_ASSERT_EQUAL_UINT(0, describeChoice(nvs, server, chooseCopy(nvs, server), buf, sizeof(buf)));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_base64_matches_the_rfc_4648_vectors);
    RUN_TEST(test_base64_carries_a_whole_state_blob_there_and_back);
    RUN_TEST(test_base64_writes_nothing_it_cannot_finish);
    RUN_TEST(test_calibration_block_matches_readings_md);
    RUN_TEST(test_a_member_is_spliced_before_the_closing_brace);
    RUN_TEST(test_the_servers_answer_is_decoded);
    RUN_TEST(test_an_answer_without_a_usable_bme688_entry_is_refused);
    RUN_TEST(test_the_servers_copy_wins_when_nvs_has_none);
    RUN_TEST(test_there_is_nothing_to_weigh_without_a_server_copy);
    RUN_TEST(test_a_more_accurate_copy_wins_and_a_less_accurate_one_never_does);
    RUN_TEST(test_at_the_same_accuracy_only_a_copy_over_an_hour_newer_wins);
    RUN_TEST(test_a_copy_with_no_time_counts_as_the_older);
    RUN_TEST(test_the_log_says_which_state_was_selected_and_why);
    RUN_TEST(test_a_choice_that_does_not_fit_writes_nothing);
    return UNITY_END();
}
