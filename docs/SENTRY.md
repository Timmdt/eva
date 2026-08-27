# Sentry und Power Grid

Sentry läuft auf dem kleinen lokalen Server. `RTSPCamera` reduziert den Stream auf 1–5 Detection-FPS, skaliert Frames und verbindet bei Abbruch neu. Presence Detection nutzt OpenCV HOG. Im Modus `presence_only` reicht eine erkannte Person; `recognized_user` verlangt eine bewusst registrierte lokale Identity.

## Ablauf

1. Presence wird erkannt.
2. `ServerStatus` prüft bevorzugt `EVA_HEALTH_URL`, sonst Ping.
3. Nur wenn der große Server nicht bereit ist, sendet `WakeOnLan` ein Magic Packet.
4. Ein Cooldown verhindert Packet-Spam.
5. Nach dem Presence-Timeout wird eine Sleep-Anfrage erzeugt.

Shutdown ist nur möglich, wenn Sentry aktiviert ist, keine EVA-Anfrage, Ingestion oder kritische Aufgabe läuft, keine Keep-Awake-/Inhibit-Datei existiert und die Boot-Grace abgelaufen ist. Mit `EVA_SENTRY_ALLOW_SHUTDOWN=false` wird ausschließlich `Would shut down server now.` geloggt. Erst ein bewusst gesetztes `true` erlaubt `systemctl poweroff`.

Keep awake:

```bash
touch /tmp/eva_keep_awake
# später manuell entfernen
rm /tmp/eva_keep_awake
```

Die Vorlagen `deployment/systemd/eva.service` und `eva-sentry.service` werden nicht automatisch installiert oder gestartet. Zugangsdaten, MAC und IP gehören ausschließlich in die lokale `.env`.
