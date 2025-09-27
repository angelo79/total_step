import streamlit as st
import pandas as pd
import requests
import re
from math import sin, cos, radians
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import pytz
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAZIONE GITHUB ---
GITHUB_USER = "angelo79"
REPO_NAME = "total_step"
BRANCH = "main"
PATH_AIRPORTS = "airport_list.csv"
PATH_LIMITS = "aircraft_limits.csv"

url_airports = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_AIRPORTS}"
url_limits = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_LIMITS}"


# --- FUNZIONI DI CALCOLO E PARSING ---

@st.cache_data(ttl=300)
def get_weather_data(icao):
    """Recupera METAR e TAF."""
    metar, taf = "METAR non disponibile", "TAF non disponibile"
    headers = {"User-Agent": "TotalStep-Streamlit-App/2.2"}
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
    """Carica i limiti dal file CSV."""
    loaded_df = pd.read_csv(url)
    loaded_df.columns = loaded_df.columns.str.strip()
    return loaded_df.iloc[0].to_dict()

def parse_multiple_wind_from_metar(metar):
    """Estrae tutti i gruppi di vento da una stringa METAR."""
    if not isinstance(metar, str): return []
    pattern = r"(\d{3})(\d{2,3})(?:G\d{2,3})?KT"
    matches = re.findall(pattern, metar)
    return [(int(direction), int(speed)) for direction, speed in matches if int(direction) != 0 or int(speed) != 0]

def get_max_wind_components(winds, rwy_true_heading):
    """Calcola i valori massimi di head, tail, e crosswind da una lista di venti."""
    max_headwind = 0.0
    max_tailwind = 0.0
    max_crosswind = 0.0

    for wind_dir, wind_speed in winds:
        angle_diff = radians(wind_dir - rwy_true_heading)
        headwind_component = wind_speed * cos(angle_diff)
        crosswind_component = wind_speed * sin(angle_diff)

        if headwind_component >= 0:
            max_headwind = max(max_headwind, headwind_component)
        else:
            max_tailwind = max(max_tailwind, abs(headwind_component))
        
        max_crosswind = max(max_crosswind, abs(crosswind_component))

    return max_headwind, max_tailwind, max_crosswind

def format_runway_name(magnetic_heading):
    """Converte l'orientamento magnetico nel formato RWYXX."""
    return f"RWY{round(magnetic_heading / 10):02d}"

def parse_runway_data(data_string):
    """Estrae gli orientamenti veri e magnetici da una stringa."""
    true_hdgs, magn_hdgs = [], []
    if isinstance(data_string, str):
        for pair in data_string.split(';'):
            match = re.match(r"^\s*(\d+)\s*\(\s*(\d+)\s*\)\s*$", pair.strip())
            if match:
                true_hdgs.append(int(match.group(1)))
                magn_hdgs.append(int(match.group(2)))
    return true_hdgs, magn_hdgs

# --- FUNZIONE AGGIORNATA PER OMETTERE VALORI A ZERO ---
def get_colored_wind_display(max_headwind, max_tailwind, max_crosswind, limits):
    """Genera la stringa Markdown, omettendo componenti a zero."""
    parts = []

    # Aggiunge Max Headwind solo se non è zero
    if max_headwind > 0.0:
        color_hw = "red" if max_headwind >= limits['max_headwind'] else "green"
        parts.append(f"<span style='color:{color_hw};'>Max Headwind: {max_headwind:.1f} kts</span>")

    # Aggiunge Max Tailwind solo se non è zero
    if max_tailwind > 0.0:
        color_tw = "red" if max_tailwind >= limits['max_tailwind'] else "green"
        parts.append(f"<span style='color:{color_tw};'>Max Tailwind: {max_tailwind:.1f} kts</span>")
        
    # Aggiunge sempre Max Crosswind
    if max_crosswind >= limits['max_crosswind_dry']:
        color_cw = "red"
    elif max_crosswind >= limits['max_crosswind_wet']:
        color_cw = "orange"
    else:
        color_cw = "green"
    parts.append(f"<span style='color:{color_cw};'>Max Crosswind: {max_crosswind:.1f} kt</span>")
    
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
    if "ICAO" not in airports_df.columns or colonna_piste not in airports_df.columns:
        st.error(f"Il file CSV degli aeroporti deve contenere le colonne 'ICAO' e '{colonna_piste}'.")
    else:
        for index, row in airports_df.iterrows():
            icao, name = row["ICAO"].strip(), row["Name"].strip()
            st.subheader(f"{icao} - {name}")

            metar, taf = get_weather_data(icao)
            winds = parse_multiple_wind_from_metar(metar)

            col1, col2 = st.columns(2)
            col1.text_area("METAR", metar, height=50, key=f"metar_{icao}_{index}")
            col2.text_area("TAF", taf, height=150, key=f"taf_{icao}_{index}")
            
            st.markdown("##### Wind Components per Runway")
            if pd.isna(row[colonna_piste]):
                st.warning("Runway data not available.")
            elif not winds:
                st.info("Wind not reported or calm.")
            else:
                true_hdgs, magn_hdgs = parse_runway_data(row[colonna_piste])
                if not true_hdgs:
                    st.error(f"Invalid format for runway data: '{row[colonna_piste]}'.")
                else:
                    for true_hdg, magn_hdg in zip(true_hdgs, magn_hdgs):
                        max_hw, max_tw, max_cw = get_max_wind_components(winds, true_hdg)
                        runway_name = format_runway_name(magn_hdg)
                        
                        display_text = get_colored_wind_display(max_hw, max_tw, max_cw, aircraft_limits)
                        st.markdown(f"**{runway_name}**: {display_text}", unsafe_allow_html=True)
            st.markdown("---")
except Exception as e:
    st.error(f"Impossibile caricare o processare i file da GitHub: {e}")
