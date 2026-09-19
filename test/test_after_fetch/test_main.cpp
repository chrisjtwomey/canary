// What the head does once the server has answered: the page or the version
// notice, and in either case the update on offer.
#include <unity.h>
#include <string>

#include "head/AfterFetch.h"

static std::string calls;
static bool drawWorks = true;

static bool drawPage()          { calls += "page "; return drawWorks; }
static bool drawVersionNotice() { calls += "notice "; return drawWorks; }
static void succeeded()         { calls += "succeeded "; }
static void takeOffer()         { calls += "offer "; }

static const AfterFetchSteps steps = {drawPage, drawVersionNotice, succeeded, takeOffer};

void setUp() {
    calls.clear();
    drawWorks = true;
}
void tearDown() {}

void test_a_compatible_server_gets_its_page_then_the_offer() {
    TEST_ASSERT_TRUE(afterFetch(true, steps));
    TEST_ASSERT_EQUAL_STRING("page succeeded offer ", calls.c_str());
}

void test_the_version_notice_still_takes_the_offer() {
    TEST_ASSERT_TRUE(afterFetch(false, steps));
    TEST_ASSERT_EQUAL_STRING("notice succeeded offer ", calls.c_str());
}

void test_nothing_drawn_is_a_failure_and_takes_nothing() {
    drawWorks = false;
    TEST_ASSERT_FALSE(afterFetch(true, steps));
    TEST_ASSERT_EQUAL_STRING("page ", calls.c_str());
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_a_compatible_server_gets_its_page_then_the_offer);
    RUN_TEST(test_the_version_notice_still_takes_the_offer);
    RUN_TEST(test_nothing_drawn_is_a_failure_and_takes_nothing);
    return UNITY_END();
}
