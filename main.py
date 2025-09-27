import streamlit as st
import pandas as pd
import requests
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import pytz

# --- CONFIGURAZIONE GITHUB ---
# ATTENZIONE: Modifica queste 4 variabili con i dettagli del tuo repository.
GITHUB_USER = "angelo79"
REPO_NAME = "total_step"
BRANCH = "main"  # o "master" o il nome del tuo branch principale
FILE_PATH = "airport_list.csv" # Percorso del file nel repository, es. "data/airport_list.csv"

raw_github_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{FILE_PATH}"


# --- FUNZIONI RECUPERO DATI ---

@st.cache_data(ttl=300) # Cache per 5 minuti
def get_weather_data(icao):
    """Recupera METAR e TAF usando i nuovi endpoint API di AviationWeather.gov."""
    metar = "METAR non disponibile"
    taf = "TAF non disponibile"
    headers = {"User-Agent": "Streamlit-METAR-App/1.0"}

    # --- Endpoint per METAR ---
    try:
        metar_url = "https://aviationweather.gov/api/data/metar"
        params_metar = {"ids": icao, "format": "raw", "hoursBeforeNow": 2}
        response_metar = requests.get(metar_url, params=params_metar, headers=headers)
        response_metar.raise_for_status()
        if response_metar.text:
            metar = response_metar.text.strip()
    except requests.exceptions.RequestException:
        pass

    # --- Endpoint per TAF ---
    try:
        taf_url = "https://aviationweather.gov/api/data/taf"
        params_taf = {"ids": icao, "format": "raw", "hoursBeforeNow": 3}
        response_taf = requests.get(taf_url, params=params_taf, headers=headers)
        response_taf.raise_for_status()
        if response_taf.text:
            taf = response_taf.text.strip()
    except requests.exceptions.RequestException as e:
        if e.response and e.response.status_code == 404:
            taf = "TAF non emesso per questa stazione."
        else:
            pass

    return metar, taf


# --- INTERFACCIA STREAMLIT ---

st.set_page_config(layout="wide")
st.title("METAR e TAF Viewer da GitHub")

# --- NUOVA SEZIONE: ORARIO AGGIORNAMENTO ---
# Mostra l'orario attuale ogni volta che lo script viene eseguito
now = datetime.now(pytz.timezone('Europe/Rome'))
st.info(f"**Ultimo aggiornamento (ora locale): {now.strftime('%H:%M:%S del %d/%m/%Y')}**")

# Trigger per l'aggiornamento automatico ogni 5 minuti
st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

# Pulsante per forzare l'aggiornamento manuale
if st.button("🔄 Aggiorna Dati Manualmente"):
    # Svuota la cache di tutte le funzioni per forzare il ricaricamento
    st.cache_data.clear()
    # Riesegue l'intero script dall'inizio
    st.rerun()

# Caricamento del file CSV da GitHub
try:
    airports_df = pd.read_csv(raw_github_url, skipinitialspace=True)

    if "ICAO" not in airports_df.columns or "Name" not in airports_df.columns:
        st.error(f"Il file CSV deve contenere le colonne 'ICAO' e 'Name'.")
    else:
        for index, row in airports_df.iterrows():
            icao = row["ICAO"].strip()
            name = row["Name"].strip()

            st.subheader(f"{icao} - {name}")

            metar, taf = get_weather_data(icao)

            col1, col2 = st.columns(2)
            with col1:
                st.text_area("METAR", metar, height=50, key=f"metar_{icao}_{index}")
            with col2:
                st.text_area("TAF", taf, height=150, key=f"taf_{icao}_{index}")
            st.markdown("---")

except Exception as e:
    st.error(f"Impossibile caricare il file da GitHub: {e}")
    st.warning(f"Controlla che le variabili del tuo repository siano corrette e che il repository sia pubblico.")
    st.code(f"URL tentato: {raw_github_url}")

