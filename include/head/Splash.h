#pragma once

// The logo, which the head draws itself: from its firmware, so it needs no
// network. It is drawn in black and white, which partial updates need.

// Draw the logo alone. It stays until a page or a notice replaces it.
void showSplash();

// Before takeOfferedUpdate(): the version the line under the bar names, and
// an empty bar.
void beginUpdateProgress(const char* version);

// Draw the logo with a bar under it filled to done of total bytes, and under
// that a line naming the version, for takeOfferedUpdate()'s progress hook.
// The first call draws the whole panel; the bar then fills by partial updates.
void showUpdateProgress(int done, int total);

// The update did not happen, so the next draw is in greys. The logo and the
// bar stay until a page replaces them.
void endUpdateProgress();
