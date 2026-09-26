// When the status light's Poor air quality and Calibrating triggers hold,
// judged from the latest reading.
#include <unity.h>

#include "dock/LightTriggers.h"

static const AirLimits kLimits = {1500, 37.5f, 150};

// A reading from every sensor, the air clean and BSEC calibrated.
static Readings clean() {
    Readings r = {};
    r.scd41Valid = true;
    r.scd41.co2Ppm = 600;
    r.pmValid = true;
    r.pm.pm2_5 = 5;
    r.bme688Valid = true;
    r.bme688.hasIaq = true;
    r.bme688.iaq = 40.0f;
    r.bme688.iaqAccuracy = 3;
    return r;
}

void setUp() {}
void tearDown() {}

void test_clean_air_is_not_poor() {
    TEST_ASSERT_FALSE(poorAir(clean(), kLimits));
}

void test_co2_at_its_limit_is_poor_air() {
    Readings r = clean();
    r.scd41.co2Ppm = 1499;
    TEST_ASSERT_FALSE(poorAir(r, kLimits));
    r.scd41.co2Ppm = 1500;
    TEST_ASSERT_TRUE(poorAir(r, kLimits));
}

void test_pm25_at_its_limit_is_poor_air() {
    Readings r = clean();
    r.pm.pm2_5 = 37;
    TEST_ASSERT_FALSE(poorAir(r, kLimits));
    r.pm.pm2_5 = 38;
    TEST_ASSERT_TRUE(poorAir(r, kLimits));
}

void test_iaq_at_its_limit_is_poor_air_once_bsec_is_calibrated() {
    Readings r = clean();
    r.bme688.iaq = 150.0f;
    TEST_ASSERT_TRUE(poorAir(r, kLimits));
    r.bme688.iaqAccuracy = 2;
    TEST_ASSERT_TRUE(poorAir(r, kLimits));
    r.bme688.iaqAccuracy = 1;
    TEST_ASSERT_FALSE(poorAir(r, kLimits));
}

void test_a_reading_that_is_not_valid_is_not_judged() {
    Readings r = clean();
    r.scd41.co2Ppm = 3000;
    r.pm.pm2_5 = 200;
    r.bme688.iaq = 400.0f;
    r.scd41Valid = false;
    r.pmValid = false;
    r.bme688.hasIaq = false;
    TEST_ASSERT_FALSE(poorAir(r, kLimits));
}

void test_bsec_below_its_calibrated_accuracy_is_calibrating() {
    Readings r = clean();
    TEST_ASSERT_FALSE(calibrating(r, false));
    r.bme688.iaqAccuracy = 1;
    TEST_ASSERT_TRUE(calibrating(r, false));
    r.bme688.iaqAccuracy = 0;
    TEST_ASSERT_TRUE(calibrating(r, false));
}

void test_a_recalibration_waiting_for_the_scd41_is_calibrating() {
    TEST_ASSERT_TRUE(calibrating(clean(), true));
}

void test_without_an_index_nothing_is_calibrating() {
    Readings r = clean();
    r.bme688.hasIaq = false;
    r.bme688.iaqAccuracy = 0;
    TEST_ASSERT_FALSE(calibrating(r, false));
    TEST_ASSERT_FALSE(calibrating(Readings{}, false));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_clean_air_is_not_poor);
    RUN_TEST(test_co2_at_its_limit_is_poor_air);
    RUN_TEST(test_pm25_at_its_limit_is_poor_air);
    RUN_TEST(test_iaq_at_its_limit_is_poor_air_once_bsec_is_calibrated);
    RUN_TEST(test_a_reading_that_is_not_valid_is_not_judged);
    RUN_TEST(test_bsec_below_its_calibrated_accuracy_is_calibrating);
    RUN_TEST(test_a_recalibration_waiting_for_the_scd41_is_calibrating);
    RUN_TEST(test_without_an_index_nothing_is_calibrating);
    return UNITY_END();
}
