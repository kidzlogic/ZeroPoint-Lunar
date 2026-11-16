# Zero-Point Lunar — 3-minute speech script

**Before you start:** open the app. It opens on **Sites & Dates**. Leave that board up.  
Challenge title to say out loud: **CLPS Lunar Mission Browser**.

---

## Full pitch (~2:30 speaking + 30s buffer)

### 1. Problem — 20 seconds

A south-pole landing can fail on the calendar. The Sun has to clear the local ridge or the arrays go dark, and Earth has to clear that same ridge or direct-to-Earth radio drops. Those two windows move with the date. Crews should see that before they pick a site.

### 2. What we built — 15 seconds

We built **Zero-Point Lunar** for the CLPS Lunar Mission Browser challenge. One date ranks seven south-pole regions by hours the Sun and Earth sit above the local LOLA ridge. That is the power window and the direct-to-Earth window, on the same board.

### 3. Live demo — 60–75 seconds *(click while you talk)*

*[Point at the headline]*  
This fortnight, the board names a leader: hours of Sun above the ridge, hours of Earth above it. Gold on the chart is the Sun. Cyan is Earth. The dashed line is the ridge in that direction. Above the dash, that sky is clear.

*[Click a lower-ranked site, then its “Better fortnight” line if it is there]*  
Same crater, different date. Malapert or Faustini can lose the Sun this month and recover it later in the year. The date is part of the site.

*[Click **Walk this site**]*  
The winning shoulder opens on the path board. Slope, shelter, and the walk are the next question. We do **not** claim ice detection or flight clearance. LDEM 16 is about 2 km per pixel, and the Sun and Earth directions are about 1°.

### 4. Why it matters — 20 seconds

Zero-Point Lunar turns open NASA terrain and space-weather data into a clear planning loop for students, educators, and early concept planners. Slope, power, communications, dust stand-off, and storm shelter — coupled, visible, honest about LDEM 16 resolution of roughly 3 km cells.

### 5. Close — 10 seconds

One date, seven regions, two windows: Sun for power, Earth for radio, both above the real ridge. Thank you. Questions?

---

## Ultra-short version (60 seconds)

South-pole landings fail when the Sun or Earth sits behind a ridge, and that changes with the date. Zero-Point Lunar ranks seven regions for the fortnight you pick: Sun hours for power, Earth hours for direct-to-Earth radio, on LOLA terrain. *[Point at the headline, then a site with a better fortnight.]* Planning support, about 1° on the sky and 2 km on the ground, not a landing clearance. Thank you.

---

## Judge-criteria lines *(use if asked)*

| Criterion | One line |
|-----------|----------|
| **Impact** | A bad date or a blocked ridge shows up before anyone commits a lander. |
| **Creativity** | Site and date on one board: Sun, Earth, and the local ridge, not three separate tools. |
| **Validity** | Meeus optical libration plus LOLA LDEM 16, with the error stated on the board. |
| **Relevance** | Built for CLPS Lunar Mission Browser — compare sites and dates for power and direct-to-Earth windows. |
| **Presentation** | Read the headline, open one weaker site, jump to its better fortnight. |

---

## Demo checklist

1. `python lunar_web_app.py` → http://127.0.0.1:5000 — **Sites & Dates** is already open  
2. Read the headline out loud  
3. Click a lower site, then **Better fortnight** if it appears  
4. **Walk this site** only if they ask what happens after you pick  
5. If judges ask “is it safe?” → “Planning only. About 1° on the Sun and Earth, about 2 km on LOLA. Not flight software.”
