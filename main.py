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
    headers = {"User-Agent": "TotalStep-Streamlit-App/1.1"}
    
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
    # Cerca il pattern DDDSS(Ggg)KT dove DDD è la direzione e SS la velocità
    match = re.search(r"(\d{3})(\d{2,3})(G\d{2,3})?KT", metar)
    if match:
        wind_dir = int(match.group(1))
        wind_speed = int(match.group(2))
        # Ignora le raffiche (G) per il calcolo base, ma si potrebbe estendere
        if wind_dir == 0 and wind_speed == 0: return None, None # Vento calmo
        return wind_dir, wind_speed
    return None, None

def calculate_wind_components(wind_dir, wind_speed, rwy_heading):
    """Calcola le componenti headwind e crosswind."""
    angle_diff = radians(wind_dir - rwy_heading)
    headwind = wind_speed * cos(angle_diff)
    crosswind = wind_speed * sin(angle_diff)
    return headwind, crosswind


# --- INTERFACCIA STREAMLIT ---

st.set_page_config(layout="wide")
st.title("Total Step")

now = datetime.now(pytz.timezone('Europe/Rome'))
st.info(f"**Ultimo aggiornamento (ora locale): {now.strftime('%H:%M:%S del %d/%m/%Y')}**")

st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

if st.button("🔄 Aggiorna Dati Manualmente"):
    st.cache_data.clear()
    st.rerun()

try:
    airports_df = pd.read_csv(raw_github_url, skipinitialspace=True)

    if "ICAO" not in airports_df.columns or "Name" not in airports_df.columns:
        st.error("Il file CSV deve contenere almeno le colonne 'ICAO' e 'Name'.")
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

            # --- NUOVA SEZIONE: CALCOLO E VISUALIZZAZIONE VENTO ---
            st.markdown("##### Componenti Vento per Pista")

            if "RWY_true_north" not in row or pd.isna(row["RWY_true_north"]):
                st.warning("Dati piste non disponibili in CSV per questo aeroporto.")
            elif wind_dir is None:
                st.info("Vento non riportato nel METAR o vento calmo.")
            else:
                try:
                    runways = str(row["RWY_true_north"]).split(';')
                    runway_headings = [int(r.strip()) for r in runways]

                    wind_info_list = []
                    for rwy in runway_headings:
                        headwind, crosswind = calculate_wind_components(wind_dir, wind_speed, rwy)
                        
                        hw_label = "Vento frontale" if headwind >= 0 else "Vento in coda"
                        cw_label = "da destra" if crosswind >= 0 else "da sinistra"
                        
                        wind_info_list.append(
                            f"**Pista {rwy}°**: {hw_label}: **{abs(headwind):.1f} kt** | Vento traverso: **{abs(crosswind):.1f} kt** ({cw_label})"
                        )
                    
                    st.markdown("  \n".join(wind_info_list))

                except (ValueError, TypeError):
                    st.error(f"Formato dati per RWY_true_north non valido: '{row['RWY_true_north']}'. Deve essere numerico e separato da ';'.")
            
            st.markdown("---")

except Exception as e:
    st.error(f"Impossibile caricare o processare il file da GitHub: {e}")
    st.code(f"URL tentato: {raw_github_url}")

