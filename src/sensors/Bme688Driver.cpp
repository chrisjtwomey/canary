#include "sensors/Bme688Driver.h"

// bme68x_set_regs interleaves register addresses with their values and hands
// the first address over separately, so a write is never longer than this.
static const uint32_t kMaxWriteLen = BME68X_LEN_INTERLEAVE_BUFF;

int8_t Bme688Driver::busRead(uint8_t reg, uint8_t* data, uint32_t len, void* intfPtr) {
    Bme688Driver* self = static_cast<Bme688Driver*>(intfPtr);
    return self->bus_.writeRead(self->addr_, &reg, 1, data, len) ? BME68X_INTF_RET_SUCCESS
                                                                 : (int8_t)-1;
}

int8_t Bme688Driver::busWrite(uint8_t reg, const uint8_t* data, uint32_t len, void* intfPtr) {
    Bme688Driver* self = static_cast<Bme688Driver*>(intfPtr);
    if (len + 1 > kMaxWriteLen) return -1;
    uint8_t tx[kMaxWriteLen];
    tx[0] = reg;
    for (uint32_t i = 0; i < len; ++i) tx[i + 1] = data[i];
    return self->bus_.write(self->addr_, tx, len + 1) ? BME68X_INTF_RET_SUCCESS : (int8_t)-1;
}

void Bme688Driver::busDelayUs(uint32_t us, void* intfPtr) {
    Bme688Driver* self = static_cast<Bme688Driver*>(intfPtr);
    self->clock_.waitMs((us + 999) / 1000);
}

// Bosch's oversampling codes count the doublings: 1x is 1, 2x is 2, 16x is 5.
uint8_t Bme688Driver::oversamplingCode(uint8_t multiplier) {
    switch (multiplier) {
        case 0:  return BME68X_OS_NONE;
        case 1:  return BME68X_OS_1X;
        case 2:  return BME68X_OS_2X;
        case 4:  return BME68X_OS_4X;
        case 8:  return BME68X_OS_8X;
        case 16: return BME68X_OS_16X;
        default: return BME68X_OS_1X;
    }
}

bool Bme688Driver::begin(uint32_t nowMs) {
    (void)nowMs;
    ready_ = false;
    configured_ = false;
    running_ = false;

    dev_ = bme68x_dev();
    dev_.intf = BME68X_I2C_INTF;
    dev_.intf_ptr = this;
    dev_.read = &Bme688Driver::busRead;
    dev_.write = &Bme688Driver::busWrite;
    dev_.delay_us = &Bme688Driver::busDelayUs;
    dev_.amb_temp = kAmbientC;

    if (bme68x_init(&dev_) != BME68X_OK) return false;
    if (dev_.chip_id != kChipId) return false;
    // A BME680 answers the same chip ID; only the variant separates it from a
    // BME688, and a BME680 has no gas-scanner heater profile behind it.
    if (dev_.variant_id != BME68X_VARIANT_GAS_HIGH) return false;

    ready_ = true;
    return applyConfig();
}

void Bme688Driver::setOversampling(uint8_t osT, uint8_t osP, uint8_t osH) {
    osT_ = osT; osP_ = osP; osH_ = osH;
    applyConfig();
}

void Bme688Driver::setHeaterProfile(uint16_t degC, uint16_t ms) {
    heaterC_ = degC; heaterMs_ = ms;
    applyConfig();
}

bool Bme688Driver::applyConfig() {
    if (!ready_) return false;
    configured_ = false;

    conf_.os_temp = oversamplingCode(osT_);
    conf_.os_pres = oversamplingCode(osP_);
    conf_.os_hum  = oversamplingCode(osH_);
    conf_.filter  = BME68X_FILTER_OFF;
    conf_.odr     = BME68X_ODR_NONE;
    if (bme68x_set_conf(&conf_, &dev_) != BME68X_OK) return false;

    struct bme68x_heatr_conf heater = bme68x_heatr_conf();
    heater.enable = BME68X_ENABLE;
    heater.heatr_temp = heaterC_;
    heater.heatr_dur = heaterMs_;
    if (bme68x_set_heatr_conf(BME68X_FORCED_MODE, &heater, &dev_) != BME68X_OK) return false;

    // Bosch reports the conversion in microseconds and leaves the heater out
    // of it, because in forced mode the two run one after the other.
    uint32_t tphUs = bme68x_get_meas_dur(BME68X_FORCED_MODE, &conf_, &dev_);
    measurementMs_ = (tphUs + 999) / 1000 + heaterMs_;
    configured_ = true;
    return true;
}

bool Bme688Driver::startForced(uint32_t nowMs) {
    if (!configured_) return false;
    if (running_ && nowMs < doneAtMs_) return false;
    if (bme68x_set_op_mode(BME68X_FORCED_MODE, &dev_) != BME68X_OK) return false;
    running_ = true;
    doneAtMs_ = nowMs + measurementMs_;
    return true;
}

bool Bme688Driver::fetchData(uint32_t nowMs, Bme688Data& out) {
    if (!running_ || nowMs < doneAtMs_) return false;
    running_ = false;

    struct bme68x_data data = bme68x_data();
    uint8_t fields = 0;
    if (bme68x_get_data(BME68X_FORCED_MODE, &data, &fields, &dev_) != BME68X_OK) return false;
    if (fields == 0) return false;

    out.tempC = data.temperature;
    out.pressureHpa = data.pressure / 100.0f;
    out.rhPct = data.humidity;
    out.gasOhm = data.gas_resistance;
    out.gasValid = (data.status & BME68X_GASM_VALID_MSK) != 0;
    out.heatStable = (data.status & BME68X_HEAT_STAB_MSK) != 0;
    out.iaq = 0.0f;
    out.iaqAccuracy = 0;
    out.hasIaq = false;
    return true;
}
