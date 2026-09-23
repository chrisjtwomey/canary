#pragma once
#include <cstddef>
#include <cstdint>

// The status light's triggers that have a look, in StatusLed::State's order,
// and its patterns, in StatusLed::Pattern's.
static const uint8_t kLedTriggers = 5;
static const uint8_t kLedPatterns = 4;

// The dock's settings as the server's GET /board-settings gives them, held to
// the dock's own limits whatever the server says.
struct BoardSettings {
    char     version[12];        // "" until the server has given any
    uint16_t pmWarmupS;          // 0 keeps the fan on
    float    scd41OffsetC;
    bool     scd41SelfCalibration;
    bool     shtc3LowPower;
    uint8_t  ledBrightnessPct;
    uint8_t  logLevel;           // log_utils.h's numbering: 1 error to 5 debug
    uint16_t bsecSampleS;        // IBsec::kLpSampleS or kUlpSampleS
    uint8_t  ledPattern[kLedTriggers];
    uint16_t ledIntervalMs[kLedTriggers];
};

// The server's defaults, which the dock runs until the server has said anything.
BoardSettings defaultBoardSettings();

// The keys the dock can refuse, each a bit of SettingsAnswer::refused.
enum SettingKey : uint8_t {
    kPmWarmup,
    kScd41Offset,
    kScd41SelfCalibration,
    kShtc3LowPower,
    kLedBrightness,
    kLogLevel,
    kBsecSampleS,
    // Each trigger's pattern, then its interval: kLedLook + 2 * trigger (+ 1).
    kLedLook,
    kSettingKeys = kLedLook + 2 * kLedTriggers,
};

// The key as the server names it, e.g. "pm.warmup_s".
const char* settingKeyName(uint8_t key);

struct SettingsAnswer {
    BoardSettings settings;
    uint32_t refused;            // a bit per SettingKey out of range or of the wrong kind
    bool     dark;               // the light stays dark until the next reading
    uint32_t recalibrateId;      // 0 for none
    uint16_t recalibratePpm;
};

// The server's answer on top of `current`: a key in range replaces current's
// value, one out of range keeps it and is marked refused, and one the answer
// lacks keeps it. False when the text is not a JSON object with a version.
bool parseBoardSettings(const char* json, size_t len, const BoardSettings& current,
                        SettingsAnswer& out);

// The refused keys as a JSON array. Returns the length written, or 0 when it
// does not fit.
size_t refusedJson(uint32_t refused, char* buf, size_t len);

// The room refusedJson needs with every key refused, and its terminator.
static const size_t kRefusedJsonBytes = 512;

static const uint16_t kPmWarmupMinS = 30;
static const uint16_t kPmWarmupMaxS = 600;
static const float    kScd41OffsetMaxC = 20.0f;
static const uint16_t kRecalibrateMinPpm = 400;
static const uint16_t kRecalibrateMaxPpm = 2000;
static const uint16_t kLedIntervalMinMs = 250;
static const uint16_t kLedIntervalMaxMs = 10000;
