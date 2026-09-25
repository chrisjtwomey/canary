#pragma once

// How the splash screen's update bar follows the bytes written.
//
// Each step the bar gains is one partial update of the panel. There are ten,
// as the Inkplate library makes every eleventh partial update a full one.
struct ProgressBar {
    static constexpr int kSteps = 10;

    enum Push { NONE, FULL, PARTIAL };

    // The steps on the panel; -1 until the bar is drawn.
    int filled = -1;

    // What to push for done of total bytes, with filled set to the steps to
    // draw: the whole panel at the first call, then a partial update each time
    // the bar gains a step. A total of 0 is not known yet.
    Push update(int done, int total) {
        const int step = total <= 0 || done <= 0 ? 0
                         : done >= total         ? kSteps
                                                 : (int)((long long)done * kSteps / total);
        if (filled < 0) {
            filled = step;
            return FULL;
        }
        if (step <= filled) return NONE;
        filled = step;
        return PARTIAL;
    }
};
