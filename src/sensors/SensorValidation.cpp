#include "sensors/SensorValidation.h"

#include <cstdarg>
#include <cstdio>

namespace {

// The Adafruit board's frame, read straight from the address.
const size_t kPmFrameBytes = 32;

bool outside(float v, float lo, float hi) { return v < lo || v > hi; }

}  // namespace

const char* SensorValidation::outcomeName(Outcome o) {
    switch (o) {
        case PASS: return "pass";
        case WARN: return "warn";
        case FAIL: return "fail";
        default:   return "skipped";
    }
}

// ---------------------------------------------------------------------------
// Ranges (docs/HARDWARE.md 2-5)
// ---------------------------------------------------------------------------

SensorValidation::Outcome SensorValidation::check(const Shtc3Data& d) {
    if (outside(d.tempC, -40.0f, 125.0f) || outside(d.rhPct, 0.0f, 100.0f)) return FAIL;
    if (outside(d.tempC, 5.0f, 60.0f) || outside(d.rhPct, 20.0f, 80.0f)) return WARN;
    return PASS;
}

SensorValidation::Outcome SensorValidation::check(const Scd41Data& d) {
    // Zero parts per million is the reading of a sensor that has not measured,
    // not the reading of clean air.
    if (d.co2Ppm == 0 || d.co2Ppm > 40000) return FAIL;
    if (outside(d.tempC, -10.0f, 60.0f) || outside(d.rhPct, 0.0f, 100.0f)) return FAIL;
    if (d.co2Ppm < 400 || d.co2Ppm > 5000) return WARN;
    return PASS;
}

SensorValidation::Outcome SensorValidation::check(const Bme688Data& d) {
    if (outside(d.pressureHpa, 300.0f, 1100.0f)) return FAIL;
    if (!d.gasValid || d.gasOhm <= 0.0f) return FAIL;
    if (!d.heatStable) return WARN;
    return PASS;
}

SensorValidation::Outcome SensorValidation::check(const PmData& d) {
    if (d.error != 0) return FAIL;
    // Every count is of particles at or below its size, so the series can
    // only rise. A fall means a mis-parsed frame, not dirty air.
    if (d.pm1_0 > d.pm2_5 || d.pm2_5 > d.pm10) return FAIL;
    if (d.pm10 > 1000) return FAIL;
    if (d.pm10 > 500) return WARN;
    return PASS;
}

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

void SensorValidation::say(int level, const char* fmt, ...) {
    if (!logLine_) return;
    char line[120];
    va_list args;
    va_start(args, fmt);
    vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    logLine_(level, line);
}

// The millisecond stamp is what lines a PPK2 capture up with the phase it was
// taken in. See docs/BATTERY.md 10.
void SensorValidation::mark(const char* phase) {
    say(kLogNotice, "[validate] %7u ms  %s", clock_.millis(), phase);
}

SensorValidation::Outcome SensorValidation::record(Report& r, Outcome o) {
    if (o == WARN) ++r.warnings;
    if (o == FAIL) ++r.failures;
    return o;
}

// ---------------------------------------------------------------------------
// Phases
// ---------------------------------------------------------------------------

void SensorValidation::probe(Report& r) {
    mark("phase 1: probing the bus");
    suite_.begin();

    r.shtc3.present  = suite_.shtc3Present();
    r.scd41.present  = suite_.scd41Present();
    r.pm.present     = suite_.pmPresent();
    r.bme688.present = suite_.bme688Present();

    const bool present[4] = {r.shtc3.present, r.scd41.present, r.pm.present, r.bme688.present};
    const char* names[4] = {"shtc3", "scd41", "pm", "bme688"};
    SensorReport* reports[4] = {&r.shtc3, &r.scd41, &r.pm, &r.bme688};

    for (int i = 0; i < 4; ++i) {
        say(present[i] ? kLogNotice : kLogError, "[validate] %s %s", names[i],
            present[i] ? "present" : "absent");
        if (!present[i]) {
            reports[i]->normal = record(r, FAIL);
            reports[i]->lowPower = SKIPPED;
        }
    }
}

bool SensorValidation::pmAnswers() {
    uint8_t frame[kPmFrameBytes];
    return bus_.read(pmAddress_, frame, kPmFrameBytes);
}

// SET low first, so the fan's one warm-up covers both the checks that follow
// and the reading set at the end.
void SensorValidation::checkPmSetLine(Report& r) {
    mark("phase 2: PM fan stopped, checking the module sleeps");
    r.setLineWired = pm_.setLineWired();

    if (!r.setLineWired) {
        r.pm.lowPower = SKIPPED;
        say(kLogWarning, "[validate] pm SET line not wired; sleep check skipped");
        record(r, WARN);
        return;
    }

    pm_.setEnabled(false, clock_.millis());
    clock_.waitMs(kPmSetSettleMs);

    if (pmAnswers()) {
        r.pmAnsweredWithSetLow = true;
        r.pm.lowPower = record(r, WARN);
        say(kLogWarning, "[validate] PM still answers with SET low; SET wire not connected");
    } else {
        r.pm.lowPower = PASS;
        say(kLogNotice, "[validate] pm SET low: module silent, pass");
    }

    pm_.setEnabled(true, clock_.millis());
}

void SensorValidation::checkShtc3(Report& r) {
    Shtc3Data data = {};

    bool ok = shtc3_.wakeup(clock_.millis()) && shtc3_.measure(clock_.millis(), false);
    if (ok) {
        clock_.waitMs(SensorSuite::kShtc3MeasureMs);
        ok = shtc3_.read(clock_.millis(), data);
    }
    r.shtc3.normal = record(r, ok ? check(data) : FAIL);
    say(kLogNotice, "[validate] shtc3 normal %.1f C %.1f %%RH %s", data.tempC, data.rhPct,
        outcomeName(r.shtc3.normal));

    // The sleep command is the low-power state: a part that NACKs it is still
    // running, whatever it reads afterwards.
    if (!shtc3_.sleep()) {
        r.shtc3.lowPower = record(r, FAIL);
        say(kLogError, "[validate] shtc3 refused the sleep command");
        return;
    }

    Shtc3Data lowPower = {};
    ok = shtc3_.wakeup(clock_.millis()) && shtc3_.measure(clock_.millis(), true);
    if (ok) {
        clock_.waitMs(kShtc3LowPowerMs);
        ok = shtc3_.read(clock_.millis(), lowPower);
    }
    r.shtc3.lowPower = record(r, ok ? check(lowPower) : FAIL);
    say(kLogNotice, "[validate] shtc3 low power %.1f C %.1f %%RH %s", lowPower.tempC,
        lowPower.rhPct, outcomeName(r.shtc3.lowPower));

    shtc3_.sleep();
}

bool SensorValidation::waitForScd41Data() {
    uint32_t waited = 0;
    while (waited <= kScd41ReadyTimeoutMs) {
        bool ready = false;
        if (scd41_.getDataReadyStatus(clock_.millis(), ready) && ready) return true;
        clock_.waitMs(kScd41ReadyPollMs);
        waited += kScd41ReadyPollMs;
    }
    return false;
}

void SensorValidation::checkScd41(Report& r) {
    Scd41Data data = {};
    bool ok = waitForScd41Data() && scd41_.readMeasurement(clock_.millis(), data);
    r.scd41.normal = record(r, ok ? check(data) : FAIL);
    say(kLogNotice, "[validate] scd41 normal %u ppm %s", (unsigned)data.co2Ppm,
        outcomeName(r.scd41.normal));

    // Idle, never power_down: powering the part down loses the automatic
    // self-calibration history. docs/BATTERY.md 4.
    if (!scd41_.stopPeriodicMeasurement(clock_.millis())) {
        r.scd41.lowPower = record(r, FAIL);
        say(kLogError, "[validate] scd41 would not stop measuring");
        return;
    }
    clock_.waitMs(kScd41StopBusyMs);

    Scd41Data lowPower = {};
    ok = scd41_.measureSingleShot(clock_.millis());
    if (ok) {
        clock_.waitMs(kScd41SingleShotMs);
        ok = waitForScd41Data() && scd41_.readMeasurement(clock_.millis(), lowPower);
    }
    r.scd41.lowPower = record(r, ok ? check(lowPower) : FAIL);
    say(kLogNotice, "[validate] scd41 low power (idle + single shot) %u ppm %s",
        (unsigned)lowPower.co2Ppm, outcomeName(r.scd41.lowPower));
}

void SensorValidation::checkBme688(Report& r) {
    Bme688Data data = {};
    bool ok = bme_.startForced(clock_.millis());
    if (ok) {
        clock_.waitMs(bme_.measurementMs());
        ok = bme_.fetchData(clock_.millis(), data);
    }
    r.bme688.normal = record(r, ok ? check(data) : FAIL);
    say(kLogNotice, "[validate] bme688 normal %.1f hPa gas %.0f ohm %s", data.pressureHpa,
        data.gasOhm, outcomeName(r.bme688.normal));

    // Forced mode returns the part to sleep on its own, so the low-power
    // check is that a cycle started after an idle gap still reads.
    clock_.waitMs(kBmeIdleGapMs);

    Bme688Data lowPower = {};
    ok = bme_.startForced(clock_.millis());
    if (ok) {
        clock_.waitMs(bme_.measurementMs());
        ok = bme_.fetchData(clock_.millis(), lowPower);
    }
    r.bme688.lowPower = record(r, ok ? check(lowPower) : FAIL);
    say(kLogNotice, "[validate] bme688 low power (sleep + forced) %.1f hPa %s",
        lowPower.pressureHpa, outcomeName(r.bme688.lowPower));
}

void SensorValidation::checkPmRunning(Report& r) {
    uint32_t waitedMs = 0;
    while (!pm_.stable(clock_.millis()) && waitedMs < kPmStableTimeoutMs) {
        clock_.waitMs(kPmStablePollMs);
        waitedMs += kPmStablePollMs;
    }
    if (waitedMs) say(kLogNotice, "[validate] pm fan warm-up finished after %u ms", waitedMs);

    uint8_t frame[kPmFrameBytes];
    PmData data = {};
    bool ok = false;
    for (int attempt = 0; attempt < SensorSuite::kPmReadAttempts && !ok; ++attempt) {
        ok = pm_.readFrame(clock_.millis(), frame) && IPmsa003i::parseFrame(frame, data);
    }
    r.pm.normal = record(r, ok ? check(data) : FAIL);
    say(kLogNotice, "[validate] pm normal %u/%u/%u ug/m3 %s", (unsigned)data.pm1_0,
        (unsigned)data.pm2_5, (unsigned)data.pm10, outcomeName(r.pm.normal));
}

void SensorValidation::gather(Report& r, uint32_t epoch) {
    mark("phase 5: one reading set from every sensor");
    // A part that never answered has no conversion coming, so waiting for one
    // spends the timeout for nothing.
    if (r.scd41.present) waitForScd41Data();
    r.gathered = suite_.sample(epoch);

    const bool valid[4] = {r.gathered.shtc3Valid, r.gathered.scd41Valid, r.gathered.pmValid,
                           r.gathered.bme688Valid};
    const bool present[4] = {r.shtc3.present, r.scd41.present, r.pm.present, r.bme688.present};
    const char* names[4] = {"shtc3", "scd41", "pm", "bme688"};

    for (int i = 0; i < 4; ++i) {
        if (present[i] && !valid[i]) {
            record(r, FAIL);
            say(kLogError, "[validate] %s gave no reading in the set", names[i]);
        }
    }
}

void SensorValidation::allToLowPower(const Report& r) {
    mark("phase 6: all sensors low power");
    if (r.shtc3.present) shtc3_.sleep();
    if (r.scd41.present) {
        scd41_.stopPeriodicMeasurement(clock_.millis());
        clock_.waitMs(kScd41StopBusyMs);
    }
    if (r.pm.present) pm_.setEnabled(false, clock_.millis());
    // The BME688 is already asleep: forced mode leaves it there.
}

// ---------------------------------------------------------------------------

SensorValidation::Report SensorValidation::run(uint32_t epoch) {
    Report r = {};
    uint32_t startMs = clock_.millis();

    probe(r);
    if (r.pm.present) checkPmSetLine(r);

    mark("phase 3: each sensor running, then in low power");
    if (r.shtc3.present) checkShtc3(r);
    if (r.scd41.present) checkScd41(r);
    if (r.bme688.present) checkBme688(r);
    if (r.pm.present) checkPmRunning(r);

    mark("phase 4: all sensors back in normal running mode");
    if (r.scd41.present) scd41_.startPeriodicMeasurement(clock_.millis());

    gather(r, epoch);
    allToLowPower(r);

    r.elapsedMs = clock_.millis() - startMs;
    say(r.failures ? kLogError : kLogNotice,
        "[validate] summary: %u failures, %u warnings in %u ms", (unsigned)r.failures,
        (unsigned)r.warnings, r.elapsedMs);
    return r;
}
