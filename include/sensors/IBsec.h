#pragma once
#include <cstdint>

#include "sensors/Readings.h"

// What BSEC asks of the sensor next, from bsec_sensor_control().
struct BsecRequest {
    int64_t  nextCallNs;     // when BSEC wants to be asked again
    bool     measure;        // run a forced cycle now, with the settings below
    uint16_t heaterC;
    uint16_t heaterMs;
    uint8_t  osT, osP, osH;  // BME68x oversampling codes: 0 skips, 1 is 1x, 5 is 16x
    bool     runGas;
};

// What BSEC made of one cycle, from bsec_do_steps().
struct BsecResult {
    bool    hasIaq;
    float   iaq;          // 0-500
    uint8_t iaqAccuracy;  // 0-3
};

// Bosch's BSEC library, as the calls BsecRunner makes, so the host tests can
// stand in for the closed-source binary. Each returns BSEC's status: zero is
// success, a negative number an error, a positive one a warning.
class IBsec {
public:
    virtual ~IBsec() {}
    // Reset BSEC and load the configuration blob.
    virtual int init() = 0;
    virtual int setState(const uint8_t* state, uint32_t len) = 0;
    virtual int getState(uint8_t* state, uint32_t max, uint32_t* len) = 0;
    // Ask for the outputs, at the LP rate. Bosch's order is init, then any
    // state, then this.
    virtual int subscribe() = 0;
    virtual int sensorControl(int64_t nowNs, BsecRequest& request) = 0;
    // One forced cycle, with the inputs the last request asked for.
    virtual int doSteps(int64_t nowNs, const Bme688Data& data, BsecResult& result) = 0;

    static const int      kOk = 0;
    static const int      kLateCall = 100;    // BSEC_W_SC_CALL_TIMING_VIOLATION
    static const uint32_t kMaxState = 238;    // BSEC_MAX_STATE_BLOB_SIZE
};
