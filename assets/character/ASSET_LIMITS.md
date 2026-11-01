# EVA · Herkunft und Grenzen der Charakterassets

Die Körperposen stammen aus den zehn Original-PNGs der vom Nutzer
bereitgestellten `eva.zip`. Sie wurden einschließlich Alphakanal unverändert
übernommen: keine Neuzeichnung, Freistellung, Zuschnitte oder ergänzten Körperteile.
Die Bilder sind 1254 × 1254 Pixel groß, die Standpose 1024 × 1536 und die
Schlafpose 1448 × 1086 Pixel. Die App skaliert sie proportional zur Anzeige.

Die aktiven Bilder liegen unter `assets/character/poses/`. Das Manifest
`outfits/gothic.json` dokumentiert für jeden Zustand den Dateinamen in der
Original-ZIP, die Auflösung und die SHA-256-Prüfsumme. Identische Zustände
verwenden dieselbe PNG-Datei, statt zusätzliche Bildkopien zu laden oder zu
verpacken. Die ursprüngliche ZIP, frühere Körperposen und verworfene Entwürfe
liegen in der externen Bereinigungssicherung unter `eva-backups/` neben dem
Projekt; sie gehören nicht zum Windows-Paket. Details stehen in
`docs/PROJECT_CLEANUP.md` im Quellprojekt.

| Originaldatei in eva.zip | Verwendung |
| --- | --- |
| image-gen-1(20261031-225350).png | Stehen; Aufstehen als statischer Ersatz |
| image-gen-2(20261031-225352).png | Sitzen; Hinsetzen, Aufmerksam und Genervt als Ersatz |
| image-gen-3(20261031-225354).png | Zuhören und Nachdenken; Antworten als statischer Ersatz |
| image-gen-4(20261031-225356).png | Freuen |
| image-gen-5(9).png | Lesen |
| image-gen-6(6).png | Tippen / Arbeiten |
| image-gen-7(5).png | Müde |
| image-gen-8(5).png | Schlafen; Einschlafen als statischer Ersatz |
| image-gen-9(3).png | Strecken |
| image-gen-10(3).png | Winken |

Die acht separaten Ausdrucksporträts bleiben erhalten. Sie stammen weiterhin
aus der früheren Freistellung des Gothic-Character-Sheets mit dem eingebauten
Bildwerkzeug. Für diese Porträts ist Pixelgleichheit zur Vorlage nicht
garantiert. Quellen und Aufträge liegen unter `assets/references/`.

## Bewusste Einschränkungen

- Alle Posen sind **statische Einzelbilder**. Blink-, Atem-, Haar-, Lauf- und
  Mundbewegungsframes sowie Übergangsanimationen fehlen. Aufstehen, Hinsetzen
  und Einschlafen sind deshalb gekennzeichnete statische Ersatzposen.
- Antworten verwendet die Zuhörpose ohne vorgetäuschte Lippensynchronisation.
  Für Genervt fehlt eine Körperpose; das separate Porträt bleibt verfügbar.
- Transparente Ränder und sonstige Bilddetails der gelieferten PNGs bleiben
  unverändert. Sitz-/Fußanker orientieren sich am sichtbaren mittleren
  Bodenkontakt, nicht am transparenten Bildrand. Ein Feinabgleich von −24 bis
  +24 Pixeln ist in den Einstellungen verfügbar; positive Werte verschieben
  EVA nach unten.
- Der Animationsschalter spielt erst dann Bewegungen ab, wenn ein Outfit
  mehrere echte PNG-Frames pro Pose bereitstellt.

Die früheren Roboter- und anderen Charakterentwürfe werden nicht verwendet.
