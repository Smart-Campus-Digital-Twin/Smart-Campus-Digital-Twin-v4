// Flux continuous task: roll up 1-hour aggregations into daily summaries.
//
// Runs at 00:05 daily so the previous day's data is complete.
// Writes to bucket `campus_1d` with measurement `sensor_1d`.
//
// This task is optional — Spark DailyEnergyReportJob also produces
// daily summaries, but those go to PostgreSQL. This keeps a time-series
// copy in InfluxDB for Grafana long-range charts.

option task = {
    name:   "downsample_1h_to_1d",
    every:  1d,
    offset: 5m,   // run at 00:05 so the 00:00 hourly window is complete
}

from(bucket: "campus_1h")
    |> range(start: -1d)
    |> filter(fn: (r) => r._measurement =~ /^sensor_1h_/)
    |> filter(fn: (r) =>
        r._field == "avg" or
        r._field == "min" or
        r._field == "max" or
        r._field == "count"
    )
    |> aggregateWindow(
        every:        1d,
        fn:           mean,     // daily mean of hourly means
        createEmpty:  false,
    )
    // Keep daily MAX for peak-demand tracking
    |> map(fn: (r) => ({r with _measurement: "sensor_1d"}))
    |> to(
        bucket: "campus_1d",
        tagColumns: ["building_id", "floor", "room_id", "sensor_type"],
    )
