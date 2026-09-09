#pragma once
#include <cstdint>

#include "FakeI2c.h"

// The four parts as their datasheets describe them on the wire: which
// commands they accept in which state, and what bytes come back. They answer
// the bus, not the interface, so a driver that sends the wrong command or
// mishandles a NACK fails here rather than on the bench.

class FakeShtc3 : public SensirionDevice {
public:
    float    tempC = 21.0f;
    float    rhPct = 45.0f;
    uint16_t id = 0x0887;
    bool     asleep = true;
    int      measures = 0;

    bool write(const uint8_t* data, size_t len) override {
        if (len != 2) return false;
        uint16_t cmd = command(data);
        if (cmd == 0x3517) {   // wake-up, the one command sleep accepts
            asleep = false;
            return true;
        }
        if (asleep) return false;
        switch (cmd) {
            case 0xB098: asleep = true; return true;
            case 0x805D: asleep = true; return true;   // soft reset ends in sleep
            case 0xEFC8: queue(&id, 1); return true;
            case 0x7866:
            case 0x609C: {
                ++measures;
                uint16_t words[2] = {rawTemp(), rawRh()};
                queue(words, 2);
                return true;
            }
            default: return false;
        }
    }

private:
    uint16_t rawTemp() const { return raw((tempC + 45.0f) / 175.0f); }
    uint16_t rawRh() const { return raw(rhPct / 100.0f); }
    static uint16_t raw(float fraction) {
        float scaled = fraction * 65536.0f;
        if (scaled < 0.0f) return 0;
        if (scaled > 65535.0f) return 65535;
        return (uint16_t)(scaled + 0.5f);
    }
};

class FakeScd41 : public SensirionDevice {
public:
    uint16_t co2Ppm = 800;
    float    tempC = 25.0f;
    float    rhPct = 40.0f;
    uint64_t serial = 0xC0FFEE41ull;
    bool     dataReady = false;
    bool     periodic = false;
    bool     poweredDown = false;
    uint32_t lastPressurePa = 0;
    uint16_t lastOffsetWord = 0;
    int      stopsAccepted = 0;
    int      stopsRefused = 0;
    int      wakeUps = 0;
    int      singleShots = 0;

    bool write(const uint8_t* data, size_t len) override {
        if (len < 2) return false;
        uint16_t cmd = command(data);
        if (poweredDown) {
            // The part hears its own wake-up and nothing else, and does not
            // acknowledge even that one.
            if (cmd == 0x36F6) {
                ++wakeUps;
                poweredDown = false;
            }
            return false;
        }
        switch (cmd) {
            case 0x21B1:   // start periodic
            case 0x21AC:   // start low-power periodic
                if (periodic) return false;
                periodic = true;
                // The part converts on its own interval. With no clock here
                // that collapses to "a reading is always waiting", which is
                // what a caller polling data-ready sees.
                dataReady = true;
                return true;
            case 0x3F86:   // stop periodic
                if (!periodic) { ++stopsRefused; return false; }
                ++stopsAccepted;
                periodic = false;
                dataReady = false;
                return true;
            case 0x219D:   // single shot
                if (periodic) return false;
                ++singleShots;
                dataReady = true;
                return true;
            case 0xE4B8: {
                // The top five bits are reserved and carry whatever they
                // carry; a reader that does not mask them sees data that is
                // not there.
                uint16_t status = dataReady ? 0x8006 : 0x8000;
                queue(&status, 1);
                return true;
            }
            case 0xEC05: {
                if (!dataReady) return false;
                uint16_t words[3] = {co2Ppm, rawTemp(), rawRh()};
                queue(words, 3);
                dataReady = periodic;
                return true;
            }
            case 0xE000:
                if (len != 5 || !argCrcOk(data)) return false;
                lastPressurePa = (uint32_t)arg(data) * 100;
                return true;
            case 0x241D:
                if (periodic || len != 5 || !argCrcOk(data)) return false;
                lastOffsetWord = arg(data);
                return true;
            case 0x36E0:
                if (periodic) return false;
                poweredDown = true;
                return true;
            case 0x3682: {
                uint16_t words[3] = {(uint16_t)(serial >> 32), (uint16_t)(serial >> 16),
                                     (uint16_t)serial};
                queue(words, 3);
                return true;
            }
            default:
                return false;
        }
    }

private:
    uint16_t rawTemp() const { return raw((tempC + 45.0f) / 175.0f); }
    uint16_t rawRh() const { return raw(rhPct / 100.0f); }
    static uint16_t raw(float fraction) {
        float scaled = fraction * 65535.0f;
        if (scaled < 0.0f) return 0;
        if (scaled > 65535.0f) return 65535;
        return (uint16_t)(scaled + 0.5f);
    }
    static uint16_t arg(const uint8_t* data) { return (uint16_t)(data[2] << 8 | data[3]); }
    static bool argCrcOk(const uint8_t* data) { return sensirion::crc8(&data[2], 2) == data[4]; }
};

class FakePmsa003i : public FakeDevice {
public:
    uint16_t pm1 = 4, pm25 = 6, pm10 = 8;
    bool     answering = true;
    int      corruptFrames = 0;
    int      frameReads = 0;

    // The module has no commands at all.
    bool write(const uint8_t*, size_t) override { return false; }

    bool read(uint8_t* data, size_t len) override {
        if (!answering || len != 32) return false;
        ++frameReads;
        buildFrame(data);
        if (corruptFrames > 0) {
            --corruptFrames;
            data[31] ^= 0x5A;
        }
        return true;
    }

private:
    void buildFrame(uint8_t* f) {
        for (int i = 0; i < 32; ++i) f[i] = 0;
        f[0] = 0x42; f[1] = 0x4D;
        put16(f + 2, 28);
        put16(f + 4, pm1);   put16(f + 6, pm25);   put16(f + 8, pm10);
        put16(f + 10, pm1);  put16(f + 12, pm25);  put16(f + 14, pm10);
        put16(f + 16, (uint16_t)(pm25 * 150));
        f[28] = 0x97;
        uint16_t sum = 0;
        for (int i = 0; i < 30; ++i) sum += f[i];
        put16(f + 30, sum);
    }
    static void put16(uint8_t* p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
};

class FakeBme688 : public FakeDevice {
public:
    // Registers, as the part exposes them. Calibration is left at zero: the
    // compensation is Bosch's and is not what these tests are about.
    uint8_t regs[256] = {0};
    bool    answering = true;

    FakeBme688() {
        regs[kRegChipId] = 0x61;
        regs[kRegVariantId] = 0x01;      // BME688; a BME680 answers 0x00
        regs[kRegField0] = 0x80;         // new data
        regs[kRegGasStatus] = 0x20 | 0x10;   // gas valid, heater stable
    }

    // Bosch writes register and value in pairs, the first address arriving
    // ahead of the rest of the buffer.
    bool write(const uint8_t* data, size_t len) override {
        if (!answering || len < 2) return false;
        for (size_t i = 0; i + 1 < len; i += 2) regs[data[i]] = data[i + 1];
        return true;
    }

    // The part is never read without naming a register first.
    bool read(uint8_t*, size_t) override { return false; }

    bool writeThenRead(const uint8_t* tx, size_t txLen, uint8_t* rx, size_t rxLen) override {
        if (!answering || txLen != 1) return false;
        for (size_t i = 0; i < rxLen; ++i) rx[i] = regs[(uint8_t)(tx[0] + i)];
        return true;
    }

    // Calibration and a raw conversion, so the compensated values Bosch's
    // API returns are inside the ranges docs/HARDWARE.md 4 gives the part.
    // The coefficients are a real unit's; the ADC counts are chosen to land
    // near room conditions.
    void loadCalibration(uint32_t tempAdc = kTempAdc, uint32_t presAdc = kPresAdc,
                         uint16_t humAdc = kHumAdc) {
        put16le(0x8A, (uint16_t)26543);            // par_t2
        regs[0x8C] = (uint8_t)(int8_t)3;           // par_t3
        put16le(0xE9, 26060);                      // par_t1
        put16le(0x8E, 36160);                      // par_p1
        put16le(0x90, (uint16_t)(int16_t)-10559);  // par_p2
        regs[0x92] = (uint8_t)(int8_t)88;          // par_p3
        put16le(0x94, (uint16_t)(int16_t)7480);    // par_p4
        put16le(0x96, (uint16_t)(int16_t)-140);    // par_p5
        regs[0x98] = (uint8_t)(int8_t)41;          // par_p7
        regs[0x99] = (uint8_t)(int8_t)30;          // par_p6
        put16le(0x9C, (uint16_t)(int16_t)-3568);   // par_p8
        put16le(0x9E, (uint16_t)(int16_t)-2745);   // par_p9
        regs[0xA0] = 30;                           // par_p10
        regs[0xE1] = 0x3F;                         // par_h2 high bits
        regs[0xE2] = 0x20;                         // par_h2 low nibble, par_h1 low nibble
        regs[0xE3] = 0x33;                         // par_h1 high bits
        regs[0xE4] = 0;                            // par_h3
        regs[0xE5] = 45;                           // par_h4
        regs[0xE6] = 20;                           // par_h5
        regs[0xE7] = 120;                          // par_h6
        regs[0xE8] = (uint8_t)(int8_t)-100;        // par_h7

        putAdc20(0x1F, presAdc);
        putAdc20(0x22, tempAdc);
        regs[0x25] = (uint8_t)(humAdc >> 8);
        regs[0x26] = (uint8_t)humAdc;
        // A gas reading in a middle range, so the resistance is non-zero.
        regs[0x2C] = 0x80;
        regs[0x2D] = (uint8_t)(0x20 | 0x10 | 0x05);
    }

    static const uint32_t kTempAdc = 500000;
    static const uint32_t kPresAdc = 360000;
    static const uint16_t kHumAdc  = 25000;

    static const uint8_t kRegChipId    = 0xD0;
    static const uint8_t kRegVariantId = 0xF0;
    static const uint8_t kRegField0    = 0x1D;
    static const uint8_t kRegGasStatus = 0x2D;   // gas_valid and heat_stab, high-gas variant
    static const uint8_t kRegCtrlHum   = 0x72;
    static const uint8_t kRegCtrlMeas  = 0x74;
    static const uint8_t kRegCtrlGas1  = 0x71;
    static const uint8_t kRegResHeat0  = 0x5A;
    static const uint8_t kRegGasWait0  = 0x64;

private:
    void put16le(uint8_t reg, uint16_t v) {
        regs[reg] = (uint8_t)v;
        regs[reg + 1] = (uint8_t)(v >> 8);
    }
    void putAdc20(uint8_t reg, uint32_t adc) {
        regs[reg] = (uint8_t)(adc >> 12);
        regs[reg + 1] = (uint8_t)(adc >> 4);
        regs[reg + 2] = (uint8_t)((adc & 0x0F) << 4);
    }
};
