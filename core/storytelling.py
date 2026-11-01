from __future__ import annotations

import re

STERNTALER = """Die Sterntaler

Es war einmal ein kleines Mädchen, das Vater und Mutter verloren hatte. Es war so arm, dass ihm außer den Kleidern, die es trug, nur noch ein Stück Brot geblieben war. Trotzdem ging es mutig hinaus in die Welt.

Bald begegnete ihm ein hungriger Mann. „Ach, gib mir etwas zu essen“, bat er. Das Mädchen reichte ihm sein ganzes Brot und sagte: „Es soll dir gut tun.“

Wenig später kam ein Kind, das am Kopf fror. Das Mädchen schenkte ihm seine Mütze. Dann traf es ein weiteres Kind ohne warmes Jäckchen und gab auch sein Jäckchen fort. Schließlich bat noch ein Kind um sein Röckchen. Weil das Mädchen glaubte, in der dunklen Nacht könne es niemand sehen, verschenkte es auch dieses.

Nun stand es allein im Wald. Über ihm funkelten unzählige Sterne. Plötzlich lösten sie sich vom Himmel und fielen als blanke Silbertaler zur Erde. Zugleich trug das Mädchen ein neues Hemd aus feinem Leinen. Es hielt den Saum auf und sammelte die Taler hinein.

Von da an musste es nie wieder hungern. Doch wichtiger als der neue Reichtum blieb ihm die Erinnerung daran, dass selbst in der dunkelsten Nacht ein freundliches Herz leuchten kann.

Der Wald wurde still, die Sterne standen wieder ruhig am Himmel, und das Mädchen schlief geborgen unter ihrem sanften Licht ein."""


WICHTELMAENNER = """Die Wichtelmänner

Es war einmal ein armer Schuster. Er hatte nur noch so viel Leder, dass er daraus ein einziges Paar Schuhe schneiden konnte. Am Abend legte er die zugeschnittenen Stücke auf seinen Werktisch. „Morgen mache ich mich an die Arbeit“, sagte er und ging schlafen.

Als er am nächsten Morgen in die Werkstatt kam, staunte er. Auf dem Tisch stand ein vollkommen fertiges Paar Schuhe. Jeder Stich saß genau, und das Leder war so sauber verarbeitet, wie er es selbst kaum vermocht hätte.

Schon bald kam ein Kunde, dem die Schuhe so gut gefielen, dass er mehr dafür bezahlte als verlangt. Von dem Geld kaufte der Schuster Leder für zwei weitere Paare. Wieder schnitt er es am Abend zu. Und wieder standen am Morgen fertige Schuhe auf dem Tisch.

So ging es viele Nächte lang. Der Schuster und seine Frau mussten bald keine Not mehr leiden. Eines Abends beschlossen sie, wach zu bleiben und herauszufinden, wer ihnen half. Sie versteckten sich hinter einem Vorhang.

Punkt Mitternacht kamen zwei kleine Wichtelmänner herein. Flink sprangen sie auf den Tisch, nähten, hämmerten und polierten, bis alle Schuhe fertig waren. Dann verschwanden sie wieder.

Der Schuster und seine Frau wollten sich bedanken. Sie nähten den Wichtelmännern kleine Hemden, Jacken und Hosen und stellten winzige Schuhe dazu. Als die beiden in der nächsten Nacht ihre Geschenke fanden, zogen sie alles voller Freude an. Sie tanzten durch die Werkstatt und liefen lachend hinaus.

Von diesem Tag an kamen sie nicht wieder. Doch der Schuster arbeitete fleißig weiter, und das Glück blieb bei ihm. Wenn es nachts in der Werkstatt leise knarrte, lächelten er und seine Frau und dachten dankbar an ihre kleinen Freunde."""


def local_story_response(message: str) -> str | None:
    """Liefert für eindeutige Grimm-/Gute-Nacht-Wünsche saubere lokale Prosa."""
    clean = " ".join(str(message or "").strip().split()).casefold()
    if not clean:
        return None

    is_story = bool(
        re.search(
            r"\b(?:märchen|maerchen|gutenachtgeschichte|gute[- ]nacht[- ]geschichte)\b",
            clean,
        )
        or re.search(
            r"\b(?:brüder|gebrüder|brueder|gebrueder)\s+grimm?\b",
            clean,
        )
        or re.search(
            r"\berzähl\w*\b.{0,80}\b(?:eine|eine kurze|eine kleine)\s+geschichte\b",
            clean,
        )
    )
    if not is_story:
        return None

    if re.search(r"\b(?:wichtel|nochmal|noch eine|weitere)\b", clean):
        return WICHTELMAENNER
    return STERNTALER
