#include "sensors/SensirionI2c.h"

#include "sensors/II2cBus.h"

namespace sensirion {

uint8_t crc8(const uint8_t* data, size_t len) {
    uint8_t crc = 0xFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
        }
    }
    return crc;
}

bool sendCommand(II2cBus& bus, uint8_t addr, uint16_t cmd) {
    const uint8_t tx[2] = {(uint8_t)(cmd >> 8), (uint8_t)(cmd & 0xFF)};
    return bus.write(addr, tx, sizeof(tx));
}

bool sendCommandWithArg(II2cBus& bus, uint8_t addr, uint16_t cmd, uint16_t arg) {
    uint8_t tx[5] = {(uint8_t)(cmd >> 8), (uint8_t)(cmd & 0xFF),
                     (uint8_t)(arg >> 8), (uint8_t)(arg & 0xFF), 0};
    tx[4] = crc8(&tx[2], 2);
    return bus.write(addr, tx, sizeof(tx));
}

ReadResult readWordsChecked(II2cBus& bus, uint8_t addr, uint16_t* words, size_t count) {
    if (count == 0 || count > kMaxWords) return NO_ANSWER;
    uint8_t rx[kMaxWords * 3];
    if (!bus.read(addr, rx, count * 3)) return NO_ANSWER;
    for (size_t i = 0; i < count; ++i) {
        const uint8_t* w = &rx[i * 3];
        if (crc8(w, 2) != w[2]) return BAD_CRC;
        words[i] = (uint16_t)(w[0] << 8 | w[1]);
    }
    return READ_OK;
}

bool readWords(II2cBus& bus, uint8_t addr, uint16_t* words, size_t count) {
    return readWordsChecked(bus, addr, words, count) == READ_OK;
}

}  // namespace sensirion
