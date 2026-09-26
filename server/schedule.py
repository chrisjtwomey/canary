"""canary's schedules when config.yaml gives none. epd_server.timeranges
holds how a day of time ranges works."""

# The dock syncs every half hour from 01:00 to 07:00, and every five
# minutes the rest of the day.
DEFAULT_DOCK_SYNC = [{"from": "01:00", "every": 1800}, {"from": "07:00", "every": 300}]
# The head syncs every half hour, beside each page it fetches.
DEFAULT_HEAD_SYNC_S = 1800
# A page an hour, all day.
DEFAULT_PAGE_RANGES = [{"from": "00:00", "every": 3600}]
