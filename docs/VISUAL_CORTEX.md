# Visual Cortex

Der Desktop-Client trennt Face Presence (`visual_cortex.presence`) und Identity Recognition (`visual_cortex.identity`). Zustände sind:

- `ABSENT`
- `PRESENT_UNKNOWN`
- `PRESENT_USER`

Identity-Ergebnisse enthalten Name und Confidence. Die leichte OpenCV-Implementierung erzeugt lokal einen normalisierten Deskriptor aus dem größten erkannten Gesicht. Enrollment speichert nur diese Deskriptoren in der ignorierten Datei `data/faces.json`; Kameraframes werden nicht gespeichert.

```bash
pip install -r requirements-optional.txt
python3 -m sentry.enroll Tim
EVA_VISUAL_CORTEX_ENABLED=true python3 -m visual_cortex.run
```

`VisualConfig.save_frames` und `EVA_VISUAL_SAVE_FRAMES` sind standardmäßig `false`. Es gibt keine automatische Sammlung fremder Gesichter. Unknown und Visitor erhalten mit `EVA_PROFILE_MEMORY_ISOLATION=true` keinen privaten Memory-Kontext; registrierte Profile dürfen personalisierten Kontext nutzen. Diese Zuordnung dient Begrüßung, Profil und Memory-Auswahl, niemals sicherheitskritischer Autorisierung.
