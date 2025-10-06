import streamlit as st
import pandas as pd
import requests
import re
from math import sin, cos, radians
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import pytz
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE ---
IPGEOLOCATION_API_KEY = "3a6e8044a5294776a880a165fd279516"  # Inserisci la tua chiave API

GITHUB_USER = "angelo79"
REPO_NAME = "total_step"
BRANCH = "main"
PATH_AIRPORTS = "airport_list.csv"
PATH_LIMITS = "aircraft_limits.csv"

url_airports = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_AIRPORTS}"
url_limits = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_LIMITS}"


# --- FUNZIONI DI PARSING E CALCOLO ---

def parse_coord(coord_str):
    if pd.isna(coord_str) or coord_str.strip() == '': return None, None
    try:
        lat_str, lon_str = coord_str.split(';')
        return float(lat_str), float(lon_str)
    except (ValueError, IndexError): return None, None

def parse_procedures(proc_str):
    if pd.isna(proc_str) or not isinstance(proc_str, str): return []
    pattern = r'\(([^;]+);([^;]+);([^)]+)\)'
    matches = re.findall(pattern, proc_str)
    procedures = []
    for match in matches:
        try:
            procedures.append({"proc": match[0].strip(), "ceil": int(match[1].strip()), "vis": int(match[2].strip())})
        except (ValueError, IndexError): continue
    return procedures

def parse_weather_conditions(report_str):
    if not isinstance(report_str, str): return 9999, 99999
    sanitized_report = re.sub(r'\b\d{4}/\d{4}\b', '', report_str)
    sanitized_report = re.sub(r'\b\d{6}Z\b', '', sanitized_report)
    vis_matches = re.findall(r'\b(?<!\d)\d{4}(?!\d)\b', sanitized_report)
    vis_values = [int(v) for v in vis_matches]
    if "CAVOK" in report_str: vis_values.append(9999)
    visibility = min(vis_values) if vis_values else 9999
    ceil_matches = re.findall(r'\b(BKN|OVC)(\d{3})\b', report_str)
    ceil_values = [int(height) * 100 for code, height in ceil_matches]
    ceiling = min(ceil_values) if ceil_values else 99999
    return visibility, ceiling

def parse_runway_data(data_string):
    true_hdgs, magn_hdgs = [], []
    if isinstance(data_string, str):
        pairs = data_string.strip().split(';')
        for pair in pairs:
            match = re.match(r"^\s*(\d+)\s*\(\s*(\d+)\s*\)\s*$", pair.strip())
            if match:
                true_hdgs.append(int(match.group(1)))
                magn_hdgs.append(int(match.group(2)))
    return true_hdgs, magn_hdgs

def format_grouped_procedures(procedures, vis, ceil):
    if not procedures:
        return ""
    grouped_by_rwy = {}
    for proc in procedures:
        match = re.search(r'RWY\d{2}', proc['proc'])
        rwy_key = match.group(0) if match else 'MISC'
        if rwy_key not in grouped_by_rwy:
            grouped_by_rwy[rwy_key] = []
        color = 'green' if vis >= proc['vis'] and ceil >= proc['ceil'] else 'red'
        grouped_by_rwy[rwy_key].append(f"<span style='color:{color};'>{proc['proc']}</span>")
    output_lines = [f"<div>{'&nbsp;&nbsp;|&nbsp;&nbsp;'.join(procs)}</div>" for rwy, procs in sorted(grouped_by_rwy.items())]
    return "".join(output_lines)

@st.cache_data(ttl=21600)
def get_astronomy_data(lat, lon, api_key):
    params = {"apiKey": api_key, "lat": lat, "long": lon}
    try:
        response = requests.get("https://api.ipgeolocation.io/astronomy", params=params)
        response.raise_for_status()
        data = response.json()
        local_tz = pytz.timezone('Europe/Rome')
        date_today = datetime.strptime(data['date'], '%Y-%m-%d').date()
        def to_utc(time_str):
            if not time_str or time_str == "-:-": return "N/A"
            h, m = map(int, time_str.split(':'))
            local_dt = local_tz.localize(datetime.combine(date_today, datetime.min.time())).replace(hour=h, minute=m)
            return local_dt.astimezone(pytz.utc).strftime('%H:%MZ')
        illum_str = data.get('moon_illumination_percentage', '0')
        illumination_percent = float(illum_str.replace('%','')) if illum_str else 0.0
        estimated_millilux = (illumination_percent / 100.0) * 0.25 * 1000
        return {"sunrise": to_utc(data.get("sunrise")), "sunset": to_utc(data.get("sunset")),"moonrise": to_utc(data.get("moonrise")), "moonset": to_utc(data.get("moonset")),"moon_phase": data.get("moon_phase", "N/A").replace("_", " ").title(),"moon_luminosity": round(estimated_millilux)}
    except Exception as e:
        st.warning(f"Non è stato possibile recuperare i dati astronomici: {e}")
        return None

# --- FUNZIONE METEO: NESSUNA CACHE, SOLO DOWNLOAD DIRETTO ---
def get_weather_data(icao):
    metar, taf = "METAR non disponibile", "TAF non disponibile"
    headers = {"User-Agent": "TotalStep-Streamlit-App/Final"}
    try:
        r_metar = requests.get(f"https://aviationweather.gov/api/data/metar?ids={icao}&format=raw&hoursBeforeNow=2", headers=headers)
        if r_metar.ok and r_metar.text: metar = r_metar.text.strip()
    except requests.exceptions.RequestException: pass
    try:
        r_taf = requests.get(f"https://aviationweather.gov/api/data/taf?ids={icao}&format=raw&hoursBeforeNow=3", headers=headers)
        if r_taf.ok and r_taf.text: taf = r_taf.text.strip()
        elif r_taf.status_code == 404: taf = "TAF non emesso per questa stazione."
    except requests.exceptions.RequestException: pass
    return metar, taf

@st.cache_data
def load_aircraft_limits(url):
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    # Converte esplicitamente i valori in float
    limits = {
        'max_wind': float(df['max_wind'].iloc[0]),
        'max_headwind': float(df['max_headwind'].iloc[0]),
        'max_tailwind': float(df['max_tailwind'].iloc[0]),
        'max_crosswind_dry': float(df['max_crosswind_dry'].iloc[0]),
        'max_crosswind_wet': float(df['max_crosswind_wet'].iloc[0])
    }
    return limits

def parse_multiple_wind(report_str):
    if not isinstance(report_str, str): return []
    pattern = r"(\d{3})(\d{2,3})(?:G\d{2,3})?KT"
    matches = re.findall(pattern, report_str)
    return [(int(d), int(s)) for d, s in matches if int(d) != 0 or int(s) != 0]

def get_max_wind_components(winds, rwy_true_heading):
    max_hw, max_tw, max_cw, max_w = 0.0, 0.0, 0.0, 0.0
    for wind_dir, wind_speed in winds:
        angle_diff = radians(wind_dir - rwy_true_heading)
        headwind_comp = wind_speed * cos(angle_diff)
        if headwind_comp >= 0: max_hw = max(max_hw, headwind_comp)
        else: max_tw = max(max_tw, abs(headwind_comp))
        max_cw = max(max_cw, abs(wind_speed * sin(angle_diff)))
        max_w = max(max_w, wind_speed)
    return max_hw, max_tw, max_cw, max_w

def format_runway_name(magnetic_heading):
    return f"RWY{round(magnetic_heading / 10):02d}"

def get_colored_wind_display(max_headwind, max_tailwind, max_crosswind, max_wind, limits):
    parts = []
    if max_headwind > 0.0: 
        parts.append(f"<span style='color:{'red' if max_headwind > limits['max_headwind'] else 'green'};'>Max Headwind: {max_headwind:.1f} kts</span>")
    if max_tailwind > 0.0: 
        parts.append(f"<span style='color:{'red' if max_tailwind > limits['max_tailwind'] else 'green'};'>Max Tailwind: {max_tailwind:.1f} kts</span>")
    if max_crosswind > limits['max_crosswind_dry']: color_cw = "red"
    elif max_crosswind > limits['max_crosswind_wet']: color_cw = "orange"
    else: color_cw = "green"
    parts.append(f"<span style='color:{color_cw};'>Max Crosswind: {max_crosswind:.1f} kt</span>")
    parts.append(f"<span style='color:{'red' if max_wind > limits['max_wind'] else 'green'};'>Max Wind: {max_wind:.1f} kts</span>")
    return " | ".join(parts)

# --- INTERFACCIA STREAMLIT ---
st.set_page_config(layout="wide")
st.markdown("<h1 style='text-align: center;'>TOTAL STEP</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: right; font-size: 0.9em;'>by: angelo.corallo@am.difesa.it</p>", unsafe_allow_html=True)

st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh_counter")

now = datetime.now(pytz.timezone('Europe/Rome'))
st.info(f"Last update (local time): {now.strftime('%H:%M:%S on %d/%m/%Y')}")

try:
    aircraft_limits = load_aircraft_limits(url_limits)
    airports_df = pd.read_csv(url_airports, skipinitialspace=True)
    
    first_airport_row = airports_df[airports_df['coord'].notna()].iloc[0] if 'coord' in airports_df.columns and not airports_df[airports_df['coord'].notna()].empty else None
    
    if first_airport_row is not None:
        lat, lon = parse_coord(first_airport_row['coord'])
        first_airport_icao = first_airport_row['ICAO'].strip()
    else: lat, lon, first_airport_icao = None, None, None

    for index, row in airports_df.iterrows():
        icao, name = row["ICAO"].strip(), row["Name"].strip()
        st.subheader(f"{icao} - {name}")
        
        if icao == first_airport_icao and lat is not None:
            astro_data = get_astronomy_data(lat, lon, IPGEOLOCATION_API_KEY)
            if astro_data:
                st.markdown(f"<div style='font-size: 0.9em;'>Sunrise: {astro_data['sunrise']} | Sunset: {astro_data['sunset']}<br>Moonrise: {astro_data['moonrise']} | Moonset: {astro_data['moonset']}<br>Moon Phase: {astro_data['moon_phase']} | Max Illumination: {astro_data['moon_luminosity']} millilux</div>", unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

        metar, taf = get_weather_data(icao)
        procedures = parse_procedures(row.get('(proc;ceil;vis)'))

        col1, col2 = st.columns(2)
        with col1:
            st.text("METAR")
            st.text_area("METAR_area", metar, height=50, key=f"metar_{icao}", label_visibility="collapsed")
            if procedures:
                metar_vis, metar_ceil = parse_weather_conditions(metar)
                st.markdown("Procedures (GREEN: at or above minima | RED: below minima):", unsafe_allow_html=True)
                st.markdown(format_grouped_procedures(procedures, metar_vis, metar_ceil), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
            
            st.markdown("Wind Components")
            metar_winds = parse_multiple_wind(metar)
            if not metar_winds: st.info("Wind not reported or calm.")
            else:
                true_hdgs, magn_hdgs = parse_runway_data(row['RWY_true_north(magn_north)'])
                wind_lines = []
                for true_hdg, magn_hdg in zip(true_hdgs, magn_hdgs):
                    max_hw, max_tw, max_cw, max_w = get_max_wind_components(metar_winds, true_hdg)
                    wind_lines.append(f"<div>{format_runway_name(magn_hdg)}: {get_colored_wind_display(max_hw, max_tw, max_cw, max_w, aircraft_limits)}</div>")
                st.markdown("".join(wind_lines), unsafe_allow_html=True)
        
        with col2:
            st.text("TAF")
            st.text_area("TAF_area", taf, height=150, key=f"taf_{icao}", label_visibility="collapsed")
            if procedures:
                taf_vis, taf_ceil = parse_weather_conditions(taf)
                st.markdown("Procedures (GREEN: at or above minima | RED: below minima):", unsafe_allow_html=True)
                st.markdown(format_grouped_procedures(procedures, taf_vis, taf_ceil), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                
            st.markdown("Forecast Wind Components")
            taf_winds = parse_multiple_wind(taf)
            if not taf_winds: st.info("No specific wind forecast.")
            else:
                true_hdgs, magn_hdgs = parse_runway_data(row['RWY_true_north(magn_north)'])
                wind_lines = []
                for true_hdg, magn_hdg in zip(true_hdgs, magn_hdgs):
                    max_hw, max_tw, max_cw, max_w = get_max_wind_components(taf_winds, true_hdg)
                    wind_lines.append(f"<div>{format_runway_name(magn_hdg)}: {get_colored_wind_display(max_hw, max_tw, max_cw, max_w, aircraft_limits)}</div>")
                st.markdown("".join(wind_lines), unsafe_allow_html=True)

        st.markdown("---")

except Exception as e:
    st.error(f"Impossibile caricare o processare i file: {e}")
    st.exception(e)
