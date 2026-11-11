# boot.py - Raspberry Pi Pico (CircuitPython 10) - BOT SPARATUTTO
#
# Viene letto SOLO quando attacchi la schedina (non quando salvi i file).
# Accende una seconda porta USB "dati": da li' il programma sul PC manda i
# comandi (premi questo tasto, muovi il mouse...). La schedina resta anche
# tastiera + mouse e chiavetta CIRCUITPY come prima.
#
# Dopo aver copiato questo file: STACCA e RIATTACCA la schedina.

import usb_cdc

usb_cdc.enable(console=True, data=True)
