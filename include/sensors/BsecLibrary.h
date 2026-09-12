#pragma once
#if !defined(NATIVE)
#include "sensors/IBsec.h"

// IBsec over Bosch's precompiled BSEC2: one instance, in LP mode, a sample
// every 3 s. scripts/bsec.py says how the binary is linked.
class BsecLibrary : public IBsec {
public:
    int init() override;
    int setState(const uint8_t* state, uint32_t len) override;
    int getState(uint8_t* state, uint32_t max, uint32_t* len) override;
    int subscribe() override;
    int sensorControl(int64_t nowNs, BsecRequest& request) override;
    int doSteps(int64_t nowNs, const Bme688Data& data, BsecResult& result) override;

private:
    uint32_t processData_ = 0;   // the inputs the last request asked for
};
#endif
