import streamlit as st
import pandas as pd
import requests
from streamlit_autorefresh import st_autorefresh

# --- Funzioni per il recupero dati ---

# Utilizziamo il caching di Streamlit per ottimizzare.
# La cache viene invalidata automaticamente al rerun triggered dall'autorefresh
# o dal pulsante, garantendo che i dati vengano ricaricati.
@st.cache_data(ttl=300) # La cache scade dopo 5 minuti (300 secondi)
def get_metar_taf(icao):
    """Recupera METAR e TAF per un codice ICAO."""
    base_url = "https://aviationweather.gov/api/data"
    params = {
        "datasource": "metars,tafs",
        "requestType": "retrieve",
        "format": "raw",
        "hoursBeforeNow": 3,
        "stationString": icao
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Solleva un errore per status code non 2xx
        
        data = response.text
        metar = "METAR non disponibile"
        taf = "TAF non disponibile"
        
        # Semplice parsing per estrarre i report corretti
        lines = data.splitlines()
        for line in lines:
            if line.startswith(icao): # I report METAR/TAF iniziano con l'ICAO
                metar = line.strip()
            elif line.strip().startswith('TAF'):
                taf = line.strip()

        return metar, taf

    except requests.exceptions.RequestException as e:
        return f"Errore di connessione: {e}", f"Errore di connessione: {e}"
    except Exception as e:
        return f"Errore imprevisto: {e}", f"Errore imprevisto: {e}"


# --- Interfaccia Streamlit ---

st.title("METAR e TAF Viewer")

# Trigger per l'aggiornamento automatico ogni 5 minuti (300,000 ms)
st_autorefresh(interval=5 * 60 * 1000, key="data_refresh")

# Pulsante per forzare l'aggiornamento manuale
if st.button("Aggiorna Dati Manualmente"):
    # Svuota la cache per forzare il ricaricamento dei dati
    st.cache_data.clear()

uploaded_file = st.file_uploader("Carica il tuo file `airport_list.csv`", type=["csv"])

if uploaded_file is not None:
    try:
        airports_df = pd.read_csv(uploaded_file)
        
        # Verifica che le colonne 'ICAO' e 'Name' esistano
        if "ICAO" not in airports_df.columns or "Name" not in airports_df.columns:
            st.error("Il file CSV deve contenere le colonne 'ICAO' e 'Name'.")
        else:
            st.info(f"Trovati {len(airports_df)} aeroporti nel file. Caricamento dati...")
            
            for index, row in airports_df.iterrows():
                icao = row["ICAO"]
                name = row["Name"]
                
                st.subheader(f"{icao} - {name}")
                
                metar, taf = get_metar_taf(icao)
                
                st.text_area("METAR", metar, height=50, key=f"metar_{icao}_{index}")
                st.text_area("TAF", taf, height=150, key=f"taf_{icao}_{index}")
                st.markdown("---")

    except Exception as e:
        st.error(f"Errore durante la lettura del file CSV: {e}")
else:
    st.info("In attesa del caricamento di un file CSV.")

