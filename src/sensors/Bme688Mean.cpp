#include "sensors/Bme688Mean.h"

void Bme688Mean::add(const Bme688Data& cycle) {
    newest_ = cycle;
    ++cycles_;
    tempSum_ += cycle.tempC;
    pressureSum_ += cycle.pressureHpa;
    rhSum_ += cycle.rhPct;
    if (cycle.gasValid && cycle.heatStable) {
        gasSum_ += cycle.gasOhm;
        ++gasN_;
    }
    if (cycle.hasIaq && cycle.iaqAccuracy >= kCountedAccuracy) {
        iaqSum_ += cycle.iaq;
        iaqAccuracy_ = cycle.iaqAccuracy;
        ++iaqN_;
    }
    if (cycle.hasStaticIaq && cycle.staticIaqAccuracy >= kCountedAccuracy) {
        staticIaqSum_ += cycle.staticIaq;
        staticIaqAccuracy_ = cycle.staticIaqAccuracy;
        ++staticIaqN_;
    }
}

bool Bme688Mean::take(Bme688Data& mean, Bme688Data& newest, Bme688Samples& n) {
    if (!cycles_) return false;
    newest = newest_;
    mean = newest_;
    mean.tempC = (float)(tempSum_ / cycles_);
    mean.pressureHpa = (float)(pressureSum_ / cycles_);
    mean.rhPct = (float)(rhSum_ / cycles_);
    if (gasN_) {
        mean.gasOhm = (float)(gasSum_ / gasN_);
        mean.gasValid = mean.heatStable = true;
    }
    if (iaqN_) {
        mean.iaq = (float)(iaqSum_ / iaqN_);
        mean.iaqAccuracy = iaqAccuracy_;
        mean.hasIaq = true;
    }
    if (staticIaqN_) {
        mean.staticIaq = (float)(staticIaqSum_ / staticIaqN_);
        mean.staticIaqAccuracy = staticIaqAccuracy_;
        mean.hasStaticIaq = true;
    }
    n = {cycles_, iaqN_, staticIaqN_};
    *this = Bme688Mean();
    return true;
}
