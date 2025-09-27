import streamlit as st
import pandas as pd
import requests
import re
from math import sin, cos, radians
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import pytz

# --- CONFIGURAZIONE GITHUB ---
GITHUB_USER = "angelo79"
REPO_NAME = "total_step"
BRANCH = "main"  # o "master" o il nome del tuo branch principale

# Percorsi ai file nel repository
PATH_AIRPORTS = "airport_list.csv"
PATH_LIMITS = "aircraft_limits.csv"

url_airports = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_AIRPORTS}"
url_limits = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{PATH_LIMITS}"


# --- FUNZIONI DI CALCOLO E PARSING ---

@st.cache_data(ttl=300)
def get_weather_data(icao):
    """Recupera METAR e TAF."""
    metar, taf = "METAR non disponibile", "TAF non disponibile"
    headers = {"User-Agent": "TotalStep-Streamlit-App/1.4"}
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
    """Carica i limiti dal file CSV su GitHub."""
    limits_df = pd.read_csv(url)
    return limits_df.iloc[0].to_dict()

def parse_wind_from_metar(metar):
    if not isinstance(metar, str): return None, None
    match = re.search(r"(\d{3})(\d{2,3})(G\d{2,3})?KT", metar)
    if match and (int(match.group(1)) != 0 or int(match.group(2)) != 0):
        return int(match.group(1)), int(match.group(2))
    return None, None

def calculate_wind_components(wind_dir, wind_speed, rwy_true_heading):
    angle_diff = radians(wind_dir - rwy_true_heading)
    return wind_speed * cos(angle_diff), wind_speed * sin(angle_diff)

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

# --- NUOVA FUNZIONE PER LA COLORAZIONE ---
def get_colored_wind_display(headwind, crosswind, limits):
    """Genera la stringa Markdown con i colori condizionali."""
    abs_crosswind = abs(crosswind)
    
    # Determina colore e testo per Head/Tail Wind
    if headwind >= 0:
        color = "red" if headwind > limits['max_headwind'] else "green"
        hw_text = f"<span style='color:{color};'>Head Wind: {headwind:.1f} kts</span>"
    else:
        tailwind = abs(headwind)
        color = "red" if tailwind > limits['max_tailwind'] else "green"
        hw_text = f"<span style='color:{color};'>Tail Wind: {tailwind:.1f} kts</span>"
        
    # Determina colore per Cross Wind
    if abs_crosswind > limits['max_crosswind_dry']:
        color = "red"
    elif abs_crosswind > limits['max_crosswind_wet']:
        color = "orange"
    else:
        color = "green"
    
    cw_dir = "right" if crosswind >= 0 else "left"
    cw_text = f"<span style='color:{color};'>Cross Wind: {abs_crosswind:.1f} kt ({cw_dir})</span>"
    
    return f"{hw_text} | {cw_text}"


# --- INTERFACCIA STREAMLIT ---
st.set_page_config(layout="wide")
st.title("Total Step")

now = datetime.now(pytz.timezone('Europe/Rome'))
st.info(f"**Last update (local time): {now.strftime('%H:%M:%S on %d/%m/%Y')}**")

st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

if st.button("🔄 Manual Refresh"):
    st.cache_data.clear()
    st.rerun()

try:
    # Carica entrambi i file
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
            wind_dir, wind_speed = parse_wind_from_metar(metar)

            col1, col2 = st.columns(2)
            col1.text_area("METAR", metar, height=50, key=f"metar_{icao}_{index}")
            col2.text_area("TAF", taf, height=150, key=f"taf_{icao}_{index}")
            
            st.markdown("##### Wind Components per Runway")
            if pd.isna(row[colonna_piste]):
                st.warning("Runway data not available.")
            elif wind_dir is None:
                st.info("Wind not reported or calm.")
            else:
                true_hdgs, magn_hdgs = parse_runway_data(row[colonna_piste])
                if not true_hdgs:
                    st.error(f"Invalid format for runway data: '{row[colonna_piste]}'.")
                else:
                    for true_hdg, magn_hdg in zip(true_hdgs, magn_hdgs):
                        headwind, crosswind = calculate_wind_components(wind_dir, wind_speed, true_hdg)
                        runway_name = format_runway_name(magn_hdg)
                        
                        # --- USA LA NUOVA FUNZIONE PER OTTENERE LA STRINGA COLORATA ---
                        display_text = get_colored_wind_display(headwind, crosswind, aircraft_limits)
                        st.markdown(f"**{runway_name}**: {display_text}", unsafe_allow_html=True)
            st.markdown("---")

except Exception as e:
    st.error(f"Impossibile caricare o processare i file da GitHub: {e}")

