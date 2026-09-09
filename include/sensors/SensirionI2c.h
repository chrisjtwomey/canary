#pragma once
#include <cstddef>
#include <cstdint>

class II2cBus;

// The wire conventions the SHTC3 and the SCD41 share: 16-bit big-endian
// commands, and every data word followed by a CRC-8 over that word
// (polynomial 0x31, initial value 0xFF, no reflection, no final XOR).
namespace sensirion {

// The most words either part returns in one read.
const size_t kMaxWords = 3;

uint8_t crc8(const uint8_t* data, size_t len);

bool sendCommand(II2cBus& bus, uint8_t addr, uint16_t cmd);

// A command carrying one argument word, which the part expects with its CRC.
bool sendCommandWithArg(II2cBus& bus, uint8_t addr, uint16_t cmd, uint16_t arg);

// Read `count` words, checking every CRC. False if any is wrong, or if the
// part NACKed, which is how both of these report "no data".
bool readWords(II2cBus& bus, uint8_t addr, uint16_t* words, size_t count);

}  // namespace sensirion
