#pragma once
#include <cstdint>

// A simulated room, deterministic for a given seed and time. It is the
// "truth" every mock sensor reads from, so the four mocks stay consistent
// with each other: the SCD41's temperature runs warm relative to the SHTC3,
// the BME688's gas resistance falls when the same humidity rises, and so on.
//
// Dynamics, all driven by the hour of day:
//   occupancy  people in the room; morning and evening
//   CO2        + per person, decays to 420 ppm with ventilation (windows open twice a day)
//   humidity   absolute humidity + per person, same decay; RH follows from temperature
//   temp       relaxes toward a heating schedule, plus a little per person
//   PM2.5      cooking and toast events, decays toward a low baseline
//   VOC        cooking, cleaning, occupancy; an index 0..1 that sets the BME688 gas resistance
//   pressure   a slow sinusoid, period three days
class EnvModel {
public:
    explicit EnvModel(uint32_t seed = 1);

    // Start the room in a plausible state for the time of day.
    void reset(uint32_t epochS);
    // Integrate forward to epochS in steps of at most 60 s.
    void advanceTo(uint32_t epochS);

    uint32_t epoch() const { return epoch_; }
    int   occupancy() const { return occupancy_; }
    float tempC() const { return temp_; }
    float absHumidity() const { return absHum_; }   // g/m3
    float rhPct() const { return rhFromAbs(absHum_, temp_); }
    float pressureHpa() const;
    float co2Ppm() const { return co2_; }
    float pm25() const { return pm25_; }
    float pm1() const { return pm25_ * 0.62f; }
    float pm10() const { return pm25_ * 1.35f; }
    float vocIndex() const { return voc_; }          // 0 clean .. 1 heavy
    float gasOhm() const;                            // what a BME688 plate sees

    // Deterministic pseudo-Gaussian noise, sigma in the caller's units.
    float noise(float sigma);
    // Deterministic uniform in [0, 1).
    float uniform();

    static float rhFromAbs(float absHum, float tempC);
    static float absFromRh(float rhPct, float tempC);

private:
    void step(float dtS);
    float hourOfDay() const;
    static int   occupancyAt(float hour);
    static float heatingTargetAt(float hour);
    static float ventilationTauAt(float hour);
    static float pmSourceAt(float hour);
    static float vocSourceAt(float hour);
    uint32_t rnd();

    uint32_t rng_;
    uint32_t epoch_ = 0;
    int   occupancy_ = 0;
    float temp_ = 20.0f;
    float absHum_ = 7.5f;
    float co2_ = 450.0f;
    float pm25_ = 4.0f;
    float voc_ = 0.15f;
};
