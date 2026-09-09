#include "sensors/Scd41Driver.h"

#include "sensors/SensirionI2c.h"

constexpr float Scd41Driver::kMaxOffsetC;

bool Scd41Driver::begin(uint32_t nowMs) {
    (void)nowMs;
    // A warm reset leaves the part in whatever mode the last boot chose, and
    // a measuring part refuses everything but a stop. The stop is NACKed when
    // the part was already idle, which is not a fault, so its result is not
    // checked.
    sensirion::sendCommand(bus_, addr_, kCmdStopPeriodic);
    clock_.waitMs(kStopBusyMs);
    mode_ = IDLE;
    busyUntilMs_ = clock_.millis();

    uint64_t serial = 0;
    if (getSerialNumber(serial)) return true;
    mode_ = POWERED_DOWN;
    return false;
}

bool Scd41Driver::startPeriodicMeasurement(uint32_t nowMs) {
    if (mode_ != IDLE || busy(nowMs)) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdStartPeriodic)) return false;
    mode_ = PERIODIC;
    return true;
}

bool Scd41Driver::startLowPowerPeriodicMeasurement(uint32_t nowMs) {
    if (mode_ != IDLE || busy(nowMs)) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdStartLowPowerPeriodic)) return false;
    mode_ = LOW_POWER_PERIODIC;
    return true;
}

bool Scd41Driver::stopPeriodicMeasurement(uint32_t nowMs) {
    if (mode_ == POWERED_DOWN) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdStopPeriodic)) return false;
    mode_ = IDLE;
    busyUntilMs_ = nowMs + kStopBusyMs;
    return true;
}

bool Scd41Driver::measureSingleShot(uint32_t nowMs) {
    if (mode_ != IDLE || busy(nowMs)) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdMeasureSingleShot)) return false;
    mode_ = SINGLE_SHOT;
    busyUntilMs_ = nowMs + kSingleShotMs;
    return true;
}

bool Scd41Driver::getDataReadyStatus(uint32_t nowMs, bool& ready) {
    if (mode_ == POWERED_DOWN || busy(nowMs)) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdGetDataReady)) return false;
    uint16_t status = 0;
    if (!readAnswer(&status, 1)) return false;
    ready = (status & kDataReadyMask) != 0;
    if (ready && mode_ == SINGLE_SHOT) mode_ = IDLE;
    return true;
}

bool Scd41Driver::readMeasurement(uint32_t nowMs, Scd41Data& out) {
    if (mode_ == POWERED_DOWN || busy(nowMs)) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdReadMeasurement)) return false;
    uint16_t words[3];
    // With no conversion waiting the part NACKs the read, which arrives here
    // as a failed transfer.
    if (!readAnswer(words, 3)) return false;
    out.co2Ppm = words[0];
    out.tempC = -45.0f + 175.0f * (float)words[1] / 65535.0f;
    out.rhPct = 100.0f * (float)words[2] / 65535.0f;
    if (mode_ == SINGLE_SHOT) mode_ = IDLE;
    return true;
}

bool Scd41Driver::setAmbientPressure(uint32_t pa) {
    if (mode_ == POWERED_DOWN) return false;
    if (pa < kMinPressurePa || pa > kMaxPressurePa) return false;
    return sensirion::sendCommandWithArg(bus_, addr_, kCmdSetAmbientPressure,
                                         (uint16_t)(pa / 100));
}

bool Scd41Driver::setTemperatureOffset(float degC) {
    if (mode_ != IDLE) return false;
    if (degC < 0.0f || degC > kMaxOffsetC) return false;
    uint16_t word = (uint16_t)(degC * 65535.0f / kMaxOffsetC + 0.5f);
    return sensirion::sendCommandWithArg(bus_, addr_, kCmdSetTemperatureOffset, word);
}

bool Scd41Driver::powerDown() {
    if (mode_ != IDLE) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdPowerDown)) return false;
    mode_ = POWERED_DOWN;
    return true;
}

bool Scd41Driver::wakeUp(uint32_t nowMs) {
    (void)nowMs;
    if (mode_ != POWERED_DOWN) return false;
    // The part does not ACK its own wake-up command, so the write reports a
    // failure every time. Reading the serial number is what proves it woke.
    sensirion::sendCommand(bus_, addr_, kCmdWakeUp);
    clock_.waitMs(kWakeMs);
    mode_ = IDLE;
    busyUntilMs_ = clock_.millis();

    uint64_t serial = 0;
    if (getSerialNumber(serial)) return true;
    mode_ = POWERED_DOWN;
    return false;
}

bool Scd41Driver::getSerialNumber(uint64_t& serial) {
    if (mode_ == POWERED_DOWN) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdGetSerialNumber)) return false;
    uint16_t words[3];
    if (!readAnswer(words, 3)) return false;
    serial = (uint64_t)words[0] << 32 | (uint64_t)words[1] << 16 | words[2];
    return true;
}

bool Scd41Driver::readAnswer(uint16_t* words, size_t count) {
    clock_.waitMs(kCommandMs);
    return sensirion::readWords(bus_, addr_, words, count);
}
