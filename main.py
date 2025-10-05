import streamlit as st
import pandas as pd
import requests
import re
from math import sin, cos, radians
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone
import pytz
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE ---
# Inserisci la tua chiave API se ne hai una, altrimenti lasciala vuota per un uso base.
IPGEOLOCATION_API_KEY = "3a6e8044a5294776a880a165fd279516" # YOUR_API_KEY

# Coordinate per Istrana (TV), Italia
ISTRANA_LAT = 45.68
ISTRANA_LON = 12.08

GITHUB_USER = "angelo79"
REPO_NAME = "total_step"
BRANCH = "main"
PATH_AIRPORTS = "airport_list.csv"
PATH_LIMITS = "aircraft_limits.csv"

url_airports = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_AIRPORTS}"
url_limits = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_LIMITS}"


# --- FUNZIONI DI CALCOLO E PARSING ---

# --- FUNZIONE AGGIORNATA PER DATI LUNARI ---
@st.cache_data(ttl=1800)  # Cache per 30 minuti
def get_astronomy_data(lat, lon, api_key):
    """Recupera dati astronomici completi da IPGeolocation."""
    params = {"apiKey": api_key, "lat": lat, "long": lon}
    try:
        response = requests.get("https://api.ipgeolocation.io/astronomy", params=params)
        response.raise_for_status()
        data = response.json()
        
        local_tz = pytz.timezone(data['location']['timezone'])
        date_today = datetime.strptime(data['date'], '%Y-%m-%d').date()

        def to_utc(time_str):
            # Gestisce orari non disponibili (es. luna sempre sopra/sotto l'orizzonte)
            if time_str == "-:-": return "N/A"
            h, m = map(int, time_str.split(':'))
            local_dt = local_tz.localize(datetime.combine(date_today, datetime.min.time())).replace(hour=h, minute=m)
            return local_dt.astimezone(pytz.utc).strftime('%H:%MZ')

        # Stima della luminosità della luna in millilux
        illumination_percent = float(data.get('moon_illumination', '0').replace('%',''))
        # Valore di riferimento: luna piena ~0.25 lux
        max_moon_lux = 0.25 
        estimated_millilux = (illumination_percent / 100.0) * max_moon_lux * 1000

        return {
            "morning_twilight": to_utc(data["civil_twilight_begin"]),
            "evening_twilight": to_utc(data["civil_twilight_end"]),
            "moonrise": to_utc(data["moonrise"]),
            "moonset": to_utc(data["moonset"]),
            "moon_phase": data["moon_status"].replace("_", " ").title(),
            "moon_luminosity": round(estimated_millilux)
        }
    except Exception as e:
        st.warning(f"Non è stato possibile recuperare i dati astronomici: {e}")
        return None

# ... (tutte le altre funzioni rimangono invariate) ...
@st.cache_data(ttl=300)
def get_weather_data(icao):
    metar, taf = "METAR non disponibile", "TAF non disponibile"
    headers = {"User-Agent": "TotalStep-Streamlit-App/2.8"}
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

def load_aircraft_limits(url):
    loaded_df = pd.read_csv(url, dtype=float) 
    loaded_df.columns = loaded_df.columns.str.strip()
    return loaded_df.iloc[0].to_dict()

def parse_multiple_wind_from_metar(metar):
    if not isinstance(metar, str): return []
    pattern = r"(\d{3})(\d{2,3})(?:G\d{2,3})?KT"
    matches = re.findall(pattern, metar)
    return [(int(direction), int(speed)) for direction, speed in matches if int(direction) != 0 or int(speed) != 0]

def parse_multiple_wind_from_taf(taf):
    if not isinstance(taf, str): return []
    pattern = r"(\d{3})(\d{2,3})(?:G\d{2,3})?KT"
    matches = re.findall(pattern, taf)
    return [(int(direction), int(speed)) for direction, speed in matches if int(direction) != 0 or int(speed) != 0]

def get_max_wind_components(winds, rwy_true_heading):
    max_headwind, max_tailwind, max_crosswind, max_wind = 0.0, 0.0, 0.0, 0.0
    for wind_dir, wind_speed in winds:
        angle_diff = radians(wind_dir - rwy_true_heading)
        headwind_component = wind_speed * cos(angle_diff)
        crosswind_component = wind_speed * sin(angle_diff)
        max_wind = max(max_wind, wind_speed)
        if headwind_component >= 0:
            max_headwind = max(max_headwind, headwind_component)
        else:
            max_tailwind = max(max_tailwind, abs(headwind_component))
        max_crosswind = max(max_crosswind, abs(crosswind_component))
    return max_headwind, max_tailwind, max_crosswind, max_wind

def format_runway_name(magnetic_heading):
    return f"RWY{round(magnetic_heading / 10):02d}"

def parse_runway_data(data_string):
    true_hdgs, magn_hdgs = [], []
    if isinstance(data_string, str):
        for pair in data_string.split(';'):
            match = re.match(r"^\s*(\d+)\s*\(\s*(\d+)\s*\)\s*$", pair.strip())
            if match:
                true_hdgs.append(int(match.group(1)))
                magn_hdgs.append(int(match.group(2)))
    return true_hdgs, magn_hdgs

def get_colored_wind_display(max_headwind, max_tailwind, max_crosswind, max_wind, limits):
    parts = []
    if max_headwind > 0.0:
        color_hw = "red" if max_headwind >= limits['max_headwind'] else "green"
        parts.append(f"<span style='color:{color_hw};'>Max Headwind: {max_headwind:.1f} kts</span>")
    if max_tailwind > 0.0:
        color_tw = "red" if max_tailwind >= limits['max_tailwind'] else "green"
        parts.append(f"<span style='color:{color_tw};'>Max Tailwind: {max_tailwind:.1f} kts</span>")
    if max_crosswind >= limits['max_crosswind_dry']:
        color_cw = "red"
    elif max_crosswind >= limits['max_crosswind_wet']:
        color_cw = "orange"
    else:
        color_cw = "green"
    parts.append(f"<span style='color:{color_cw};'>Max Crosswind: {max_crosswind:.1f} kt</span>")
    color_wind = "red" if max_wind >= limits['max_wind'] else "green"
    parts.append(f"<span style='color:{color_wind};'>Max Wind: {max_wind:.1f} kts</span>")
    return " | ".join(parts)


# --- INTERFACCIA STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Total Step")

refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="auto_refresh_counter")
if refresh_count > 0:
    st.cache_data.clear()
    streamlit_js_eval(js_expressions="parent.window.location.reload()")
if st.button("🔄 Manual Refresh"):
    st.cache_data.clear()
    streamlit_js_eval(js_expressions="parent.window.location.reload()")
now = datetime.now(pytz.timezone('Europe/Rome'))
st.info(f"**Last update (local time): {now.strftime('%H:%M:%S on %d/%m/%Y')}**")

try:
    aircraft_limits = load_aircraft_limits(url_limits)
    airports_df = pd.read_csv(url_airports, skipinitialspace=True)
    
    colonna_piste = "RWY_true_north(magn_north)"
    for index, row in airports_df.iterrows():
        icao, name = row["ICAO"].strip(), row["Name"].strip()

        st.subheader(f"{icao} - {name}")
        
        # --- VISUALIZZAZIONE DATI ASTRONOMICI PER ISTRANA ---
        if icao == "LIPS":
            astro_data = get_astronomy_data(ISTRANA_LAT, ISTRANA_LON, IPGEOLOCATION_API_KEY)
            if astro_data:
                st.markdown(
                    f"<div style='font-size: 0.9em;'>"
                    f"**Morning Civil Twilight:** {astro_data['morning_twilight']}<br>"
                    f"**Evening Civil Twilight:** {astro_data['evening_twilight']}<br>"
                    f"**Moonrise:** {astro_data['moonrise']} | **Moonset:** {astro_data['moonset']}<br>"
                    f"**Moon Phase:** {astro_data['moon_phase']} | **Max Illumination:** {astro_data['moon_luminosity']} millilux"
                    "</div>", unsafe_allow_html=True
                )
        
        metar, taf = get_weather_data(icao)
        col1, col2 = st.columns(2)
        col1.text_area("METAR", metar, height=50, key=f"metar_{icao}_{index}")
        col2.text_area("TAF", taf, height=150, key=f"taf_{icao}_{index}")
        
        true_hdgs, magn_hdgs = parse_runway_data(row[colonna_piste])
        
        st.markdown("##### METAR Wind Components")
        metar_winds = parse_multiple_wind_from_metar(metar)
        if pd.isna(row[colonna_piste]):
            st.warning("Runway data not available.")
        elif not metar_winds:
            st.info("Wind not reported or calm in METAR.")
        else:
            for true_hdg, magn_hdg in zip(true_hdgs, magn_hdgs):
                max_hw, max_tw, max_cw, max_w = get_max_wind_components(metar_winds, true_hdg)
                runway_name = format_runway_name(magn_hdg)
                display_text = get_colored_wind_display(max_hw, max_tw, max_cw, max_w, aircraft_limits)
                st.markdown(f"**{runway_name}**: {display_text}", unsafe_allow_html=True)
        
        st.markdown("##### TAF Forecast Wind Components")
        taf_winds = parse_multiple_wind_from_taf(taf)
        if pd.isna(row[colonna_piste]):
            st.warning("Runway data not available.")
        elif not taf_winds:
            st.info("No specific wind forecast in TAF.")
        else:
            for true_hdg, magn_hdg in zip(true_hdgs, magn_hdgs):
                max_hw, max_tw, max_cw, max_w = get_max_wind_components(taf_winds, true_hdg)
                runway_name = format_runway_name(magn_hdg)
                display_text = get_colored_wind_display(max_hw, max_tw, max_cw, max_w, aircraft_limits)
                st.markdown(f"**{runway_name}**: {display_text}", unsafe_allow_html=True)

        st.markdown("---")

except Exception as e:
    st.error(f"Impossibile caricare o processare i file da GitHub: {e}")
    st.exception(e)

