#pragma once
#include <cstdint>

#include "IClock.h"
#include "II2cBus.h"
#include "IScd41.h"

// Sensirion SCD41 on I2C.
//
// The part refuses every command but read, data-ready, stop and pressure
// while periodic measurement runs, and refuses everything for 500 ms after a
// stop. The driver tracks which mode it put the part in so a refusal comes
// back as false rather than as a NACK the caller has to interpret.
class Scd41Driver : public IScd41 {
public:
    Scd41Driver(II2cBus& bus, IClock& clock, uint8_t addr = kAddress)
        : bus_(bus), clock_(clock), addr_(addr) {}

    bool begin(uint32_t nowMs) override;
    bool startPeriodicMeasurement(uint32_t nowMs) override;
    bool startLowPowerPeriodicMeasurement(uint32_t nowMs) override;
    bool stopPeriodicMeasurement(uint32_t nowMs) override;
    bool measureSingleShot(uint32_t nowMs) override;
    bool getDataReadyStatus(uint32_t nowMs, bool& ready) override;
    bool readMeasurement(uint32_t nowMs, Scd41Data& out) override;
    bool setAmbientPressure(uint32_t pa) override;
    bool setTemperatureOffset(float degC) override;
    bool powerDown() override;
    bool wakeUp(uint32_t nowMs) override;
    bool getSerialNumber(uint64_t& serial) override;
    bool getAutomaticSelfCalibration(bool& on) override;
    bool getTemperatureOffset(float& degC) override;
    uint32_t crcFailures() const override { return crcFailures_; }

    enum Mode { IDLE, PERIODIC, LOW_POWER_PERIODIC, SINGLE_SHOT, POWERED_DOWN };
    Mode mode() const { return mode_; }

    static const uint8_t kAddress = 0x62;

    static const uint16_t kCmdStartPeriodic         = 0x21B1;
    static const uint16_t kCmdStartLowPowerPeriodic = 0x21AC;
    static const uint16_t kCmdStopPeriodic          = 0x3F86;
    static const uint16_t kCmdMeasureSingleShot     = 0x219D;
    static const uint16_t kCmdGetDataReady          = 0xE4B8;
    static const uint16_t kCmdReadMeasurement       = 0xEC05;
    static const uint16_t kCmdSetTemperatureOffset  = 0x241D;
    static const uint16_t kCmdSetAmbientPressure    = 0xE000;
    static const uint16_t kCmdPowerDown             = 0x36E0;
    static const uint16_t kCmdWakeUp                = 0x36F6;
    static const uint16_t kCmdGetSerialNumber       = 0x3682;
    static const uint16_t kCmdGetAsc                = 0x2313;
    static const uint16_t kCmdGetTemperatureOffset  = 0x2318;

    // The data-ready word is "not ready" only when its low eleven bits are
    // all zero; the top five are reserved and carry whatever they carry.
    static const uint16_t kDataReadyMask = 0x07FF;

    static const uint32_t kStopBusyMs   = 500;
    static const uint32_t kSingleShotMs = 5000;
    static const uint32_t kWakeMs       = 30;
    // Every command that answers with data needs 1 ms before the read.
    static const uint32_t kCommandMs = 1;

    static const uint32_t kMinPressurePa = 70000;
    static const uint32_t kMaxPressurePa = 120000;
    // The offset word is degrees C x 65535/175, so 175 C is the ceiling.
    static constexpr float kMaxOffsetC = 175.0f;

private:
    bool busy(uint32_t nowMs) const { return nowMs < busyUntilMs_; }
    bool readAnswer(uint16_t* words, size_t count);

    II2cBus& bus_;
    IClock&  clock_;
    uint8_t  addr_;
    Mode     mode_ = POWERED_DOWN;
    uint32_t busyUntilMs_ = 0;
    uint32_t crcFailures_ = 0;
};
