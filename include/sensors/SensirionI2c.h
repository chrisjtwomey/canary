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

// What a read of words came to. A NACK is how both parts say "no data"; a
// word whose CRC is wrong arrived damaged, which a sound bus never does.
enum ReadResult : uint8_t { READ_OK, NO_ANSWER, BAD_CRC };

// Read `count` words, checking every CRC.
ReadResult readWordsChecked(II2cBus& bus, uint8_t addr, uint16_t* words, size_t count);

// The same, true only when every word arrived whole.
bool readWords(II2cBus& bus, uint8_t addr, uint16_t* words, size_t count);

}  // namespace sensirion
