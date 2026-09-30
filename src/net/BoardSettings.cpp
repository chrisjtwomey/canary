#include "net/BoardSettings.h"

#include <ArduinoJson.h>
#include <cstdio>
#include <cstring>

#include "dock/StatusLed.h"

static const char* const kKeyNames[kSettingKeys] = {
    "pm.warmup_s",
    "scd41.temperature_offset_c",
    "scd41.self_calibration",
    "shtc3.low_power",
    "led.brightness_pct",
    "log.level",
    "bsec.sample_s",
    "led.looks",
    "led.smoothness",
    "scd41.poor_air_ppm",
    "pm.poor_air_ug_m3",
    "bsec.poor_air_iaq",
    "scd41.warmup_s",
};

static const char* const kLedTriggerNames[kLedTriggers] = {
    "booting", "error", "poor_air_quality", "calibrating", "running",
};
static const char* const kLedPatternNames[kLedPatterns] = {
    "off", "solid", "pulse", "flash",
    "double_flash", "triple_flash", "double_pulse", "triple_pulse",
    "blip", "swell", "ramp",
};
// The server's defaults, in StatusLed's numbering.
static const uint8_t  kLedDefaultPattern[kLedTriggers] = {
    StatusLed::PULSE, StatusLed::FLASH, StatusLed::DOUBLE_FLASH, StatusLed::SWELL, StatusLed::PULSE};
static const uint16_t kLedDefaultLengthMs[kLedTriggers] = {500, 1000, 2000, 4000, 1000};

// In log_utils.h's order, from LOG_ERROR.
static const char* const kLevels[] = {"error", "warning", "notice", "info", "debug"};

BoardSettings defaultBoardSettings() {
    BoardSettings s = {};
    s.pmWarmupS = 35;
    s.scd41OffsetC = 4.0f;
    s.scd41SelfCalibration = true;
    s.shtc3LowPower = false;
    s.ledBrightnessPct = 15;
    s.logLevel = 5;
    s.bsecSampleS = 300;
    for (uint8_t t = 0; t < kLedTriggers; ++t) {
        s.ledPattern[t] = kLedDefaultPattern[t];
        s.ledLengthMs[t] = kLedDefaultLengthMs[t];
    }
    s.ledSmoothness = StatusLed::kDefaultSmoothness;
    s.scd41PoorPpm = 1500;
    s.pmPoorUgM3 = 37.5f;
    s.bsecPoorIaq = 150;
    s.scd41WarmupS = 180;
    return s;
}

const char* settingKeyName(uint8_t key) { return key < kSettingKeys ? kKeyNames[key] : ""; }

namespace {

// Each take* leaves `value` alone when the key is absent, and marks the key
// refused when it is there but unusable.
class Taker {
public:
    explicit Taker(uint32_t& refused) : refused_(refused) {}

    template <typename T>
    void take(JsonVariantConst v, SettingKey key, T& value, bool (*usable)(JsonVariantConst)) {
        if (v.isNull()) return;
        if (!usable(v)) {
            refuse(key);
            return;
        }
        value = v.as<T>();
    }

    void refuse(uint8_t key) { refused_ |= 1ul << key; }

private:
    uint32_t& refused_;
};

bool warmupUsable(JsonVariantConst v) {
    if (!v.is<int>()) return false;
    const int s = v.as<int>();
    return s == 0 || (s >= kPmWarmupMinS && s <= kPmWarmupMaxS);
}
bool scd41WarmupUsable(JsonVariantConst v) {
    return v.is<int>() && v.as<int>() >= 0 && v.as<int>() <= kScd41WarmupMaxS;
}
bool offsetUsable(JsonVariantConst v) {
    if (!v.is<float>()) return false;
    const float c = v.as<float>();
    return c >= 0.0f && c <= kScd41OffsetMaxC;
}
bool boolUsable(JsonVariantConst v) { return v.is<bool>(); }
bool rateUsable(JsonVariantConst v) {
    return v.is<int>() && (v.as<int>() == 3 || v.as<int>() == 300);
}
bool pctUsable(JsonVariantConst v) {
    return v.is<int>() && v.as<int>() >= 0 && v.as<int>() <= 100;
}
bool smoothnessUsable(JsonVariantConst v) {
    return v.is<int>() && v.as<int>() >= 1 && v.as<int>() <= StatusLed::kSmoothnessStops;
}
bool poorPpmUsable(JsonVariantConst v) {
    return v.is<int>() && v.as<int>() >= kPoorPpmMin && v.as<int>() <= kPoorPpmMax;
}
bool poorUgM3Usable(JsonVariantConst v) {
    return v.is<float>() && v.as<float>() >= kPoorUgM3Min && v.as<float>() <= kPoorUgM3Max;
}
bool poorIaqUsable(JsonVariantConst v) {
    return v.is<int>() && v.as<int>() >= kPoorIaqMin && v.as<int>() <= kPoorIaqMax;
}

// `name`'s place in `names`, or -1.
int indexOf(const char* name, const char* const* names, uint8_t count) {
    for (uint8_t i = 0; i < count; ++i) {
        if (strcmp(name, names[i]) == 0) return i;
    }
    return -1;
}

int nameIn(JsonVariantConst v, const char* const* names, uint8_t count) {
    return v.is<const char*>() ? indexOf(v.as<const char*>(), names, count) : -1;
}

// The looks, a list of {trigger, pattern, length_s}, replace all of `s`'s:
// a trigger the list leaves out has none. False, with `s` as it was, when
// the dock cannot use the list or any look in it.
bool takeLedLooks(JsonVariantConst looks, BoardSettings& s) {
    if (!looks.is<JsonArrayConst>()) return false;
    uint8_t pattern[kLedTriggers];
    uint16_t lengthMs[kLedTriggers];
    for (uint8_t t = 0; t < kLedTriggers; ++t) {
        pattern[t] = kLedNoLook;
        lengthMs[t] = s.ledLengthMs[t];
    }
    for (JsonVariantConst look : looks.as<JsonArrayConst>()) {
        const int t = nameIn(look["trigger"], kLedTriggerNames, kLedTriggers);
        if (t < 0 || pattern[t] != kLedNoLook) return false;
        const int p = nameIn(look["pattern"], kLedPatternNames, kLedPatterns);
        if (p < 0) return false;
        JsonVariantConst length = look["length_s"];
        const float ms = length.is<float>() ? length.as<float>() * 1000.0f : -1.0f;
        if (ms < StatusLed::minLengthMs((StatusLed::Pattern)p) - 0.5f ||
            ms > StatusLed::kMaxLengthMs + 0.5f) return false;
        pattern[t] = (uint8_t)p;
        lengthMs[t] = (uint16_t)(ms + 0.5f);
    }
    memcpy(s.ledPattern, pattern, sizeof(pattern));
    memcpy(s.ledLengthMs, lengthMs, sizeof(lengthMs));
    return true;
}

}  // namespace

bool parseBoardSettings(const char* json, size_t len, const BoardSettings& current,
                        SettingsAnswer& out) {
    JsonDocument doc;
    if (deserializeJson(doc, json, len) || !doc.is<JsonObjectConst>()) return false;
    const char* version = doc["version"] | (const char*)nullptr;
    if (!version || !version[0] || strlen(version) >= sizeof(out.settings.version)) return false;

    out = SettingsAnswer();
    out.settings = current;
    strcpy(out.settings.version, version);
    Taker t(out.refused);
    BoardSettings& s = out.settings;
    t.take(doc["pm"]["warmup_s"], kPmWarmup, s.pmWarmupS, warmupUsable);
    t.take(doc["scd41"]["temperature_offset_c"], kScd41Offset, s.scd41OffsetC, offsetUsable);
    t.take(doc["scd41"]["self_calibration"], kScd41SelfCalibration, s.scd41SelfCalibration,
           boolUsable);
    t.take(doc["shtc3"]["low_power"], kShtc3LowPower, s.shtc3LowPower, boolUsable);
    t.take(doc["led"]["brightness_pct"], kLedBrightness, s.ledBrightnessPct, pctUsable);
    t.take(doc["bsec"]["sample_s"], kBsecSampleS, s.bsecSampleS, rateUsable);
    t.take(doc["led"]["smoothness"], kLedSmoothness, s.ledSmoothness, smoothnessUsable);
    t.take(doc["scd41"]["poor_air_ppm"], kScd41PoorPpm, s.scd41PoorPpm, poorPpmUsable);
    t.take(doc["pm"]["poor_air_ug_m3"], kPmPoorUgM3, s.pmPoorUgM3, poorUgM3Usable);
    t.take(doc["bsec"]["poor_air_iaq"], kBsecPoorIaq, s.bsecPoorIaq, poorIaqUsable);
    t.take(doc["scd41"]["warmup_s"], kScd41Warmup, s.scd41WarmupS, scd41WarmupUsable);
    JsonVariantConst looks = doc["led"]["looks"];
    if (!looks.isNull() && !takeLedLooks(looks, s)) t.refuse(kLedLooks);

    JsonVariantConst level = doc["log"]["level"];
    if (!level.isNull()) {
        const char* name = level.is<const char*>() ? level.as<const char*>() : "";
        uint8_t found = 0;
        for (uint8_t i = 0; i < sizeof(kLevels) / sizeof(kLevels[0]); ++i) {
            if (strcmp(name, kLevels[i]) == 0) found = i + 1;
        }
        if (found) {
            s.logLevel = found;
        } else {
            t.refuse(kLogLevel);
        }
    }

    out.dark = doc["led"]["dark"] | false;
    JsonVariantConst id = doc["recalibrate"]["id"];
    JsonVariantConst ppm = doc["recalibrate"]["ppm"];
    if (id.is<uint32_t>() && id.as<uint32_t>() && ppm.is<int>() &&
        ppm.as<int>() >= kRecalibrateMinPpm && ppm.as<int>() <= kRecalibrateMaxPpm) {
        out.recalibrateId = id.as<uint32_t>();
        out.recalibratePpm = (uint16_t)ppm.as<int>();
    }
    return true;
}

size_t refusedJson(uint32_t refused, char* buf, size_t len) {
    size_t n = 0;
    int w = snprintf(buf, len, "[");
    if (w < 0 || (size_t)w >= len) return 0;
    n += (size_t)w;
    bool first = true;
    for (uint8_t key = 0; key < kSettingKeys; ++key) {
        if (!(refused & (1ul << key))) continue;
        w = snprintf(buf + n, len - n, "%s\"%s\"", first ? "" : ",", kKeyNames[key]);
        if (w < 0 || (size_t)w >= len - n) {
            buf[0] = '\0';
            return 0;
        }
        n += (size_t)w;
        first = false;
    }
    w = snprintf(buf + n, len - n, "]");
    if (w < 0 || (size_t)w >= len - n) {
        buf[0] = '\0';
        return 0;
    }
    return n + (size_t)w;
}
