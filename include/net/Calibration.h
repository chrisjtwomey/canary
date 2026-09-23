#pragma once
#include <cstddef>
#include <cstdint>

// BSEC's learned state on its way to the server and back: the calibration
// block in each readings POST, the server's answer to GET /calibration, and
// the rule for which of two saved copies BSEC should run on.

// Base64 without line breaks. Each returns the length written, or 0 when the
// output does not fit; decoding also returns 0 for anything but base64.
size_t base64Encode(const uint8_t* in, size_t len, char* out, size_t outLen);
size_t base64Decode(const char* in, size_t inLen, uint8_t* out, size_t outLen);

// {"bme688":{"state":"<base64>","accuracy":3,"saved":1757443200,"sample_s":300}}.
// Returns the length written, or 0 when it does not fit.
size_t calibrationJson(const uint8_t* state, uint32_t len, uint8_t accuracy, uint32_t savedEpoch,
                       uint16_t sampleS, char* buf, size_t bufLen);

// `doc` with "key":obj added before its closing brace. Returns the length
// written, or 0 when out is too small or doc or obj is not an object.
size_t withMember(const char* doc, const char* key, const char* obj, char* out, size_t len);

// The bme688 entry of the server's answer, decoded. False when there is none
// or it does not parse.
bool parseBme688Calibration(const char* json, uint8_t* state, uint32_t max, uint32_t& len,
                            uint8_t& accuracy, uint32_t& savedEpoch, uint16_t& sampleS);

// What the board knows of a saved state. A savedEpoch of 0 is a copy saved
// before NTP set the clock, whose age is unknown.
struct SavedCopy {
    bool     present;
    uint8_t  accuracy;
    uint32_t savedEpoch;
};

// Which branch of the rule decided: one value for each.
enum class CopyReason : uint8_t {
    NoServerCopy,
    NoNvsCopy,
    MoreAccurate,
    LessAccurate,
    ServerHasNoTime,
    NvsHasNoTime,
    Newer,           // same accuracy, more than kNewerByS newer
    NotNewEnough,    // same accuracy, older or at most kNewerByS newer
};

struct CopyChoice {
    bool       takeServer;
    CopyReason reason;
};

// Whether BSEC should restart on the server's copy rather than go on with the
// one it took from NVS, and why. Never for a less accurate copy; always for a
// more accurate one; at the same accuracy, only for one more than kNewerByS
// newer, where a copy with no time counts as the older.
CopyChoice chooseCopy(const SavedCopy& nvs, const SavedCopy& server);
static const uint32_t kNewerByS = 3600;

// The choice as the log gives it, e.g. "server selected (more accurate: 3 vs
// 1)". Returns the length written, or 0 when it does not fit.
size_t describeChoice(const SavedCopy& nvs, const SavedCopy& server, const CopyChoice& choice,
                      char* buf, size_t len);
