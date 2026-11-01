"""Exercise the live bridge with the reported conversation regressions and a synthetic screen.

Runs on the server. The only image is created in RAM; no user's real screen is read.
Optional development dependency: Pillow. No model or token is copied to Windows.
"""

from __future__ import annotations

import base64
import io
import json
import time

from PIL import Image, ImageDraw, ImageFont

from desktop_agent.companion_client import CompanionClient
from tools.setup_desktop_bridge import ROOT, env_values


def main():
    values = env_values(ROOT / ".env")
    client = CompanionClient(
        f"http://{values['EVA_COMPANION_HOST']}:{values['EVA_COMPANION_PORT']}",
        values["EVA_COMPANION_TOKEN"],
    )
    image = Image.new("RGB", (1200, 720), "#eeeeee")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
    draw.rounded_rectangle((65, 60, 1135, 655), radius=16, fill="white", outline="black", width=3)
    draw.text((100, 90), "EVA TESTFENSTER", fill="black", font=font)
    draw.text((100, 170), "Status: OFFLINE", fill="black", font=font)
    draw.rectangle((110, 280, 1080, 590), fill="#00bb22")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    bad_history = [
        {"role": "user", "content": "wie geht es dir"},
        {
            "role": "assistant",
            "content": "Ich bin EVA, der weiblichen KI-Assistentin des EVA-Projekts. Ich habe die angezeigte Desktop-Oberfläche analysiert. Ich kann dir helfen, wenn du möchtest.",
        },
    ]
    cases = [
        ("smalltalk", "wie geht es dir", []),
        ("repair_legacy_history", "ich habe gefragt wie es dir geht", bad_history),
        ("simple_math", "was ist 5+5", bad_history),
        ("everyday_frustration", "Heute war echt ein langer und stressiger Arbeitstag.", []),
        (
            "screen",
            "Was siehst du auf meinem Monitor? Nenne nur den Fenstertitel, den Status und die Farbe der Fläche.",
            [],
        ),
    ]
    report = {"status": client.status(), "cases": []}
    for name, question, history in cases:
        started = time.monotonic()
        # Include the image even in text requests to emulate the installed older
        # client. The server must suppress it for unrelated conversation.
        response = "".join(client.stream(question, history, encoded))
        row = {
            "case": name,
            "question": question,
            "answer": response,
            "seconds": round(time.monotonic() - started, 2),
        }
        print(json.dumps(row, ensure_ascii=False), flush=True)
        report["cases"].append(row)
    path = ROOT / "data/benchmarks/desktop-dialog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in report["cases"]:
        answer = row["answer"].casefold()
        if row["case"] in {"smalltalk", "repair_legacy_history"}:
            assert len(answer) <= 220 and all(
                word not in answer
                for word in ("ich bin eva", "desktop", "analysiert", "weiblichen ki-assistentin")
            ), row
        elif row["case"] == "simple_math":
            assert "10" in answer and len(answer) <= 100 and "bereits" not in answer, row
        elif row["case"] == "everyday_frustration":
            assert len(answer) <= 400 and all(
                word not in answer
                for word in ("oder:", "monster", "ich bin eva", "gerade gerade", "analysiert")
            ), row
        else:
            assert (
                "offline" in answer
                and ("grün" in answer or "gruen" in answer)
                and "testfenster" in answer
            ), row
            assert "meinem monitor" not in answer and "analysiert" not in answer, row
    print(f"Live-Regressionsprüfung bestanden. Bericht: {path}")


if __name__ == "__main__":
    main()
