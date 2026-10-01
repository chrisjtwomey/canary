// The mean of the BME688 cycles between two readings: what each value counts,
// and what it falls back to.
#include <unity.h>

#include "sensors/Bme688Mean.h"

static Bme688Data cycle(float tempC, float gasOhm, bool heatStable, float iaq, uint8_t accuracy) {
    Bme688Data d = {};
    d.tempC = tempC;
    d.pressureHpa = 1000.0f + tempC;
    d.rhPct = 2 * tempC;
    d.gasOhm = gasOhm;
    d.gasValid = true;
    d.heatStable = heatStable;
    d.iaq = iaq;
    d.iaqAccuracy = accuracy;
    d.hasIaq = true;
    d.staticIaq = iaq / 2;
    d.staticIaqAccuracy = accuracy;
    d.hasStaticIaq = true;
    return d;
}

static Bme688Data mean, newest;
static Bme688Samples n;

void setUp() {
    mean = Bme688Data();
    newest = Bme688Data();
    n = Bme688Samples();
}
void tearDown() {}

void test_temperature_pressure_and_humidity_are_the_mean_of_every_cycle() {
    Bme688Mean m;
    m.add(cycle(20, 100000, true, 50, 3));
    m.add(cycle(22, 100000, true, 50, 3));
    TEST_ASSERT_TRUE(m.take(mean, newest, n));
    TEST_ASSERT_EQUAL_FLOAT(21.0f, mean.tempC);
    TEST_ASSERT_EQUAL_FLOAT(1021.0f, mean.pressureHpa);
    TEST_ASSERT_EQUAL_FLOAT(42.0f, mean.rhPct);
    TEST_ASSERT_EQUAL_FLOAT(22.0f, newest.tempC);
    TEST_ASSERT_EQUAL_UINT16(2, n.cycles);
}

void test_the_gas_resistance_counts_only_a_heater_at_its_target() {
    Bme688Mean m;
    m.add(cycle(20, 100000, true, 50, 3));
    m.add(cycle(20, 900000, false, 50, 3));
    TEST_ASSERT_TRUE(m.take(mean, newest, n));
    TEST_ASSERT_EQUAL_FLOAT(100000.0f, mean.gasOhm);
    TEST_ASSERT_TRUE(mean.gasValid && mean.heatStable);
}

void test_without_a_good_gas_cycle_the_newest_stands_unflagged() {
    Bme688Mean m;
    m.add(cycle(20, 900000, false, 50, 3));
    TEST_ASSERT_TRUE(m.take(mean, newest, n));
    TEST_ASSERT_EQUAL_FLOAT(900000.0f, mean.gasOhm);
    TEST_ASSERT_FALSE(mean.heatStable);
}

void test_each_index_counts_only_cycles_at_high_accuracy() {
    Bme688Mean m;
    m.add(cycle(20, 100000, true, 60, 3));
    m.add(cycle(20, 100000, true, 200, 1));
    m.add(cycle(20, 100000, true, 80, 3));
    TEST_ASSERT_TRUE(m.take(mean, newest, n));
    TEST_ASSERT_EQUAL_FLOAT(70.0f, mean.iaq);
    TEST_ASSERT_EQUAL_UINT8(3, mean.iaqAccuracy);
    TEST_ASSERT_EQUAL_FLOAT(35.0f, mean.staticIaq);
    TEST_ASSERT_EQUAL_UINT8(3, mean.staticIaqAccuracy);
    TEST_ASSERT_EQUAL_UINT16(3, n.cycles);
    TEST_ASSERT_EQUAL_UINT16(2, n.iaq);
    TEST_ASSERT_EQUAL_UINT16(2, n.staticIaq);
    TEST_ASSERT_EQUAL_FLOAT(80.0f, newest.iaq);
}

void test_without_an_accurate_cycle_the_newest_index_stands_with_its_accuracy() {
    Bme688Mean m;
    m.add(cycle(20, 100000, true, 200, 1));
    m.add(cycle(20, 100000, true, 150, 2));
    TEST_ASSERT_TRUE(m.take(mean, newest, n));
    TEST_ASSERT_EQUAL_FLOAT(150.0f, mean.iaq);
    TEST_ASSERT_EQUAL_UINT8(2, mean.iaqAccuracy);
    TEST_ASSERT_EQUAL_UINT16(0, n.iaq);
    TEST_ASSERT_EQUAL_UINT16(0, n.staticIaq);
}

void test_take_empties_the_mean() {
    Bme688Mean m;
    TEST_ASSERT_FALSE(m.take(mean, newest, n));
    m.add(cycle(20, 100000, true, 50, 3));
    TEST_ASSERT_TRUE(m.take(mean, newest, n));
    TEST_ASSERT_FALSE(m.take(mean, newest, n));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_temperature_pressure_and_humidity_are_the_mean_of_every_cycle);
    RUN_TEST(test_the_gas_resistance_counts_only_a_heater_at_its_target);
    RUN_TEST(test_without_a_good_gas_cycle_the_newest_stands_unflagged);
    RUN_TEST(test_each_index_counts_only_cycles_at_high_accuracy);
    RUN_TEST(test_without_an_accurate_cycle_the_newest_index_stands_with_its_accuracy);
    RUN_TEST(test_take_empties_the_mean);
    return UNITY_END();
}
