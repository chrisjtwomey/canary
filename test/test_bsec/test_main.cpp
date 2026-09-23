// BsecRunner against a stand-in for Bosch's binary: the order it drives BSEC
// in, what it hands the sensor, what it keeps, and when it saves the state.
#include <unity.h>

#include <cstring>
#include <initializer_list>
#include <string>
#include <vector>

#include "sensors/BsecRunner.h"

class FakeClock : public IClock {
public:
    uint32_t now = 0;
    uint32_t millis() const override { return now; }
    void waitMs(uint32_t ms) override { now += ms; }
};

// BSEC as its interface promises: a forced cycle at the rate it was started
// at, and the index at whatever accuracy the test sets.
class FakeBsec : public IBsec {
public:
    std::string          calls;
    std::vector<uint8_t> stateSet;
    int     initResult = kOk;
    int     setStateResult = kOk;
    int     nextStatus = kOk;
    int     controls = 0;
    int     steps = 0;
    uint8_t accuracy = 0;
    uint16_t initRate = 0, subscribeRate = 0;

    int init(uint16_t sampleS) override {
        calls += "init ";
        initRate = sampleS;
        return initResult;
    }
    int setState(const uint8_t* state, uint32_t len) override {
        calls += "state ";
        stateSet.assign(state, state + len);
        return setStateResult;
    }
    int getState(uint8_t* state, uint32_t max, uint32_t* len) override {
        const uint32_t n = max < 10 ? max : 10;
        memset(state, 0x5A, n);
        *len = n;
        return kOk;
    }
    int subscribe(uint16_t sampleS) override {
        calls += "subscribe ";
        subscribeRate = sampleS;
        return kOk;
    }
    int sensorControl(int64_t nowNs, BsecRequest& r) override {
        ++controls;
        r = BsecRequest();
        r.measure = true;
        r.heaterC = 320;
        r.heaterMs = 197;
        r.osT = 2;
        r.osP = 5;
        r.osH = 1;
        r.runGas = true;
        r.nextCallNs = nowNs + (int64_t)subscribeRate * 1000000000LL;
        const int status = nextStatus;
        nextStatus = kOk;
        return status;
    }
    int doSteps(int64_t, const Bme688Data&, BsecResult& result) override {
        ++steps;
        result.hasIaq = true;
        result.iaq = 42.0f;
        result.iaqAccuracy = accuracy;
        return kOk;
    }
};

// A sensor that records the settings it is given, and can be taken away.
class SpyBme : public IBme688 {
public:
    bool     present = true;
    bool     gasValid = true;
    int      begins = 0;
    int      settingsWrites = 0;
    uint8_t  osT = 0, osP = 0, osH = 0;
    uint16_t heaterC = 0, heaterMs = 0;

    bool begin(uint32_t) override {
        ++begins;
        return present;
    }
    void setOversampling(uint8_t t, uint8_t p, uint8_t h) override {
        ++settingsWrites;
        osT = t;
        osP = p;
        osH = h;
    }
    void setHeaterProfile(uint16_t c, uint16_t ms) override {
        heaterC = c;
        heaterMs = ms;
    }
    bool startForced(uint32_t) override { return present; }
    uint32_t measurementMs() const override { return heaterMs + 10u; }
    bool fetchData(uint32_t, Bme688Data& d) override {
        if (!present) return false;
        d = Bme688Data();
        d.tempC = 22.0f;
        d.pressureHpa = 1010.0f;
        d.rhPct = 40.0f;
        d.gasOhm = 100000.0f;
        d.gasValid = gasValid;
        d.heatStable = true;
        return true;
    }
    uint8_t chipId() override { return 0x61; }
};

class FakeStore : public IBsecStateStore {
public:
    bool      has = false;
    BsecState stored = {};
    int       saves = 0;

    bool load(BsecState& out) override {
        if (!has) return false;
        out = stored;
        return true;
    }
    bool save(const BsecState& state) override {
        stored = state;
        has = true;
        ++saves;
        return true;
    }
};

static uint32_t fakeEpoch = 0;
static uint32_t epochNow() { return fakeEpoch; }

static FakeClock*  clk;
static FakeBsec*   bsec;
static SpyBme*     bme;
static FakeStore*  store;
static BsecRunner* runner;

void setUp() {
    fakeEpoch = 0;
    clk = new FakeClock();
    bsec = new FakeBsec();
    bme = new SpyBme();
    store = new FakeStore();
    runner = new BsecRunner(*bsec, *bme, *clk, *store, epochNow);
}

void tearDown() {
    delete runner;
    delete store;
    delete bme;
    delete bsec;
    delete clk;
}

static BsecState stateOf(std::initializer_list<uint8_t> bytes, uint8_t accuracy, uint32_t saved,
                         uint16_t sampleS = IBsec::kLpSampleS) {
    BsecState s = {};
    s.sampleS = sampleS;
    for (uint8_t b : bytes) s.blob[s.len++] = b;
    s.accuracy = accuracy;
    s.savedEpoch = saved;
    return s;
}

// The task, for `ms` of clock: step, then sleep what the step says.
static void runFor(uint32_t ms) {
    const uint32_t until = clk->now + ms;
    while (clk->now < until) {
        const uint32_t wait = runner->step();
        clk->now += wait ? wait : 1;
    }
}

// ─── Starting ────────────────────────────────────────────────────────────

void test_begin_restores_the_stored_state_between_init_and_subscribe() {
    store->has = true;
    store->stored = stateOf({1, 2, 3}, 3, 1000);
    BsecState loaded;
    TEST_ASSERT_TRUE(runner->begin(&loaded));
    TEST_ASSERT_EQUAL_STRING("init state subscribe ", bsec->calls.c_str());
    TEST_ASSERT_EQUAL_UINT(3, bsec->stateSet.size());
    TEST_ASSERT_EQUAL_UINT8(2, bsec->stateSet[1]);
    TEST_ASSERT_TRUE(runner->status().restored);
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(1000, loaded.savedEpoch, "the loop weighs it against the server's copy");
}

void test_begin_without_a_stored_state_starts_from_nothing() {
    BsecState loaded;
    TEST_ASSERT_TRUE(runner->begin(&loaded));
    TEST_ASSERT_EQUAL_STRING("init subscribe ", bsec->calls.c_str());
    TEST_ASSERT_FALSE(runner->status().restored);
    TEST_ASSERT_EQUAL_UINT32(0, loaded.len);
}

void test_a_state_bsec_refuses_means_starting_from_nothing() {
    store->has = true;
    store->stored = stateOf({1, 2, 3}, 3, 1000);
    bsec->setStateResult = -34;   // BSEC_E_CONFIG_VERSIONMISMATCH
    TEST_ASSERT_TRUE(runner->begin());
    TEST_ASSERT_EQUAL_STRING("init state init subscribe ", bsec->calls.c_str());
    TEST_ASSERT_FALSE(runner->status().restored);
}

void test_bsec_that_will_not_start_is_tried_again() {
    bsec->initResult = -33;   // BSEC_E_CONFIG_FAIL
    TEST_ASSERT_FALSE(runner->begin());
    TEST_ASSERT_FALSE(runner->status().started);
    TEST_ASSERT_FALSE(runner->status().running);
    TEST_ASSERT_EQUAL_UINT32(BsecRunner::kRetryMs, runner->step());

    bsec->initResult = IBsec::kOk;
    runFor(10000);
    TEST_ASSERT_TRUE(runner->status().started);
    TEST_ASSERT_TRUE(runner->status().running);
    TEST_ASSERT_TRUE(bsec->steps > 0);
}

void test_bsec_starts_while_the_sensor_is_missing() {
    bme->present = false;
    TEST_ASSERT_FALSE(runner->begin());
    TEST_ASSERT_TRUE_MESSAGE(runner->status().started, "BSEC took its configuration");
    TEST_ASSERT_FALSE(runner->status().running);

    bme->present = true;
    runFor(10000);
    TEST_ASSERT_TRUE(runner->status().running);
}

// ─── Cycles ──────────────────────────────────────────────────────────────

void test_a_step_runs_the_cycle_bsec_asks_for_and_keeps_the_index() {
    runner->begin();
    bsec->accuracy = 1;
    const uint32_t wait = runner->step();

    TEST_ASSERT_EQUAL_INT(1, bsec->steps);
    Bme688Data d;
    uint32_t at = 0;
    TEST_ASSERT_TRUE(runner->latest(d, at));
    TEST_ASSERT_TRUE(d.hasIaq);
    TEST_ASSERT_EQUAL_FLOAT(42.0f, d.iaq);
    TEST_ASSERT_EQUAL_UINT8(1, d.iaqAccuracy);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 1010.0f, d.pressureHpa);
    TEST_ASSERT_UINT32_WITHIN_MESSAGE(250, 3000, wait, "BSEC asks again in 3 s, less the cycle");
}

void test_bsec_is_not_asked_before_the_time_it_gave() {
    runner->begin();
    runner->step();
    clk->now += 1000;
    const uint32_t wait = runner->step();
    TEST_ASSERT_EQUAL_INT(1, bsec->controls);
    TEST_ASSERT_UINT32_WITHIN(250, 2000, wait);
}

void test_a_late_call_is_counted_and_the_cycle_still_runs() {
    runner->begin();
    bsec->nextStatus = IBsec::kLateCall;
    runner->step();
    TEST_ASSERT_EQUAL_UINT32(1, runner->status().lateCalls);
    TEST_ASSERT_EQUAL_INT(1, bsec->steps);
}

void test_bsec_settings_reach_the_sensor_as_multipliers_once() {
    runner->begin();
    runner->step();
    TEST_ASSERT_EQUAL_UINT8(2, bme->osT);    // code 2
    TEST_ASSERT_EQUAL_UINT8(16, bme->osP);   // code 5
    TEST_ASSERT_EQUAL_UINT8(1, bme->osH);    // code 1
    TEST_ASSERT_EQUAL_UINT16(320, bme->heaterC);
    TEST_ASSERT_EQUAL_UINT16(197, bme->heaterMs);
    runFor(30000);
    TEST_ASSERT_EQUAL_INT_MESSAGE(1, bme->settingsWrites, "unchanged settings are not written again");
}

void test_a_cycle_without_a_gas_conversion_is_not_handed_to_bsec() {
    bme->gasValid = false;
    runner->begin();
    runner->step();
    TEST_ASSERT_EQUAL_INT(0, bsec->steps);
    Bme688Data d;
    uint32_t at = 0;
    TEST_ASSERT_TRUE(runner->latest(d, at));
    TEST_ASSERT_FALSE(d.hasIaq);
}

void test_a_sensor_that_stops_answering_is_started_again() {
    runner->begin();
    runner->step();
    TEST_ASSERT_TRUE(runner->status().running);

    bme->present = false;
    const int beginsBefore = bme->begins;
    runFor(BsecRunner::kMissedLimit * 3000 + 100);
    TEST_ASSERT_FALSE(runner->status().running);
    TEST_ASSERT_TRUE(bme->begins > beginsBefore);

    bme->present = true;
    runFor(10000);
    TEST_ASSERT_TRUE(runner->status().running);
}

// ─── The state ───────────────────────────────────────────────────────────

void test_the_state_is_copied_each_minute_with_its_accuracy_and_time() {
    runner->begin();
    bsec->accuracy = 2;
    runner->step();
    BsecState s;
    TEST_ASSERT_TRUE(runner->current(s));
    TEST_ASSERT_EQUAL_UINT32(10, s.len);
    TEST_ASSERT_EQUAL_UINT8(2, s.accuracy);
    TEST_ASSERT_EQUAL_UINT32_MESSAGE(0, s.savedEpoch, "the clock is not set yet");

    fakeEpoch = 1757443200;
    runFor(BsecRunner::kCopyEveryMs + 3000);
    TEST_ASSERT_TRUE(runner->current(s));
    TEST_ASSERT_EQUAL_UINT32(1757443200, s.savedEpoch);
}

void test_the_state_is_saved_when_accuracy_reaches_3_then_every_six_hours() {
    runner->begin();
    bsec->accuracy = 1;
    runFor(3600000);
    TEST_ASSERT_EQUAL_INT(0, store->saves);

    bsec->accuracy = 3;
    runFor(10000);
    TEST_ASSERT_EQUAL_INT(1, store->saves);
    TEST_ASSERT_EQUAL_UINT8(3, store->stored.accuracy);

    runFor(BsecRunner::kSaveEveryMs - 60000);
    TEST_ASSERT_EQUAL_INT(1, store->saves);
    runFor(120000);
    TEST_ASSERT_EQUAL_INT(2, store->saves);
}

void test_a_restart_with_the_servers_copy_waits_for_the_next_step() {
    runner->begin();
    runner->step();
    bsec->calls.clear();

    runner->restartWith(stateOf({9, 9}, 3, 2000));
    TEST_ASSERT_EQUAL_STRING("", bsec->calls.c_str());
    runner->step();
    TEST_ASSERT_EQUAL_STRING("init state subscribe ", bsec->calls.c_str());
    TEST_ASSERT_EQUAL_UINT(2, bsec->stateSet.size());
    TEST_ASSERT_EQUAL_UINT8(9, bsec->stateSet[0]);
    TEST_ASSERT_TRUE(runner->status().restored);
}

// ─── What SensorSuite sees ───────────────────────────────────────────────

void test_the_suite_sees_the_newest_cycle_while_it_is_fresh() {
    BsecBme688 adapter(*runner);
    Bme688Data d;
    TEST_ASSERT_FALSE_MESSAGE(adapter.fetchData(clk->now, d), "no cycle yet");

    runner->begin();
    TEST_ASSERT_TRUE(adapter.begin(clk->now));
    runner->step();
    TEST_ASSERT_TRUE(adapter.startForced(clk->now));
    TEST_ASSERT_EQUAL_UINT32(0, adapter.measurementMs());
    TEST_ASSERT_TRUE(adapter.fetchData(clk->now, d));
    TEST_ASSERT_TRUE(d.hasIaq);
    TEST_ASSERT_FALSE_MESSAGE(adapter.fetchData(clk->now + 3 * 3000 + 1, d),
                              "a reading BSEC has not renewed is not a reading");
}

// ─── The sample rate ─────────────────────────────────────────────────────

void test_bsec_starts_at_the_rate_set_before_begin() {
    runner->setSampleS(IBsec::kUlpSampleS);
    runner->begin();
    TEST_ASSERT_EQUAL_UINT16(300, bsec->initRate);
    TEST_ASSERT_EQUAL_UINT16(300, bsec->subscribeRate);
    TEST_ASSERT_EQUAL_UINT16(300, runner->status().sampleS);
}

void test_a_stored_state_from_the_other_rate_is_not_used() {
    store->has = true;
    store->stored = stateOf({1, 2, 3}, 3, 1000, IBsec::kLpSampleS);
    runner->setSampleS(IBsec::kUlpSampleS);
    runner->begin();
    TEST_ASSERT_EQUAL_STRING("init subscribe ", bsec->calls.c_str());
    TEST_ASSERT_FALSE(runner->status().restored);
}

void test_a_new_rate_starts_bsec_again_from_nothing_at_the_next_step() {
    store->has = true;
    store->stored = stateOf({1, 2, 3}, 3, 1000);
    runner->begin();
    runner->step();
    bsec->calls.clear();

    runner->setSampleS(IBsec::kUlpSampleS);
    TEST_ASSERT_EQUAL_STRING("", bsec->calls.c_str());
    runner->step();
    TEST_ASSERT_EQUAL_STRING("init subscribe ", bsec->calls.c_str());
    TEST_ASSERT_EQUAL_UINT16(300, bsec->initRate);
    TEST_ASSERT_FALSE(runner->status().restored);
    BsecState copy;
    TEST_ASSERT_TRUE(runner->current(copy));
    TEST_ASSERT_EQUAL_UINT16_MESSAGE(300, copy.sampleS, "no copy from the old rate survives");
}

void test_the_same_rate_again_or_an_unknown_one_changes_nothing() {
    runner->begin();
    runner->step();
    bsec->calls.clear();
    runner->setSampleS(IBsec::kLpSampleS);
    runner->setSampleS(60);
    runner->step();
    TEST_ASSERT_EQUAL_STRING("", bsec->calls.c_str());
    TEST_ASSERT_EQUAL_UINT16(3, runner->sampleS());
}

void test_a_copy_from_the_other_rate_is_refused() {
    runner->begin();
    TEST_ASSERT_FALSE(runner->restartWith(stateOf({9, 9}, 3, 2000, IBsec::kUlpSampleS)));
    bsec->calls.clear();
    runner->step();
    TEST_ASSERT_EQUAL_STRING("", bsec->calls.c_str());
}

void test_at_300_s_a_cycle_stays_fresh_for_three_cycles() {
    BsecBme688 adapter(*runner);
    Bme688Data d;
    runner->setSampleS(IBsec::kUlpSampleS);
    runner->begin();
    runner->step();
    TEST_ASSERT_TRUE(adapter.fetchData(clk->now + 899000, d));
    TEST_ASSERT_FALSE(adapter.fetchData(clk->now + 900001, d));
}

void test_at_300_s_bsec_is_asked_again_after_300_s() {
    runner->setSampleS(IBsec::kUlpSampleS);
    runner->begin();
    runFor(295000);                        // the task wakes at most 3 s apart
    TEST_ASSERT_EQUAL_INT(1, bsec->controls);
    runFor(8000);
    TEST_ASSERT_EQUAL_INT(2, bsec->controls);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_begin_restores_the_stored_state_between_init_and_subscribe);
    RUN_TEST(test_begin_without_a_stored_state_starts_from_nothing);
    RUN_TEST(test_a_state_bsec_refuses_means_starting_from_nothing);
    RUN_TEST(test_bsec_that_will_not_start_is_tried_again);
    RUN_TEST(test_bsec_starts_while_the_sensor_is_missing);
    RUN_TEST(test_a_step_runs_the_cycle_bsec_asks_for_and_keeps_the_index);
    RUN_TEST(test_bsec_is_not_asked_before_the_time_it_gave);
    RUN_TEST(test_a_late_call_is_counted_and_the_cycle_still_runs);
    RUN_TEST(test_bsec_settings_reach_the_sensor_as_multipliers_once);
    RUN_TEST(test_a_cycle_without_a_gas_conversion_is_not_handed_to_bsec);
    RUN_TEST(test_a_sensor_that_stops_answering_is_started_again);
    RUN_TEST(test_the_state_is_copied_each_minute_with_its_accuracy_and_time);
    RUN_TEST(test_the_state_is_saved_when_accuracy_reaches_3_then_every_six_hours);
    RUN_TEST(test_a_restart_with_the_servers_copy_waits_for_the_next_step);
    RUN_TEST(test_the_suite_sees_the_newest_cycle_while_it_is_fresh);
    RUN_TEST(test_bsec_starts_at_the_rate_set_before_begin);
    RUN_TEST(test_a_stored_state_from_the_other_rate_is_not_used);
    RUN_TEST(test_a_new_rate_starts_bsec_again_from_nothing_at_the_next_step);
    RUN_TEST(test_the_same_rate_again_or_an_unknown_one_changes_nothing);
    RUN_TEST(test_a_copy_from_the_other_rate_is_refused);
    RUN_TEST(test_at_300_s_a_cycle_stays_fresh_for_three_cycles);
    RUN_TEST(test_at_300_s_bsec_is_asked_again_after_300_s);
    return UNITY_END();
}
