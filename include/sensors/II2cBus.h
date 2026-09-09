#pragma once
#include <cstddef>
#include <cstdint>

// The I2C bus a sensor driver talks to. Injected for the same reason IClock
// is: the register sequences, the CRCs and the conversions are the part of a
// driver worth testing, and a host test cannot drive Wire.
class II2cBus {
public:
    virtual ~II2cBus() {}
    // True when the device ACKed its address and took every byte.
    virtual bool write(uint8_t addr, const uint8_t* data, size_t len) = 0;
    // True when `len` bytes arrived.
    virtual bool read(uint8_t addr, uint8_t* data, size_t len) = 0;
    // Write, then read across a repeated start. Register-addressed parts want
    // this; Sensirion parts want a stop and a wait between the two, so they
    // use write() and read() instead.
    virtual bool writeRead(uint8_t addr, const uint8_t* tx, size_t txLen,
                           uint8_t* rx, size_t rxLen) = 0;
};

#if !defined(NATIVE)
#include <Wire.h>

// Wire, which Inkplate::begin() has already started at 100 kHz.
class ArduinoI2cBus : public II2cBus {
public:
    explicit ArduinoI2cBus(TwoWire& wire = Wire) : wire_(wire) {}

    bool write(uint8_t addr, const uint8_t* data, size_t len) override {
        wire_.beginTransmission(addr);
        if (len && wire_.write(data, len) != len) return false;
        return wire_.endTransmission() == 0;
    }

    bool read(uint8_t addr, uint8_t* data, size_t len) override {
        if (wire_.requestFrom((uint16_t)addr, (uint8_t)len) != len) return false;
        for (size_t i = 0; i < len; ++i) data[i] = (uint8_t)wire_.read();
        return true;
    }

    bool writeRead(uint8_t addr, const uint8_t* tx, size_t txLen,
                   uint8_t* rx, size_t rxLen) override {
        wire_.beginTransmission(addr);
        if (wire_.write(tx, txLen) != txLen) return false;
        if (wire_.endTransmission(false) != 0) return false;
        return read(addr, rx, rxLen);
    }

private:
    TwoWire& wire_;
};
#endif
