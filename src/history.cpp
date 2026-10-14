#include "history.h"

#include <Arduino.h>

#include <string.h>

namespace {

struct SeriesData {
    float v[History::SAMPLES];
    int   head;   /* on s'escriura la propera mostra */
    int   n;      /* quantes mostres valides hi ha */
};

SeriesData gData[History::SERIES_COUNT];

const char* const kNames[History::SERIES_COUNT] = {
    "CPU", "RAM", "DISC", "BAT", "LOAD", "XARXA"
};

/* Noms dels gadgets que tenen grafic. */
const char* const kWidgets[History::SERIES_COUNT] = {
    "cpu", "mem", "disk", "bat", "load", "net"
};

}  // namespace

namespace History {

void begin()
{
    memset(gData, 0, sizeof(gData));
}

void push(const MacLink::Stats& s)
{
    if (!s.valid) {
        return;
    }
    const float vals[SERIES_COUNT] = {
        s.cpu, s.mem, s.disk, s.bat, s.load, s.up + s.dn
    };
    for (int i = 0; i < SERIES_COUNT; ++i) {
        SeriesData& d = gData[i];
        d.v[d.head] = vals[i];
        d.head = (d.head + 1) % SAMPLES;
        if (d.n < SAMPLES) {
            ++d.n;
        }
    }
}

int seriesFor(const char* widgetId)
{
    if (widgetId == nullptr) {
        return -1;
    }
    for (int i = 0; i < SERIES_COUNT; ++i) {
        if (strcmp(widgetId, kWidgets[i]) == 0) {
            return i;
        }
    }
    return -1;
}

const char* name(int series)
{
    return (series >= 0 && series < SERIES_COUNT) ? kNames[series] : "?";
}

bool isPercent(int series)
{
    return series == CPU || series == MEM || series == DISK || series == BAT;
}

int count(int series)
{
    if (series < 0 || series >= SERIES_COUNT) {
        return 0;
    }
    return gData[series].n;
}

float value(int series, int i)
{
    if (series < 0 || series >= SERIES_COUNT) {
        return 0.0f;
    }
    const SeriesData& d = gData[series];
    if (i < 0 || i >= d.n) {
        return 0.0f;
    }
    /* Si encara no hem donat la volta, les dades comencen a la posicio 0. */
    const int start = (d.n < SAMPLES) ? 0 : d.head;
    return d.v[(start + i) % SAMPLES];
}

float minValue(int series)
{
    const int n = count(series);
    if (n == 0) {
        return 0.0f;
    }
    float m = value(series, 0);
    for (int i = 1; i < n; ++i) {
        const float v = value(series, i);
        if (v < m) {
            m = v;
        }
    }
    return m;
}

float maxValue(int series)
{
    const int n = count(series);
    if (n == 0) {
        return 0.0f;
    }
    float m = value(series, 0);
    for (int i = 1; i < n; ++i) {
        const float v = value(series, i);
        if (v > m) {
            m = v;
        }
    }
    return m;
}

float avgValue(int series)
{
    const int n = count(series);
    if (n == 0) {
        return 0.0f;
    }
    float sum = 0.0f;
    for (int i = 0; i < n; ++i) {
        sum += value(series, i);
    }
    return sum / static_cast<float>(n);
}

float lastValue(int series)
{
    const int n = count(series);
    return (n == 0) ? 0.0f : value(series, n - 1);
}

}  // namespace History
