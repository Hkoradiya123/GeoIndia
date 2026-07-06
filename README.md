# 🇮🇳 GeoIndia — LGD Codes Explorer

An interactive Streamlit web app for browsing India's **Local Government Directory (LGD)** codes — States, Districts, Sub-Districts, and Villages — sourced live from [lgdirectory.gov.in](https://lgdirectory.gov.in).

## Features

- **4 tabs** matching the official LGD website hierarchy
  - 🏛️ State / UTs
  - 📍 Districts (select a state)
  - 🗺️ Sub-Districts (select state → district)
  - 🌾 Villages — Search By Hierarchy (select state → district → sub-district)
- **Auto CAPTCHA solving** via `ddddocr` — no manual input needed
- **Search / filter** within any tab
- **Export** as CSV, Excel, or JSON; one-click Copy JSON

## Quick Start

```bash
pip install -r requirements.txt
streamlit run geoindia.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## How It Works

- States / Districts / Sub-Districts are fetched via the LGD site's **DWR (Direct Web Remoting)** API
- Villages are fetched by POSTing to `globalviewvillage.do` with `searchCriteriaType=LANDH`; the CAPTCHA is auto-solved using `ddddocr`

## Source

Data: [lgdirectory.gov.in](https://lgdirectory.gov.in) — Ministry of Panchayati Raj, Government of India
