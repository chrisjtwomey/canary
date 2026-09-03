#include "sensors/mock/EnvModel.h"
#include <cmath>

namespace {
const float kPi = 3.14159265f;
const float kCo2Outdoor = 420.0f;
const float kCo2PerPersonPerS = 4.0f / 60.0f;      // ~4 ppm/min per person in a ~40 m3 room
const float kAbsHumOutdoor = 7.5f;                 // g/m3
const float kAbsHumPerPersonPerS = 0.0003f;        // breathing
const float kTempTauS = 2400.0f;                   // 40 min to settle on the heating target
const float kPmBaseline = 4.0f;
const float kPmTauS = 2700.0f;                     // 45 min settling of a cooking spike
const float kVocBaseline = 0.12f;
const float kVocTauS = 3600.0f;
const float kVocPerPersonPerS = 0.00002f;

bool between(float h, float from, float to) { return h >= from && h < to; }
}

EnvModel::EnvModel(uint32_t seed) : rng_(seed ? seed : 0x9E3779B9u) {}

uint32_t EnvModel::rnd() {
    // xorshift32
    uint32_t x = rng_;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    rng_ = x;
    return x;
}

float EnvModel::uniform() { return (rnd() >> 8) * (1.0f / 16777216.0f); }

float EnvModel::noise(float sigma) {
    // Sum of three uniforms has variance 0.25; scale to sigma.
    float s = uniform() + uniform() + uniform() - 1.5f;
    return s * 2.0f * sigma;
}

float EnvModel::rhFromAbs(float absHum, float tempC) {
    float es = 6.112f * expf(17.62f * tempC / (243.12f + tempC));        // hPa, Magnus
    float rh = 100.0f * absHum * (tempC + 273.15f) / (216.7f * es);
    return rh < 0 ? 0 : (rh > 100 ? 100 : rh);
}

float EnvModel::absFromRh(float rhPct, float tempC) {
    float es = 6.112f * expf(17.62f * tempC / (243.12f + tempC));
    return 216.7f * (rhPct / 100.0f * es) / (tempC + 273.15f);
}

float EnvModel::hourOfDay() const { return (epoch_ % 86400u) / 3600.0f; }

int EnvModel::occupancyAt(float h) {
    if (between(h, 7.0f, 8.5f))  return 1;
    if (between(h, 17.5f, 23.0f)) return 2;
    if (between(h, 23.0f, 24.0f)) return 1;
    return 0;
}

float EnvModel::heatingTargetAt(float h) {
    if (between(h, 6.5f, 8.5f))  return 21.0f;
    if (between(h, 17.0f, 23.0f)) return 21.5f;
    return 18.5f;
}

float EnvModel::ventilationTauAt(float h) {
    if (between(h, 8.0f, 8.5f) || between(h, 21.0f, 21.25f)) return 900.0f;   // a window open
    return 7200.0f;                                                            // closed up
}

float EnvModel::pmSourceAt(float h) {
    if (between(h, 18.0f, 18.4f)) return 0.08f;     // cooking
    if (between(h, 7.5f, 7.65f))  return 0.03f;     // toast
    return 0.0f;
}

float EnvModel::vocSourceAt(float h) {
    if (between(h, 18.0f, 18.5f)) return 0.0004f;   // cooking
    if (between(h, 10.0f, 10.33f)) return 0.0004f;  // cleaning
    return 0.0f;
}

float EnvModel::pressureHpa() const {
    float t = (float)(epoch_ % (3u * 86400u));
    return 1013.0f + 8.0f * sinf(2.0f * kPi * t / (3.0f * 86400.0f));
}

float EnvModel::gasOhm() const {
    float rh = rhPct();
    float humidityPull = (rh - 40.0f) / 50.0f;
    if (humidityPull < -0.5f) humidityPull = -0.5f;
    if (humidityPull > 1.0f) humidityPull = 1.0f;
    return 200000.0f * expf(-2.4f * voc_) * (1.0f - 0.5f * humidityPull);
}

void EnvModel::reset(uint32_t epochS) {
    epoch_ = epochS;
    float h = hourOfDay();
    occupancy_ = occupancyAt(h);
    temp_ = heatingTargetAt(h);
    absHum_ = kAbsHumOutdoor + 0.8f * occupancy_;
    co2_ = kCo2Outdoor + 80.0f + 150.0f * occupancy_;
    pm25_ = kPmBaseline;
    voc_ = kVocBaseline + 0.05f * occupancy_;
}

void EnvModel::advanceTo(uint32_t epochS) {
    if (epochS <= epoch_) { epoch_ = epochS; return; }
    while (epoch_ < epochS) {
        uint32_t dt = epochS - epoch_;
        if (dt > 60) dt = 60;
        step((float)dt);
        epoch_ += dt;
    }
}

void EnvModel::step(float dt) {
    float h = hourOfDay();
    occupancy_ = occupancyAt(h);
    float ventTau = ventilationTauAt(h);

    co2_ += dt * (kCo2PerPersonPerS * occupancy_ - (co2_ - kCo2Outdoor) / ventTau);
    absHum_ += dt * (kAbsHumPerPersonPerS * occupancy_ - (absHum_ - kAbsHumOutdoor) / ventTau);

    float target = heatingTargetAt(h) + 0.3f * occupancy_;
    temp_ += dt * (target - temp_) / kTempTauS;

    pm25_ += dt * (pmSourceAt(h) - (pm25_ - kPmBaseline) / kPmTauS);
    voc_ += dt * (vocSourceAt(h) + kVocPerPersonPerS * occupancy_ - (voc_ - kVocBaseline) / kVocTauS);
    if (voc_ > 1.0f) voc_ = 1.0f;
    if (pm25_ < 0.0f) pm25_ = 0.0f;
}
