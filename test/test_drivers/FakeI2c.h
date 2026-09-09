#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "sensors/II2cBus.h"
#include "sensors/SensirionI2c.h"

// A part on the fake bus. Every transfer either ACKs (true) or NACKs
// (false), which is all a real part tells the host.
class FakeDevice {
public:
    virtual ~FakeDevice() {}
    virtual bool write(const uint8_t* data, size_t len) = 0;
    virtual bool read(uint8_t* data, size_t len) = 0;
    // A repeated start. Register-addressed parts take the write as the
    // address of the read; the Sensirion parts never see one.
    virtual bool writeThenRead(const uint8_t* tx, size_t txLen, uint8_t* rx, size_t rxLen) {
        return write(tx, txLen) && read(rx, rxLen);
    }
};

class FakeI2cBus : public II2cBus {
public:
    static const size_t kMaxDevices = 4;

    void attach(uint8_t addr, FakeDevice* device) {
        if (count_ >= kMaxDevices) return;
        addrs_[count_] = addr;
        devices_[count_] = device;
        ++count_;
    }

    bool write(uint8_t addr, const uint8_t* data, size_t len) override {
        ++writes;
        FakeDevice* d = find(addr);
        return d && d->write(data, len);
    }

    bool read(uint8_t addr, uint8_t* data, size_t len) override {
        ++reads;
        FakeDevice* d = find(addr);
        return d && d->read(data, len);
    }

    bool writeRead(uint8_t addr, const uint8_t* tx, size_t txLen,
                   uint8_t* rx, size_t rxLen) override {
        ++writeReads;
        FakeDevice* d = find(addr);
        return d && d->writeThenRead(tx, txLen, rx, rxLen);
    }

    int writes = 0;
    int reads = 0;
    int writeReads = 0;

private:
    FakeDevice* find(uint8_t addr) {
        for (size_t i = 0; i < count_; ++i) {
            if (addrs_[i] == addr) return devices_[i];
        }
        return nullptr;   // nobody home: the address is not ACKed
    }

    uint8_t     addrs_[kMaxDevices] = {0};
    FakeDevice* devices_[kMaxDevices] = {nullptr};
    size_t      count_ = 0;
};

// The answer buffer both Sensirion parts build: words, each followed by its
// CRC. sensirion::crc8 is checked against the datasheet's own vector in the
// tests before anything here relies on it.
class SensirionDevice : public FakeDevice {
public:
    bool read(uint8_t* data, size_t len) override {
        if (pendingWords_ == 0 || len != pendingWords_ * 3) return false;
        memcpy(data, buf_, len);
        pendingWords_ = 0;
        return true;
    }

    // Flip a bit in the next answer, the way a bus glitch would.
    void corruptNextAnswer() { corrupt_ = true; }

protected:
    void queue(const uint16_t* words, size_t count) {
        for (size_t i = 0; i < count; ++i) {
            uint8_t* w = &buf_[i * 3];
            w[0] = (uint8_t)(words[i] >> 8);
            w[1] = (uint8_t)(words[i] & 0xFF);
            w[2] = sensirion::crc8(w, 2);
        }
        if (corrupt_) {
            buf_[1] ^= 0x01;
            corrupt_ = false;
        }
        pendingWords_ = count;
    }

    static uint16_t command(const uint8_t* data) {
        return (uint16_t)(data[0] << 8 | data[1]);
    }

private:
    uint8_t buf_[sensirion::kMaxWords * 3] = {0};
    size_t  pendingWords_ = 0;
    bool    corrupt_ = false;
};
