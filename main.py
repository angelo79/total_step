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
    headers = {"User-Agent": "TotalStep-Streamlit-App/1.2"}
    
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

def calculate_wind_components(wind_dir, wind_speed, rwy_heading):
    """Calcola le componenti headwind e crosswind."""
    angle_diff = radians(wind_dir - rwy_heading)
    headwind = wind_speed * cos(angle_diff)
    crosswind = wind_speed * sin(angle_diff)
    return headwind, crosswind

# --- NUOVA FUNZIONE PER FORMATTARE IL NOME PISTA ---
def format_runway_name(heading):
    """Converte i gradi della pista nel formato RWYXX (es. 262 -> RWY26)."""
    runway_number = round(heading / 10)
    return f"RWY{runway_number:02d}"


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

            if "RWY_true_north" not in row or pd.isna(row["RWY_true_north"]):
                st.warning("Runway data not available in CSV for this airport.")
            elif wind_dir is None:
                st.info("Wind not reported in METAR or calm wind.")
            else:
                try:
                    runways = str(row["RWY_true_north"]).split(';')
                    runway_headings = [int(r.strip()) for r in runways]

                    wind_info_list = []
                    for rwy_hdg in runway_headings:
                        headwind, crosswind = calculate_wind_components(wind_dir, wind_speed, rwy_hdg)
                        
                        # --- TESTO AGGIORNATO COME RICHIESTO ---
                        hw_label = f"Head Wind: {abs(headwind):.1f} kts" if headwind >= 0 else f"Tail Wind: {abs(headwind):.1f} kts"
                        cw_dir_label = "right" if crosswind >= 0 else "left"
                        cw_label = f"Cross Wind: {abs(crosswind):.1f} kt ({cw_dir_label})"
                        
                        # Usa la nuova funzione per formattare il nome della pista
                        runway_name = format_runway_name(rwy_hdg)
                        
                        wind_info_list.append(f"**{runway_name}**: {hw_label} | {cw_label}")
                    
                    st.markdown("  \n".join(wind_info_list))

                except (ValueError, TypeError):
                    st.error(f"Invalid format for RWY_true_north: '{row['RWY_true_north']}'. Must be numeric and semicolon-separated.")
            
            st.markdown("---")

except Exception as e:
    st.error(f"Could not load or process the file from GitHub: {e}")
    st.code(f"Attempted URL: {raw_github_url}")

