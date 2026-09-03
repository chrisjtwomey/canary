#include "sensors/SensorSuite.h"

bool SensorSuite::begin() {
    shtc3Ok_ = shtc3_.begin(clock_.millis());

    scd41Ok_ = scd41_.begin(clock_.millis());
    if (scd41Ok_) {
        clock_.waitMs(kScd41WakeMs);
        scd41Ok_ = scd41_.startPeriodicMeasurement(clock_.millis());
    }

    pmOk_ = pm_.begin(clock_.millis());

    bmeOk_ = bme_.begin(clock_.millis());
    if (bmeOk_) {
        bme_.setOversampling(kBmeOsT, kBmeOsP, kBmeOsH);
        bme_.setHeaterProfile(kBmeHeaterC, kBmeHeaterMs);
    }

    return shtc3Ok_ && scd41Ok_ && pmOk_ && bmeOk_;
}

void SensorSuite::setFanEnabled(bool on) {
    if (pmOk_) pm_.setEnabled(on, clock_.millis());
}

Readings SensorSuite::sample(uint32_t epoch) {
    Readings r = {};
    r.ts = epoch;
    sampleShtc3(r);
    sampleBme688(r);
    sampleScd41(r);
    samplePm(r);
    return r;
}

void SensorSuite::sampleShtc3(Readings& r) {
    if (!shtc3Ok_) return;
    if (!shtc3_.wakeup(clock_.millis())) return;
    if (shtc3_.measure(clock_.millis(), false)) {
        clock_.waitMs(kShtc3MeasureMs);
        r.shtc3Valid = shtc3_.read(clock_.millis(), r.shtc3);
    }
    shtc3_.sleep();
}

void SensorSuite::sampleBme688(Readings& r) {
    if (!bmeOk_) return;
    if (!bme_.startForced(clock_.millis())) return;
    clock_.waitMs(bme_.measurementMs());
    r.bme688Valid = bme_.fetchData(clock_.millis(), r.bme688);
}

void SensorSuite::sampleScd41(Readings& r) {
    if (!scd41Ok_) return;
    // NDIR absorption scales with gas density, so the SCD41 needs the real
    // ambient pressure to convert correctly. The BME688 has just measured it.
    if (r.bme688Valid) {
        scd41_.setAmbientPressure((uint32_t)(r.bme688.pressureHpa * 100.0f));
    }
    bool ready = false;
    if (!scd41_.getDataReadyStatus(clock_.millis(), ready) || !ready) return;
    r.scd41Valid = scd41_.readMeasurement(clock_.millis(), r.scd41);
}

void SensorSuite::samplePm(Readings& r) {
    // Before the fan has run for 30 s the counts are still ramping up, so a
    // frame read now would be believable and wrong.
    if (!pmOk_ || !pm_.stable(clock_.millis())) return;
    uint8_t frame[32];
    for (int attempt = 0; attempt < kPmReadAttempts && !r.pmValid; ++attempt) {
        if (pm_.readFrame(clock_.millis(), frame)) {
            r.pmValid = IPmsa003i::parseFrame(frame, r.pm);
        }
    }
}
