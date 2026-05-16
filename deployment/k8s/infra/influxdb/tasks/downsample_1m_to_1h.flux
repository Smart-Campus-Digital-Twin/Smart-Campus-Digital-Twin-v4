// Flux continuous task: roll up 1-minute aggregations into hourly summaries.
//
// Runs at hh:05 every hour so the previous hour's data is complete.
// Writes to bucket `campus_1h` with measurement `sensor_1h_<type>`.
//
// Implemented natively in InfluxDB Flux (no external scheduler required).

option task = {
    name:   "downsample_1m_to_1h",
    every:  1h,
    offset: 5m,   // run at hh:05 so the hh:00 window is complete
}

from(bucket: "campus_1m")
    |> range(start: -1h)
    |> filter(fn: (r) => r._measurement =~ /^sensor_1m_/)
    |> filter(fn: (r) =>
        r._field == "avg" or
        r._field == "min" or
        r._field == "max" or
        r._field == "sum" or
        r._field == "count" or
        r._field == "quality"
    )
    |> aggregateWindow(
        every:        1h,
        fn:           mean,     // hourly mean of 1-min aggregations
        createEmpty:  false,
    )
    // Preserve sensor_type in measurement name: sensor_1m_temperature → sensor_1h_temperature
    |> map(fn: (r) => ({
        r with _measurement: 
            if r._measurement =~ /^sensor_1m_/ then
                "sensor_1h_" + strings.substring(v: r._measurement, start: 10, end: strings.strlen(v: r._measurement))
            else
                "sensor_1h"
    }))
    |> to(
        bucket: "campus_1h",
        tagColumns: ["building_id", "floor", "room_id", "sensor_type"],
    )
