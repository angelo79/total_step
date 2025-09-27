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
FILE_PATH = "airport_list.csv" # Percorso del file nel repository, es. "data/airport_list.csv"

raw_github_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{FILE_PATH}"


# --- FUNZIONI DI CALCOLO E PARSING ---

@st.cache_data(ttl=300)
def get_weather_data(icao):
    """Recupera METAR e TAF."""
    metar = "METAR non disponibile"
    taf = "TAF non disponibile"
    headers = {"User-Agent": "TotalStep-Streamlit-App/1.3"}
    
    try:
        metar_url = "https://aviationweather.gov/api/data/metar"
        params_metar = {"ids": icao, "format": "raw", "hoursBeforeNow": 2}
        response_metar = requests.get(metar_url, params=params_metar, headers=headers)
        if response_metar.ok and response_metar.text:
            metar = response_metar.text.strip()
    except requests.exceptions.RequestException: pass
    
    try:
        taf_url = "https://aviationweather.gov/api/data/taf"
        params_taf = {"ids": icao, "format": "raw", "hoursBeforeNow": 3}
        response_taf = requests.get(taf_url, params=params_taf, headers=headers)
        if response_taf.ok and response_taf.text:
            taf = response_taf.text.strip()
        elif response_taf.status_code == 404:
            taf = "TAF non emesso per questa stazione."
    except requests.exceptions.RequestException: pass

    return metar, taf

def parse_wind_from_metar(metar):
    """Estrae direzione e velocità del vento da una stringa METAR."""
    if not isinstance(metar, str): return None, None
    match = re.search(r"(\d{3})(\d{2,3})(G\d{2,3})?KT", metar)
    if match:
        wind_dir = int(match.group(1))
        wind_speed = int(match.group(2))
        if wind_dir == 0 and wind_speed == 0: return None, None
        return wind_dir, wind_speed
    return None, None

def calculate_wind_components(wind_dir, wind_speed, rwy_true_heading):
    """Calcola le componenti headwind e crosswind usando l'orientamento vero."""
    angle_diff = radians(wind_dir - rwy_true_heading)
    headwind = wind_speed * cos(angle_diff)
    crosswind = wind_speed * sin(angle_diff)
    return headwind, crosswind

def format_runway_name(magnetic_heading):
    """Converte l'orientamento magnetico nel formato RWYXX."""
    runway_number = round(magnetic_heading / 10)
    return f"RWY{runway_number:02d}"

# --- NUOVA FUNZIONE DI PARSING PER LA COLONNA DELLE PISTE ---
def parse_runway_data(data_string):
    """
    Estrae gli orientamenti veri e magnetici da una stringa.
    Formato atteso: "true1(magn1);true2(magn2)"
    """
    true_headings = []
    magnetic_headings = []
    
    if not isinstance(data_string, str):
        return [], []
        
    pairs = data_string.split(';')
    for pair in pairs:
        match = re.match(r"^\s*(\d+)\s*\(\s*(\d+)\s*\)\s*$", pair.strip())
        if match:
            true_headings.append(int(match.group(1)))
            magnetic_headings.append(int(match.group(2)))
    return true_headings, magnetic_headings


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
    # --- MODIFICA NOME COLONNA ---
    colonna_piste = "RWY_true_north(magn_north)"
    airports_df = pd.read_csv(raw_github_url, skipinitialspace=True)

    if "ICAO" not in airports_df.columns or "Name" not in airports_df.columns:
        st.error("CSV file must contain 'ICAO' and 'Name' columns.")
    else:
        for index, row in airports_df.iterrows():
            icao = row["ICAO"].strip()
            name = row["Name"].strip()

            st.subheader(f"{icao} - {name}")

            metar, taf = get_weather_data(icao)
            wind_dir, wind_speed = parse_wind_from_metar(metar)

            col1, col2 = st.columns(2)
            col1.text_area("METAR", metar, height=50, key=f"metar_{icao}_{index}")
            col2.text_area("TAF", taf, height=150, key=f"taf_{icao}_{index}")

            st.markdown("##### Wind Components per Runway")

            if colonna_piste not in row or pd.isna(row[colonna_piste]):
                st.warning("Runway data not available in CSV for this airport.")
            elif wind_dir is None:
                st.info("Wind not reported in METAR or calm wind.")
            else:
                # --- USA LA NUOVA FUNZIONE DI PARSING ---
                true_headings, magnetic_headings = parse_runway_data(row[colonna_piste])
                
                if not true_headings:
                    st.error(f"Invalid format for runway data: '{row[colonna_piste]}'. Expected 'true(magn);...'.")
                else:
                    wind_info_list = []
                    # Itera su entrambe le liste contemporaneamente
                    for true_hdg, magn_hdg in zip(true_headings, magnetic_headings):
                        headwind, crosswind = calculate_wind_components(wind_dir, wind_speed, true_hdg)
                        
                        hw_label = f"Head Wind: {abs(headwind):.1f} kts" if headwind >= 0 else f"Tail Wind: {abs(headwind):.1f} kts"
                        cw_dir_label = "right" if crosswind >= 0 else "left"
                        cw_label = f"Cross Wind: {abs(crosswind):.1f} kt ({cw_dir_label})"
                        
                        runway_name = format_runway_name(magn_hdg)
                        
                        wind_info_list.append(f"**{runway_name}**: {hw_label} | {cw_label}")
                    
                    st.markdown("  \n".join(wind_info_list))
            
            st.markdown("---")

except Exception as e:
    st.error(f"Could not load or process the file from GitHub: {e}")
    st.code(f"Attempted URL: {raw_github_url}")

