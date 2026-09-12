#if !defined(NATIVE)
#include "sensors/BsecLibrary.h"

#include <cstring>

#include "bsec_datatypes.h"
#include "bsec_interface_multi.h"

namespace {

// Bosch's configuration for a BME688 on 3.3 V in LP mode, with a four-day
// calibration window, compiled in the way Bosch's own examples do it.
const uint8_t kConfig[] = {
#include "bme688/bme688_sel_33v_3s_4d/bsec_selectivity.txt"
};

// What Bosch's wrapper sets aside for an instance; init() checks that the
// binary agrees.
const size_t kInstanceBytes = 3272;
const int    kInstanceTooSmall = -105;   // the wrapper's BSEC_E_INSUFFICIENT_INSTANCE_SIZE
uint8_t instance[kInstanceBytes];
uint8_t work[BSEC_MAX_WORKBUFFER_SIZE];

const uint8_t kOutputs[] = {
    BSEC_OUTPUT_IAQ,
    BSEC_OUTPUT_STATIC_IAQ,
    BSEC_OUTPUT_CO2_EQUIVALENT,
    BSEC_OUTPUT_BREATH_VOC_EQUIVALENT,
    BSEC_OUTPUT_STABILIZATION_STATUS,
    BSEC_OUTPUT_RUN_IN_STATUS,
};
const uint8_t kOutputCount = sizeof(kOutputs) / sizeof(kOutputs[0]);

const uint8_t kForcedMode = 1;   // BME68X_FORCED_MODE

bool wanted(uint32_t processData, uint8_t input) {
    return (processData & (1u << (input - 1))) != 0;
}

}  // namespace

int BsecLibrary::init() {
    if (bsec_get_instance_size_m() > kInstanceBytes) return kInstanceTooSmall;
    processData_ = 0;
    int status = bsec_init_m(instance);
    if (status != BSEC_OK) return status;
    return bsec_set_configuration_m(instance, kConfig, sizeof(kConfig), work, sizeof(work));
}

int BsecLibrary::setState(const uint8_t* state, uint32_t len) {
    return bsec_set_state_m(instance, state, len, work, sizeof(work));
}

int BsecLibrary::getState(uint8_t* state, uint32_t max, uint32_t* len) {
    return bsec_get_state_m(instance, 0, state, max, work, sizeof(work), len);
}

int BsecLibrary::subscribe() {
    bsec_sensor_configuration_t requested[kOutputCount];
    for (uint8_t i = 0; i < kOutputCount; ++i) {
        requested[i].sensor_id = kOutputs[i];
        requested[i].sample_rate = BSEC_SAMPLE_RATE_LP;
    }
    bsec_sensor_configuration_t required[BSEC_MAX_PHYSICAL_SENSOR];
    uint8_t nRequired = BSEC_MAX_PHYSICAL_SENSOR;
    return bsec_update_subscription_m(instance, requested, kOutputCount, required, &nRequired);
}

int BsecLibrary::sensorControl(int64_t nowNs, BsecRequest& request) {
    bsec_bme_settings_t settings;
    memset(&settings, 0, sizeof(settings));
    const int status = bsec_sensor_control_m(instance, nowNs, &settings);
    processData_ = settings.process_data;
    request.nextCallNs = settings.next_call;
    request.measure = settings.trigger_measurement && settings.op_mode == kForcedMode;
    request.heaterC = settings.heater_temperature;
    request.heaterMs = settings.heater_duration;
    request.osT = settings.temperature_oversampling;
    request.osP = settings.pressure_oversampling;
    request.osH = settings.humidity_oversampling;
    request.runGas = settings.run_gas != 0;
    return status;
}

int BsecLibrary::doSteps(int64_t nowNs, const Bme688Data& data, BsecResult& result) {
    bsec_input_t inputs[BSEC_MAX_PHYSICAL_SENSOR];
    uint8_t n = 0;
    auto add = [&](uint8_t input, float signal) {
        if (!wanted(processData_, input) || n >= BSEC_MAX_PHYSICAL_SENSOR) return;
        inputs[n].time_stamp = nowNs;
        inputs[n].signal = signal;
        inputs[n].signal_dimensions = 1;
        inputs[n].sensor_id = input;
        ++n;
    };
    add(BSEC_INPUT_HEATSOURCE, 0.0f);
    add(BSEC_INPUT_TEMPERATURE, data.tempC);
    add(BSEC_INPUT_HUMIDITY, data.rhPct);
    // hPa. BSEC's header says Pa, but Bosch's own BSEC2 wrapper converts the
    // sensor's Pa to hPa before handing it over, and this follows the wrapper.
    add(BSEC_INPUT_PRESSURE, data.pressureHpa);
    add(BSEC_INPUT_GASRESISTOR, data.gasOhm);
    add(BSEC_INPUT_PROFILE_PART, 0.0f);   // a forced cycle is one heater step
    result.hasIaq = false;
    if (n == 0) return BSEC_OK;

    bsec_output_t outputs[BSEC_NUMBER_OUTPUTS];
    uint8_t nOutputs = BSEC_NUMBER_OUTPUTS;
    const int status = bsec_do_steps_m(instance, inputs, n, outputs, &nOutputs);
    if (status < BSEC_OK) return status;
    for (uint8_t i = 0; i < nOutputs; ++i) {
        if (outputs[i].sensor_id != BSEC_OUTPUT_IAQ) continue;
        result.hasIaq = true;
        result.iaq = outputs[i].signal;
        result.iaqAccuracy = outputs[i].accuracy;
    }
    return status;
}
#endif
