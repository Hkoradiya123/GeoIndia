"""
Interactive Streamlit app — India LGD Codes
4 tabs matching the official LGD website hierarchy:
  1. LGD Codes of State/UTs
  2. LGD Codes of Districts          (State → Districts)
  3. LGD Codes of Sub-Districts      (State → District → Sub-Districts)
  4. LGD Codes of Villages           (State → District → Sub-District → Villages)
Source: https://lgdirectory.gov.in
"""

import http.cookiejar
import io
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

LGD_BASE = "https://lgdirectory.gov.in"


# ─── HTTP / DWR core ────────────────────────────────────────────────────────

def _new_opener():
    ctx = ssl.create_default_context()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(jar),
    )
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"),
        ("Accept", "text/html,*/*"),
    ]
    return opener, jar


def _get_session(page_path: str):
    opener, jar = _new_opener()
    with opener.open(f"{LGD_BASE}{page_path}", timeout=15) as r:
        r.read()
    jsid = next((c.value for c in jar if c.name == "JSESSIONID"), None)
    if not jsid:
        raise RuntimeError(f"No JSESSIONID from {page_path}")
    return opener, jsid


def _dwr(opener, jsid, script, method, param_type, param_val, page_path):
    body = (
        f"callCount=1\nnextReverseAjaxIndex=0\n"
        f"c0-scriptName={script}\nc0-methodName={method}\n"
        f"c0-id=0\nc0-param0={param_type}:{param_val}\n"
        f"batchId=1\ninstanceId=0\n"
        f"page={urllib.parse.quote(page_path)}\n"
        f"httpSessionId={jsid}\nscriptSessionId={jsid}00\n"
    )
    req = urllib.request.Request(
        f"{LGD_BASE}/dwr/call/plaincall/{script}.{method}.dwr",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "text/plain",
            "Origin": LGD_BASE,
            "Referer": f"{LGD_BASE}{page_path}",
        },
    )
    with opener.open(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


# ─── Data fetchers (cached) ──────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def fetch_states():
    """List of (lgd_code_str, state_name) sorted by name."""
    opener, jar = _new_opener()
    opener.addheaders = [("User-Agent", "Mozilla/5.0"), ("Accept", "text/html,*/*")]
    with opener.open(f"{LGD_BASE}/districtWiseDetailReport.do", timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")
    opts = re.findall(r'<option[^>]*value=["\'](\d+)["\'][^>]*>(.*?)</option>', html, re.I)
    return sorted([(c.strip(), n.strip()) for c, n in opts if c.strip()], key=lambda x: x[1])


@st.cache_data(show_spinner=False)
def fetch_districts(state_code: str):
    """List of (district_code_str, district_name) for a state, sorted by name."""
    opener, jsid = _get_session("/districtWiseDetailReport.do")
    resp = _dwr(opener, jsid,
                "lgdDwrDistrictService", "getDistrictList",
                "number", state_code, "/districtWiseDetailReport.do")
    codes = re.findall(r'districtCode:(\d+)', resp)
    names = re.findall(r'districtNameEnglish:"(.*?)"', resp)
    return sorted(zip(codes, names), key=lambda x: x[1])


@st.cache_data(show_spinner=False)
def fetch_subdistricts_by_state(state_code: str):
    """All sub-districts for a state (state-level, no district grouping)."""
    opener, jsid = _get_session("/globalviewsubdistrictforcitizen.do")
    resp = _dwr(opener, jsid,
                "lgdDwrSubDistrictService", "getSubdistrictList",
                "number", state_code, "/globalviewsubdistrictforcitizen.do")
    codes = re.findall(r'subdistrictCode:(\d+)', resp)
    names = re.findall(r'subdistrictNameEnglish:"(.*?)"', resp)
    return sorted(zip(codes, names), key=lambda x: x[1])


@st.cache_data(show_spinner=False)
def fetch_subdistricts_by_district(district_code: str):
    """Sub-districts for a specific district (hierarchy fetch)."""
    opener, jsid = _get_session("/globalviewvillageforcitizen.do")
    resp = _dwr(opener, jsid,
                "lgdDwrSubDistrictService", "getSubDistListbyDistCodeShift",
                "number", district_code, "/globalviewvillageforcitizen.do")
    codes = re.findall(r'subdistrictCode:(\d+)', resp)
    names = re.findall(r'subdistrictNameEnglish:"(.*?)"', resp)
    return sorted(zip(codes, names), key=lambda x: x[1])


def fetch_villages_auto(state_code: str, district_code: str,
                        subdistrict_code: str = "", max_tries: int = 6):
    """Auto-solve CAPTCHA via ddddocr and POST to globalviewvillage.do."""
    import ddddocr
    ocr = ddddocr.DdddOcr(show_ad=False)

    for attempt in range(max_tries):
        opener, jar = _new_opener()
        opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"),
            ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            ("Connection", "keep-alive"),
        ]
        with opener.open(f"{LGD_BASE}/globalviewvillageforcitizen.do", timeout=20) as r:
            page_html = r.read().decode("utf-8", "replace")
        jsid = next((c.value for c in jar if c.name == "JSESSIONID"), None)
        csrf_m = re.search(r'OWASP_CSRFTOKEN[^>]*value="([^"]+)"', page_html)
        csrf = csrf_m.group(1) if csrf_m else ""

        time.sleep(0.3)
        with opener.open(f"{LGD_BASE}/captchaImage", timeout=10) as r:
            cap_bytes = r.read()
        captcha_text = ocr.classification(cap_bytes).upper()

        post_data = urllib.parse.urlencode({
            "OWASP_CSRFTOKEN": csrf,
            "searchCriteriaType": "LANDH",
            "paramEntityCode": "",
            "paramEntityName": "",
            "paramStateCode": state_code,
            "paramDistrictCode": district_code,
            "paramSubDistrictCode": subdistrict_code,
            "captchaAnswer": captcha_text,
            "entitesForMessage": "",
            "stateCode": "",
            "lbTypeHierarchy": "",
            "lgd_LBTypeName": "",
            "localBody": "",
        }).encode()
        req = urllib.request.Request(
            f"{LGD_BASE}/globalviewvillage.do",
            data=post_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{LGD_BASE}/globalviewvillageforcitizen.do",
                "Origin": LGD_BASE,
                "Cookie": f"JSESSIONID={jsid}",
            },
        )
        with opener.open(req, timeout=60) as r:
            resp = r.read().decode("utf-8", "replace")

        if "incorrectly" in resp:
            time.sleep(0.5)
            continue

        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', resp, re.DOTALL | re.I)
        villages = []
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.I)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c for c in cells if c]
            if len(cells) >= 3 and cells[0].isdigit():
                lgd_code  = cells[1] if len(cells) > 1 else ""
                name_en   = cells[2] if len(cells) > 2 else ""
                name_lo   = cells[3] if len(cells) > 3 else ""
                hierarchy = cells[4] if len(cells) > 4 else ""
                sd_m = re.search(r'^(.*?)\(Sub-District\)', hierarchy)
                sub_dist  = sd_m.group(1).strip() if sd_m else ""
                villages.append({
                    "LGD Village Code": lgd_code,
                    "Village Name": name_en,
                    "Village Name (Local)": name_lo,
                    "Sub-District": sub_dist,
                })
        return villages

    raise RuntimeError(f"CAPTCHA failed after {max_tries} attempts. Please try again.")


# ─── Export helpers ──────────────────────────────────────────────────────────

def _to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="LGD")
    return buf.getvalue()


def _to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def export_bar(df: pd.DataFrame, key: str):
    json_str = df.to_json(orient="records", indent=2, force_ascii=False)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("⬇️ Download CSV", _to_csv(df),
                           file_name=f"lgd_{key}.csv", mime="text/csv",
                           use_container_width=True, key=f"csv_{key}")
    with c2:
        try:
            st.download_button("⬇️ Download Excel", _to_excel(df),
                               file_name=f"lgd_{key}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True, key=f"xl_{key}")
        except Exception:
            st.info("Install `openpyxl` for Excel export.")
    with c3:
        st.download_button("⬇️ Download JSON", json_str.encode("utf-8"),
                           file_name=f"lgd_{key}.json", mime="application/json",
                           use_container_width=True, key=f"js_{key}")
    with c4:
        components.html(f"""
        <script>
        function copy_{key}() {{
            navigator.clipboard.writeText({json.dumps(json_str)}).then(function() {{
                var el = document.getElementById('cp_{key}');
                el.innerText = '✅ Copied!';
                setTimeout(function(){{ el.innerText = ''; }}, 2000);
            }});
        }}
        </script>
        <button onclick="copy_{key}()" style="width:100%;padding:8px 0;border-radius:6px;
            background:#0068c9;color:#fff;border:none;font-size:14px;cursor:pointer;font-weight:500;">
            📋 Copy JSON
        </button>
        <div id="cp_{key}" style="color:green;font-size:13px;text-align:center;margin-top:4px;"></div>
        """, height=64)


# ─── Page setup ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="GeoIndia", page_icon="🇮🇳", layout="wide")

st.markdown("""
<style>
.stTabs [data-baseweb="tab"] { font-size: 15px; font-weight: 600; }
.metric-box { background:#f0f2f6; border-radius:8px; padding:12px 16px; }
</style>
""", unsafe_allow_html=True)

st.title("🇮🇳  GeoIndia — Local Government Directory (LGD) Codes")
st.caption("Source: [lgdirectory.gov.in](https://lgdirectory.gov.in) · Ministry of Panchayati Raj, Government of India")
st.divider()

# Load state list once (needed by all tabs)
try:
    ALL_STATES = fetch_states()           # [(code, name), ...]
    STATE_NAME_TO_CODE = {n: c for c, n in ALL_STATES}
    STATE_NAMES = sorted(STATE_NAME_TO_CODE)
except Exception as _e:
    ALL_STATES = []
    STATE_NAME_TO_CODE = {}
    STATE_NAMES = []
    st.error(f"Could not reach LGD portal: {_e}")

TAB_ST, TAB_DI, TAB_SD, TAB_VG = st.tabs([
    "🏛️  State / UTs",
    "📍  Districts",
    "🗺️  Sub-Districts",
    "🌾  Villages — Search By Hierarchy",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — States / UTs
# ═══════════════════════════════════════════════════════════════════════════════
with TAB_ST:
    st.subheader("LGD Codes of State / UTs")
    if st.button("🔄 Refresh", key="ref_states"):
        fetch_states.clear()
        st.rerun()

    if ALL_STATES:
        df_st = pd.DataFrame(ALL_STATES, columns=["LGD Code", "State / UT"])
        df_st["S.No."] = range(1, len(df_st) + 1)
        df_st = df_st[["S.No.", "LGD Code", "State / UT"]]

        q = st.text_input("🔍 Search", key="q_st", placeholder="e.g. Gujarat")
        if q:
            df_st = df_st[df_st["State / UT"].str.contains(q, case=False, na=False)]

        st.metric("Total States / UTs", len(df_st))
        st.dataframe(df_st.set_index("S.No."), use_container_width=True, height=500)
        st.divider()
        st.subheader("📤 Export")
        export_bar(df_st.reset_index(drop=True), "states")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Districts
# ═══════════════════════════════════════════════════════════════════════════════
with TAB_DI:
    st.subheader("LGD Codes of Districts")

    sel_st_d = st.selectbox("Select State / UT",
                            ["— select state —"] + STATE_NAMES, key="st_d")
    if sel_st_d != "— select state —":
        with st.spinner(f"Loading districts for {sel_st_d}…"):
            try:
                dists = fetch_districts(STATE_NAME_TO_CODE[sel_st_d])
            except Exception as e:
                st.error(str(e)); dists = []

        if dists:
            df_d = pd.DataFrame(dists, columns=["LGD District Code", "District Name"])
            df_d.insert(0, "State / UT", sel_st_d)
            df_d["S.No."] = range(1, len(df_d) + 1)
            df_d = df_d[["S.No.", "State / UT", "LGD District Code", "District Name"]]

            q_d = st.text_input("🔍 Search district", key="q_d", placeholder="e.g. Pune")
            if q_d:
                df_d = df_d[df_d["District Name"].str.contains(q_d, case=False, na=False)]

            st.metric("Districts", len(df_d))
            st.dataframe(df_d.set_index("S.No."), use_container_width=True, height=480)
            st.divider()
            st.subheader("📤 Export")
            export_bar(df_d.reset_index(drop=True), "districts")
        else:
            st.info("No districts found.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Sub-Districts  (State → District → Sub-Districts)
# ═══════════════════════════════════════════════════════════════════════════════
with TAB_SD:
    st.subheader("LGD Codes of Sub-Districts")

    sel_st_sd = st.selectbox("Select State / UT",
                             ["— select state —"] + STATE_NAMES, key="st_sd")

    sel_di_sd = "— select district —"
    dists_sd = []

    if sel_st_sd != "— select state —":
        with st.spinner(f"Loading districts for {sel_st_sd}…"):
            try:
                dists_sd = fetch_districts(STATE_NAME_TO_CODE[sel_st_sd])
            except Exception as e:
                st.error(str(e))

        if dists_sd:
            dist_map_sd = {n: c for c, n in dists_sd}
            sel_di_sd = st.selectbox(
                "Select District",
                ["— select district —"] + [n for _, n in dists_sd],
                key="di_sd",
            )

    if sel_di_sd != "— select district —":
        with st.spinner(f"Loading sub-districts for {sel_di_sd}…"):
            try:
                subdists = fetch_subdistricts_by_district(dist_map_sd[sel_di_sd])
            except Exception as e:
                st.error(str(e)); subdists = []

        if subdists:
            df_sd = pd.DataFrame(subdists, columns=["LGD Sub-District Code", "Sub-District Name"])
            df_sd.insert(0, "District", sel_di_sd)
            df_sd.insert(0, "State / UT", sel_st_sd)
            df_sd["S.No."] = range(1, len(df_sd) + 1)
            df_sd = df_sd[["S.No.", "State / UT", "District",
                           "LGD Sub-District Code", "Sub-District Name"]]

            q_sd = st.text_input("🔍 Search sub-district", key="q_sd", placeholder="e.g. Anjar")
            if q_sd:
                df_sd = df_sd[df_sd["Sub-District Name"].str.contains(q_sd, case=False, na=False)]

            st.metric("Sub-Districts", len(df_sd))
            st.dataframe(df_sd.set_index("S.No."), use_container_width=True, height=480)
            st.divider()
            st.subheader("📤 Export")
            export_bar(df_sd.reset_index(drop=True), "subdistricts")
        else:
            st.info("No sub-districts found.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Villages  (State → District → Sub-District → Villages)
# ═══════════════════════════════════════════════════════════════════════════════
with TAB_VG:
    st.subheader("LGD Codes of Villages — Search By Hierarchy")

    # session state init
    for _k, _v in {"vg_df": None, "vg_result_key": None}.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    col_st, col_di, col_sd = st.columns(3)

    with col_st:
        sel_st_v = st.selectbox(
            "Select State *",
            ["----------Select----------"] + STATE_NAMES,
            key="st_v",
        )

    dists_v, dist_map_v = [], {}
    if sel_st_v != "----------Select----------":
        with st.spinner(""):
            try:
                dists_v = fetch_districts(STATE_NAME_TO_CODE[sel_st_v])
                dist_map_v = {n: c for c, n in dists_v}
            except Exception as e:
                st.error(str(e))

    with col_di:
        sel_di_v = st.selectbox(
            "Select District *",
            ["----------Select----------"] + [n for _, n in dists_v],
            key="di_v",
            disabled=(not dists_v),
        )

    subdists_v, sdist_map_v = [], {}
    if sel_di_v != "----------Select----------" and sel_di_v in dist_map_v:
        with st.spinner(""):
            try:
                subdists_v = fetch_subdistricts_by_district(dist_map_v[sel_di_v])
                sdist_map_v = {n: c for c, n in subdists_v}
            except Exception as e:
                st.error(str(e))

    with col_sd:
        sel_sd_v = st.selectbox(
            "Select Sub-District *",
            ["All"] + [n for _, n in subdists_v],
            key="sd_v",
            disabled=(not subdists_v),
        )

    _state_code = STATE_NAME_TO_CODE.get(sel_st_v, "")
    _dist_code  = dist_map_v.get(sel_di_v, "")
    _sd_code    = "" if sel_sd_v == "All" else sdist_map_v.get(sel_sd_v, "")
    _sel_key    = (_state_code, _dist_code, _sd_code)

    # clear results if selection changed
    if st.session_state.vg_result_key and st.session_state.vg_result_key != _sel_key:
        st.session_state.vg_df = None
        st.session_state.vg_result_key = None

    st.divider()

    if sel_di_v != "----------Select----------" and subdists_v:

        if st.session_state.vg_df is None:
            if st.button("🌾 Load Villages", key="btn_get_villages"):
                with st.spinner(f"Fetching villages for **{sel_di_v}** (auto-solving CAPTCHA)…"):
                    try:
                        village_list = fetch_villages_auto(
                            state_code=_state_code,
                            district_code=_dist_code,
                            subdistrict_code=_sd_code,
                        )
                        if village_list:
                            df_vg = pd.DataFrame(village_list)
                            df_vg.insert(0, "S.No.", range(1, len(df_vg) + 1))
                            st.session_state.vg_df = df_vg
                            st.session_state.vg_result_key = _sel_key
                            st.rerun()
                        else:
                            st.warning("No villages returned. Please try again.")
                    except Exception as _e:
                        st.error(f"Error: {_e}")
        else:
            df_vg = st.session_state.vg_df.copy()

            rc1, rc2 = st.columns([4, 1])
            with rc2:
                if st.button("🔄 Refresh", key="btn_reset_vg"):
                    st.session_state.vg_df = None
                    st.session_state.vg_result_key = None
                    st.rerun()

            q_vg = st.text_input("🔍 Search Village Name", key="q_vg",
                                 placeholder="Type a village name to filter…")
            if q_vg:
                df_vg = df_vg[df_vg["Village Name"].str.contains(q_vg, case=False, na=False)]

            m1, m2, m3 = st.columns(3)
            m1.metric("District", sel_di_v)
            m2.metric("Sub-District", sel_sd_v)
            m3.metric("Villages Found", len(df_vg))

            st.dataframe(df_vg.set_index("S.No."), use_container_width=True, height=520)
            st.divider()
            st.subheader("📤 Export")
            export_bar(df_vg.reset_index(drop=True), "villages")

    else:
        if sel_st_v == "----------Select----------":
            st.info("👆 Select a **State / UT** to begin.")
        elif sel_di_v == "----------Select----------":
            st.info("👆 Now select a **District**.")
