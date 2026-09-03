#include "sensors/IPmsa003i.h"

// The 32-byte frame the sensor keeps updated, decoded. Shared by every
// driver: the wire format is the sensor's, not any one implementation's.
bool IPmsa003i::parseFrame(const uint8_t f[32], PmData& out) {
    if (f[0] != 0x42 || f[1] != 0x4D) return false;
    uint16_t len = (uint16_t)(f[2] << 8 | f[3]);
    if (len != 28) return false;
    uint16_t sum = 0;
    for (int i = 0; i < 30; ++i) sum += f[i];
    if (sum != (uint16_t)(f[30] << 8 | f[31])) return false;

    auto w = [&](int i) { return (uint16_t)(f[i] << 8 | f[i + 1]); };
    out.pm1_0Cf1 = w(4);  out.pm2_5Cf1 = w(6);  out.pm10Cf1 = w(8);
    out.pm1_0 = w(10);    out.pm2_5 = w(12);    out.pm10 = w(14);
    out.pc0_3 = w(16); out.pc0_5 = w(18); out.pc1_0 = w(20);
    out.pc2_5 = w(22); out.pc5_0 = w(24); out.pc10 = w(26);
    out.version = f[28];
    out.error = f[29];
    return true;
}
