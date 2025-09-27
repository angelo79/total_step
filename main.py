import streamlit as st
import pandas as pd
import requests
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURAZIONE GITHUB ---
# ATTENZIONE: Modifica queste 4 variabili con i dettagli del tuo repository.
# Lo script presume che il repository sia pubblico.
GITHUB_USER = "angelo79"
REPO_NAME = "total_step"
BRANCH = "main"  # o "master" o il nome del tuo branch principale
FILE_PATH = "airport_list.csv" # Percorso del file nel repository, es. "data/airport_list.csv"

# Costruisce l'URL per accedere al file raw su GitHub
raw_github_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{FILE_PATH}"


# --- FUNZIONI RECUPERO DATI ---

@st.cache_data(ttl=300) # Cache per 5 minuti
def get_weather_data(icao):
    """Recupera METAR e TAF usando i nuovi endpoint API di AviationWeather.gov."""
    metar = "METAR non disponibile"
    taf = "TAF non disponibile"
    # È buona pratica includere un User-Agent per identificare la tua app
    headers = {"User-Agent": "Streamlit-METAR-App/1.0 (https://github.com/TuoNomeUtenteGitHub/NomeDelTuoRepo)"}

    # --- Endpoint aggiornato per METAR ---
    try:
        metar_url = "https://aviationweather.gov/api/data/metar"
        params_metar = {"ids": icao, "format": "raw", "hoursBeforeNow": 2}
        response_metar = requests.get(metar_url, params=params_metar, headers=headers)
        response_metar.raise_for_status() # Solleva un'eccezione per errori HTTP (es. 4xx, 5xx)
        if response_metar.text:
            metar = response_metar.text.strip()
    except requests.exceptions.RequestException:
        # Se il METAR non viene trovato (es. 404), la funzione non bloccherà l'app,
        # ma mostrerà il messaggio di default "METAR non disponibile".
        pass

    # --- Endpoint aggiornato per TAF ---
    try:
        taf_url = "https://aviationweather.gov/api/data/taf"
        params_taf = {"ids": icao, "format": "raw", "hoursBeforeNow": 3}
        response_taf = requests.get(taf_url, params=params_taf, headers=headers)
        response_taf.raise_for_status()
        if response_taf.text:
            taf = response_taf.text.strip()
    except requests.exceptions.RequestException as e:
        # Molti aeroporti (specialmente militari) non emettono TAF. Un errore 404 è normale.
        if e.response and e.response.status_code == 404:
            taf = "TAF non emesso per questa stazione."
        else:
            # Per altri errori (es. di connessione), lascialo come "non disponibile".
            pass

    return metar, taf


# --- INTERFACCIA STREAMLIT ---

st.set_page_config(layout="wide")
st.title("METAR e TAF Viewer da GitHub")

# Trigger per l'aggiornamento automatico ogni 5 minuti
st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

# Pulsante per forzare l'aggiornamento manuale
if st.button("Aggiorna Dati Manualmente"):
    st.cache_data.clear()
    st.rerun()

# Caricamento del file CSV da GitHub
try:
    st.info(f"Caricamento di `{FILE_PATH}` dal repository GitHub...")
    airports_df = pd.read_csv(raw_github_url, skipinitialspace=True)

    if "ICAO" not in airports_df.columns or "Name" not in airports_df.columns:
        st.error(f"Il file CSV in `{raw_github_url}` deve contenere le colonne 'ICAO' e 'Name'.")
        st.write(f"Colonne rilevate: {airports_df.columns.tolist()}")
    else:
        st.success(f"Trovati {len(airports_df)} aeroporti. Caricamento dati meteo...")

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
    st.warning(f"Controlla che le variabili GITHUB_USER, REPO_NAME, BRANCH, e FILE_PATH siano corrette e che il repository sia pubblico.")
    st.code(f"URL tentato: {raw_github_url}")

