#pragma once

// A message the head draws itself, for when it cannot show a page.
//
// It comes from the firmware rather than the server, so it still works when
// the server is what is wrong. Each notice is drawn once: asking for the one
// already on the panel leaves the panel alone, since every draw is a full
// e-paper refresh.

// This display and the server run versions that cannot work together.
// offered says whether the server offered an image this display will take;
// without one the notice asks for firmware instead of waiting for it.
bool showVersionNotice(const char* ownVersion, const char* serverVersion, bool offered);

// The server has not answered for a while. lastPage is when the last page
// arrived, in RFC 3339, or empty when none has arrived since the head started.
bool showUnreachableNotice(const char* lastPage);

// A page is on the panel, so the next notice has to be drawn in full.
void noticeReplaced();
