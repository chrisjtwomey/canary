#include "sensors/Shtc3Driver.h"

#include "sensors/SensirionI2c.h"

bool Shtc3Driver::begin(uint32_t nowMs) {
    if (!wakeup(nowMs)) return false;
    if ((readId() & kIdMask) != kId) return false;
    if (!sensirion::sendCommand(bus_, addr_, kCmdSoftReset)) return false;
    clock_.waitMs(kSettleMs);
    // A soft reset returns the part to its power-on state, which is sleep, so
    // sending the sleep command here would be NACKed.
    asleep_ = true;
    measuring_ = false;
    return true;
}

bool Shtc3Driver::wakeup(uint32_t nowMs) {
    (void)nowMs;
    if (!sensirion::sendCommand(bus_, addr_, kCmdWakeup)) return false;
    clock_.waitMs(kSettleMs);
    asleep_ = false;
    measuring_ = false;
    return true;
}

bool Shtc3Driver::sleep() {
    if (asleep_) return true;
    if (!sensirion::sendCommand(bus_, addr_, kCmdSleep)) return false;
    asleep_ = true;
    measuring_ = false;
    return true;
}

bool Shtc3Driver::measure(uint32_t nowMs, bool lowPower) {
    if (asleep_) return false;
    if (!sensirion::sendCommand(bus_, addr_, lowPower ? kCmdMeasureLp : kCmdMeasure)) return false;
    measuring_ = true;
    readyAtMs_ = nowMs + (lowPower ? kLowPowerMs : kNormalMs);
    return true;
}

bool Shtc3Driver::read(uint32_t nowMs, Shtc3Data& out) {
    if (asleep_ || !measuring_ || nowMs < readyAtMs_) return false;
    uint16_t words[2];
    if (!readAnswer(words, 2)) return false;
    measuring_ = false;
    out.tempC = -45.0f + 175.0f * (float)words[0] / 65536.0f;
    out.rhPct = 100.0f * (float)words[1] / 65536.0f;
    return true;
}

uint16_t Shtc3Driver::readId() {
    if (asleep_) return 0;
    if (!sensirion::sendCommand(bus_, addr_, kCmdReadId)) return 0;
    uint16_t id = 0;
    if (!readAnswer(&id, 1)) return 0;
    return id;
}

bool Shtc3Driver::readAnswer(uint16_t* words, size_t count) {
    const sensirion::ReadResult result = sensirion::readWordsChecked(bus_, addr_, words, count);
    if (result == sensirion::BAD_CRC) ++crcFailures_;
    return result == sensirion::READ_OK;
}
