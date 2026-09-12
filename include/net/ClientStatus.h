#pragma once
#include <cstddef>
#include <cstdint>

// What the board says about itself, posted beside the readings as the
// "client" object. Diagnostics, not measurements.
struct ClientStatus {
    const char* board;
    const char* version;
    const char* ip;
    int         rssi;            // dBm
    uint32_t    uptimeS;
    uint32_t    heapFree, heapSize;
    uint32_t    psramFree, psramSize;
    int         panelTempC;
    int16_t     width, height;
    uint8_t     rotation;
    bool        mockSensors;
    bool        shtc3, scd41, pm, bme688;   // running now
    const char* nextUrl;
    uint32_t    nextInS;
    int         backoffStep;
    uint32_t    fetchOk, fetchFailed;
};

// Encodes the "client" object. Returns the length written, or 0 if the
// buffer is too small (nothing partial is left behind).
size_t clientStatusJson(const ClientStatus& s, char* buf, size_t len);

// The readings document with the client object added before its closing
// brace. Returns the length written, or 0 if out is too small or either
// input is not an object.
size_t withClientStatus(const char* readingsJson, const char* clientJson, char* out, size_t len);
