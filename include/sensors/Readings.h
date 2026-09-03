#pragma once
#include <cstddef>
#include <cstdint>

// What each sensor hands back, and the set the firmware posts.
// Units and key names follow docs/READINGS.md.

struct Shtc3Data {
    float tempC;
    float rhPct;
};

struct Scd41Data {
    uint16_t co2Ppm;
    float    tempC;   // runs ~4 C warm until the offset is tuned
    float    rhPct;
};

struct PmData {
    uint16_t pm1_0Cf1, pm2_5Cf1, pm10Cf1;     // "CF=1, standard particle"
    uint16_t pm1_0, pm2_5, pm10;              // "atmospheric environment" — the ones we use
    uint16_t pc0_3, pc0_5, pc1_0, pc2_5, pc5_0, pc10;   // particles per 0.1 L
    uint8_t  version;
    uint8_t  error;
};

struct Bme688Data {
    float    tempC;        // runs warm; BSEC-internal
    float    pressureHpa;
    float    rhPct;
    float    gasOhm;
    bool     gasValid;     // a real gas conversion took place
    bool     heatStable;   // the heater reached its target; gasOhm is trustworthy only if true
    float    iaq;          // 0–500; only meaningful with BSEC
    uint8_t  iaqAccuracy;  // 0–3
};

struct Readings {
    uint32_t   ts;
    Shtc3Data  shtc3;   bool shtc3Valid;
    Scd41Data  scd41;   bool scd41Valid;
    PmData     pm;      bool pmValid;
    Bme688Data bme688;  bool bme688Valid;
};

// Encode to the JSON in docs/READINGS.md. Returns the length written, or 0
// if the buffer is too small (nothing partial is left behind).
size_t readingsToJson(const Readings& r, const char* device, char* buf, size_t len);
