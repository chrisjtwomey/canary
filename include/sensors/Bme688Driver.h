#pragma once
#include <cstdint>

#include "IBme688.h"
#include "IClock.h"
#include "II2cBus.h"
#include "bme68x.h"

// Bosch BME688 in forced mode, driven through Bosch's own BME68x API. The
// compensation for temperature, pressure, humidity and gas resistance reads
// twenty calibration coefficients out of the part; that arithmetic is the
// vendor's, and this class is the bus and the lifecycle around it.
//
// IAQ needs BSEC, which is not integrated, so `iaq` and `iaqAccuracy` come
// back as zero. docs/READINGS.md says those keys are absent until then.
class Bme688Driver : public IBme688 {
public:
    Bme688Driver(II2cBus& bus, IClock& clock, uint8_t addr = kAddress)
        : bus_(bus), clock_(clock), addr_(addr) {}

    bool begin(uint32_t nowMs) override;
    void setOversampling(uint8_t osT, uint8_t osP, uint8_t osH) override;
    void setHeaterProfile(uint16_t degC, uint16_t ms) override;
    bool startForced(uint32_t nowMs) override;
    uint32_t measurementMs() const override { return measurementMs_; }
    bool fetchData(uint32_t nowMs, Bme688Data& out) override;
    uint8_t chipId() override { return dev_.chip_id; }

    static const uint8_t kAddress = 0x76;   // SDO low; the Soldered board's JP1 selects 0x77
    static const uint8_t kChipId  = 0x61;

    // What the heater resistance is calculated against. Bosch's examples use
    // a fixed 25 C; the error it costs is small beside the 300 C target.
    static const int8_t kAmbientC = 25;

private:
    static int8_t busRead(uint8_t reg, uint8_t* data, uint32_t len, void* intfPtr);
    static int8_t busWrite(uint8_t reg, const uint8_t* data, uint32_t len, void* intfPtr);
    static void   busDelayUs(uint32_t us, void* intfPtr);
    static uint8_t oversamplingCode(uint8_t multiplier);

    bool applyConfig();

    II2cBus& bus_;
    IClock&  clock_;
    uint8_t  addr_;

    struct bme68x_dev  dev_ = {};
    struct bme68x_conf conf_ = {};

    uint8_t  osT_ = 2, osP_ = 16, osH_ = 1;
    uint16_t heaterC_ = 300, heaterMs_ = 100;
    uint32_t measurementMs_ = 0;
    bool     ready_ = false;
    bool     configured_ = false;
    bool     running_ = false;
    uint32_t doneAtMs_ = 0;
};
