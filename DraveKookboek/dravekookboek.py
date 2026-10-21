# -*- coding: utf-8 -*-
# DraveKookboek - je eigen recepten, groot en duidelijk, met kookstand, voorlezen en kookwekkers.
# Copyright (C) 2026 Dravenlock (Roger & Claudio). Vrije software onder de GNU GPL v3.0.
"""DraveKookboek: een kookboek voor op de pc in de keuken.

- Recepten met ingrediënten, stappen, tijd, aantal personen en een foto.
- Personen aanpassen: de hoeveelheden rekenen vanzelf mee.
- Kookstand: één stap tegelijk, heel groot. Spatie / pijltjes = volgende stap.
  Staat er een tijd in een stap ("10 minuten")? Dan krijg je een knop voor een kookwekker.
- Voorlezen van de stap (neurale stem, offline).
- Boodschappenlijst van een of meer recepten.
- Alles wordt bewaard als gewone bestanden in Documenten\\DraveKookboek. Er gaat niets naar internet.
"""
import datetime
import json
import os
import re
import shutil
import sys
import time
from fractions import Fraction

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QMarginsF
from PyQt6.QtGui import QIcon, QPixmap, QKeySequence, QShortcut, QTextDocument, QPageLayout, QPageSize, QFont
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                             QListWidget, QListWidgetItem, QLineEdit, QComboBox, QSpinBox, QTextBrowser, QDialog,
                             QFormLayout, QPlainTextEdit, QFileDialog, QMessageBox, QSplitter, QInputDialog,
                             QCheckBox, QTextEdit, QScrollArea, QFrame)

APP_NAAM = "DraveKookboek"
APP_VERSION = "1.0.1"
BG, PANEL, ZILVER, GRIJS, ACCENT, GOUD, GROEN = "#0e0e11", "#16161b", "#e6e6ea", "#8a8a94", "#6fa3d6", "#ffb347", "#5ad988"
CATEGORIEEN = ["Ontbijt", "Lunch", "Soep", "Hoofdgerecht", "Bijgerecht", "Salade", "Nagerecht", "Bakken", "Snacks",
               "Drinken", "Sauzen", "Overig"]


def app_map():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def bron(naam):
    for b in (getattr(sys, "_MEIPASS", None), app_map()):
        if b and os.path.exists(os.path.join(b, naam)):
            return os.path.join(b, naam)
    return os.path.join(app_map(), naam)


def documenten():
    try:
        import ctypes
        buf = ctypes.c_wchar_p()
        guid = (ctypes.c_ubyte * 16).from_buffer_copy(b"\xd0\x9a\xd3\xfd\x8f\x23\xaf\x46\xad\xb4\x6c\x85\x48\x03\x69\xc7")
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(buf)) == 0:
            p = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return p
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def data_map():
    p = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "DraveKookboek")
    os.makedirs(p, exist_ok=True)
    return p


CFG = os.path.join(data_map(), "instellingen.json")


def lees_cfg():
    c = dict(map=os.path.join(documenten(), "DraveKookboek"), letter=20, stem="Cole", snelheid=0.85, voorlezen=True)
    try:
        with open(CFG, encoding="utf-8-sig") as f:
            c.update(json.load(f))
    except Exception:
        pass
    if not c.get("snelheid_v2"):  # 1.0 las iets te snel voor
        c["snelheid"], c["snelheid_v2"] = 0.85, True
    return c


def bewaar_cfg(c):
    try:
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def veilige_naam(t):
    return (re.sub(r'[\\/:*?"<>|]+', "", t).strip().strip(".") or "Recept")[:80]


def esc(t):
    import html
    return html.escape(t or "")


# ------------------------------------------------------------------ hoeveelheden omrekenen
_GETAL = re.compile(r"^(\s*)(\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)(\s*-\s*(\d+(?:[.,]\d+)?))?")
_BREUK = {Fraction(1, 2): "½", Fraction(1, 4): "¼", Fraction(3, 4): "¾", Fraction(1, 3): "⅓", Fraction(2, 3): "⅔", Fraction(1, 8): "⅛"}


def _lees_getal(s):
    s = s.strip().replace(",", ".")
    if " " in s:
        a, b = s.split()
        return Fraction(a) + Fraction(b)
    return Fraction(s)


def _toon_getal(f):
    if f <= 0:
        return "0"
    heel = int(f)
    rest = f - heel
    # naar een nette breuk afronden als dat dichtbij is
    for br, teken in _BREUK.items():
        if abs(rest - br) < Fraction(1, 40):
            return ("%d%s" % (heel, teken)) if heel else teken
    if abs(rest) < Fraction(1, 24):
        return str(heel)
    if abs(rest - 1) < Fraction(1, 24):
        return str(heel + 1)
    x = float(f)
    return ("%.1f" % x).replace(".", ",") if x < 10 else str(round(x))


def schaal_regel(regel, factor):
    """'200 g bloem' * 1.5 -> '300 g bloem'. Regels zonder getal blijven gelijk."""
    if factor == 1:
        return regel
    s = regel.replace("½", "1/2").replace("¼", "1/4").replace("¾", "3/4")
    m = _GETAL.match(s)
    if not m:
        return regel
    try:
        a = _lees_getal(m.group(2)) * factor
        uit = m.group(1) + _toon_getal(a)
        if m.group(4):
            uit += "-" + _toon_getal(_lees_getal(m.group(4)) * factor)
        return uit + s[m.end():]
    except Exception:
        return regel


_TIJD = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*(?:à|a|-|tot)\s*(\d+(?:[.,]\d+)?))?\s*(uur|u\b|minuten|minuut|min\b|seconden|sec\b)",
                   re.IGNORECASE)


def tijden_in(tekst):
    """Vindt tijden in een stap: [(label, seconden), ...]. Bij '10-12 minuten' telt de hoogste."""
    uit = []
    for m in _TIJD.finditer(tekst):
        getal = float((m.group(2) or m.group(1)).replace(",", "."))
        eenheid = m.group(3).lower()
        sec = getal * (3600 if eenheid.startswith("u") else 1 if eenheid.startswith("s") else 60)
        if 0 < sec <= 24 * 3600:
            uit.append((m.group(0).strip(), int(sec)))
    return uit


_AFKORT = [  # (patroon, uitgesproken) - alleen voor voorlezen, het scherm blijft kort
    (r"\bel\b", "eetlepel"), (r"\beetl\b", "eetlepel"), (r"\btl\b", "theelepel"), (r"\btheel\b", "theelepel"),
    (r"\bkl\b", "koffielepel"), (r"\bkg\b", "kilo"), (r"\bgr?\b", "gram"), (r"\bmg\b", "milligram"),
    (r"\bml\b", "milliliter"), (r"\bcl\b", "centiliter"), (r"\bdl\b", "deciliter"), (r"\bl\b", "liter"),
    (r"\bst\b", "stuks"), (r"\bstk\b", "stuks"), (r"\bpers\b", "personen"), (r"\bmin\b", "minuten"),
    (r"\bsec\b", "seconden"), (r"(\d)\s*u\b", r"\1 uur"), (r"\bca\b", "ongeveer"), (r"\bevt\b", "eventueel"),
    (r"\bbijv\b", "bijvoorbeeld"), (r"\bmsp\b", "mespuntje"), (r"(\d)\s*°C?", r"\1 graden"),
    (r"(\d)\s*-\s*(\d)", r"\1 tot \2"),
]
_UITSPRAAK_BREUK = [("1½", "anderhalf"), ("½", " een half"), ("¼", " een kwart"), ("¾", " driekwart"),
                    ("⅓", " een derde"), ("⅔", " twee derde"), ("⅛", " een achtste"), ("1/2", "een half"),
                    ("1/4", "een kwart"), ("3/4", "driekwart")]


def uitspreekbaar(t):
    """Maakt tekst geschikt om voor te lezen: afkortingen en breuken voluit."""
    for a, b in _UITSPRAAK_BREUK:
        t = t.replace(a, b)
    t = re.sub(r"\b(min|sec|bijv|ca|evt|msp|pers|el|tl|gr)\.(?=\s+[a-z0-9à-ü])", r"\1", t)
    for pat, rep in _AFKORT:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    t = re.sub(r"(\d),(\d)", r"\1 komma \2", t)
    return re.sub(r"\s+", " ", t).strip()


def mmss(sec):
    sec = max(0, int(sec))
    return ("%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)) if sec >= 3600 else "%d:%02d" % (sec // 60, sec % 60)


# ------------------------------------------------------------------ recepten op schijf
VOORBEELDEN = [
    dict(titel="Pannenkoeken", categorie="Hoofdgerecht", personen=4, tijd="30 minuten",
         ingredienten=["500 g bloem", "1 l melk", "3 eieren", "1 snufje zout", "boter om te bakken"],
         stappen=["Doe de bloem en het zout in een kom. Maak een kuiltje in het midden.",
                  "Breek de eieren in het kuiltje. Giet er een scheutje melk bij en roer tot een glad deeg.",
                  "Roer de rest van de melk er beetje bij beetje door. Laat het beslag 15 minuten rusten.",
                  "Smelt een klontje boter in een hete koekenpan. Schep er een soeplepel beslag in en draai de pan rond.",
                  "Bak de pannenkoek ongeveer 2 minuten per kant, tot hij goudbruin is. Herhaal met de rest."],
         notities="Lekker met stroop, poedersuiker of appel. Dit is een voorbeeldrecept: je mag het aanpassen of weggooien."),
    dict(titel="Tomatensoep", categorie="Soep", personen=4, tijd="40 minuten",
         ingredienten=["1 kg rijpe tomaten", "1 ui", "2 tenen knoflook", "2 el olijfolie", "1 l groentebouillon",
                       "1 tl suiker", "peper en zout"],
         stappen=["Snijd de ui en de knoflook fijn. Snijd de tomaten in stukken.",
                  "Verhit de olie in een soeppan en fruit de ui en knoflook 5 minuten.",
                  "Doe de tomaten, de bouillon en de suiker erbij. Laat 20 minuten zachtjes koken.",
                  "Pureer de soep met een staafmixer. Breng op smaak met peper en zout."],
         notities="Voorbeeldrecept. Lekker met wat basilicum of een scheutje room."),
]


class Kookboek:
    def __init__(self, map_):
        self.map = map_
        self.rmap = os.path.join(map_, "recepten")
        self.fmap = os.path.join(map_, "fotos")
        nieuw = not os.path.isdir(self.rmap)
        os.makedirs(self.rmap, exist_ok=True)
        os.makedirs(self.fmap, exist_ok=True)
        if nieuw:
            for r in VOORBEELDEN:
                self.bewaar(dict(r))

    def alle(self):
        uit = []
        for f in os.listdir(self.rmap):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(self.rmap, f), encoding="utf-8-sig") as h:
                        r = json.load(h)
                    r["_bestand"] = f
                    uit.append(r)
                except Exception:
                    pass
        return sorted(uit, key=lambda r: r.get("titel", "").lower())

    def bewaar(self, r):
        if not r.get("_bestand"):
            stam = veilige_naam(r.get("titel", "Recept"))
            naam, n = stam + ".json", 2
            while os.path.exists(os.path.join(self.rmap, naam)):
                naam, n = "%s (%d).json" % (stam, n), n + 1
            r["_bestand"] = naam
        r["gewijzigd"] = datetime.datetime.now().isoformat(timespec="seconds")
        schoon = {k: v for k, v in r.items() if not k.startswith("_")}
        p = os.path.join(self.rmap, r["_bestand"])
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(schoon, f, ensure_ascii=False, indent=1)
        os.replace(p + ".tmp", p)
        return r

    def weg(self, r):
        prul = os.path.join(self.map, "_verwijderd")
        os.makedirs(prul, exist_ok=True)
        try:
            shutil.move(os.path.join(self.rmap, r["_bestand"]),
                        os.path.join(prul, datetime.datetime.now().strftime("%Y%m%d-%H%M%S_") + r["_bestand"]))
        except Exception:
            pass

    def foto_pad(self, r):
        f = r.get("foto")
        return os.path.join(self.fmap, f) if f else None


# ------------------------------------------------------------------ recept bewerken
class Bewerk(QDialog):
    def __init__(self, ouder, boek, r=None):
        super().__init__(ouder)
        self.boek = boek
        self.r = dict(r or {})
        self.setWindowTitle("Recept bewerken" if r else "Nieuw recept")
        self.resize(900, 860)
        f = QFormLayout(self)
        self.titel = QLineEdit(self.r.get("titel", ""))
        f.addRow("Naam", self.titel)
        self.cat = QComboBox()
        self.cat.setEditable(True)
        self.cat.addItems(CATEGORIEEN)
        self.cat.setCurrentText(self.r.get("categorie", "Hoofdgerecht"))
        f.addRow("Soort", self.cat)
        rij = QHBoxLayout()
        self.pers = QSpinBox()
        self.pers.setRange(1, 50)
        self.pers.setValue(int(self.r.get("personen", 4)))
        rij.addWidget(self.pers)
        rij.addWidget(QLabel("   Tijd:"))
        self.tijd = QLineEdit(self.r.get("tijd", ""))
        self.tijd.setPlaceholderText("bijv. 45 minuten")
        rij.addWidget(self.tijd, 1)
        f.addRow("Personen", rij)
        self.ingr = QPlainTextEdit("\n".join(self.r.get("ingredienten", [])))
        self.ingr.setPlaceholderText("Eén ingrediënt per regel, met het getal vooraan:\n200 g bloem\n2 eieren\n1/2 ui")
        f.addRow("Ingrediënten", self.ingr)
        self.stappen = QPlainTextEdit("\n".join(self.r.get("stappen", [])))
        self.stappen.setPlaceholderText("Eén stap per regel. Noem tijden gewoon, bijv. 'Laat 10 minuten koken.'\n"
                                        "Dan krijg je in de kookstand een kookwekker.")
        f.addRow("Stappen", self.stappen)
        self.notitie = QPlainTextEdit(self.r.get("notities", ""))
        self.notitie.setMaximumHeight(110)
        f.addRow("Notities", self.notitie)
        frij = QHBoxLayout()
        self.foto_lbl = QLabel(self.r.get("foto") or "geen foto")
        frij.addWidget(self.foto_lbl, 1)
        k = QPushButton("Foto kiezen...")
        k.clicked.connect(self._foto)
        frij.addWidget(k)
        k = QPushButton("Geen foto")
        k.clicked.connect(lambda: (self.r.pop("foto", None), self.foto_lbl.setText("geen foto")))
        frij.addWidget(k)
        f.addRow("Foto", frij)
        self._nieuwe_foto = None
        knoppen = QHBoxLayout()
        knoppen.addStretch(1)
        n = QPushButton("Annuleren")
        n.clicked.connect(self.reject)
        j = QPushButton("Bewaren")
        j.setObjectName("hoofd")
        j.clicked.connect(self._ok)
        knoppen.addWidget(n)
        knoppen.addWidget(j)
        f.addRow(knoppen)

    def _foto(self):
        p, _ = QFileDialog.getOpenFileName(self, "Foto", os.path.join(os.path.expanduser("~"), "Pictures"),
                                           "Foto's (*.jpg *.jpeg *.png *.webp *.bmp)")
        if p:
            self._nieuwe_foto = p
            self.foto_lbl.setText(os.path.basename(p))

    def _ok(self):
        if not self.titel.text().strip():
            QMessageBox.information(self, APP_NAAM, "Geef het recept een naam.")
            return
        r = self.r
        r.update(titel=self.titel.text().strip(), categorie=self.cat.currentText().strip() or "Overig",
                 personen=self.pers.value(), tijd=self.tijd.text().strip(),
                 ingredienten=[x.strip() for x in self.ingr.toPlainText().splitlines() if x.strip()],
                 stappen=[x.strip() for x in self.stappen.toPlainText().splitlines() if x.strip()],
                 notities=self.notitie.toPlainText().strip())
        if self._nieuwe_foto:
            naam = veilige_naam(r["titel"]) + "_" + datetime.datetime.now().strftime("%H%M%S") + \
                os.path.splitext(self._nieuwe_foto)[1].lower()
            try:
                shutil.copy2(self._nieuwe_foto, os.path.join(self.boek.fmap, naam))
                r["foto"] = naam
            except Exception as e:
                QMessageBox.warning(self, APP_NAAM, "Foto kopiëren lukt niet:\n%s" % e)
        self.r = self.boek.bewaar(r)
        self.accept()


# ------------------------------------------------------------------ kookwekkers
class Wekkers(QObject):
    veranderd = pyqtSignal()
    af = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.lijst = []  # [label, eindtijd, totaal]
        self.klok = QTimer()
        self.klok.timeout.connect(self._tik)
        self.klok.start(500)
        self._bel = QTimer()
        self._bel.timeout.connect(self._piep)
        self._bellen = 0

    def nieuw(self, label, sec):
        self.lijst.append([label, time.time() + sec, sec])
        self.veranderd.emit()

    def stop(self, i):
        if 0 <= i < len(self.lijst):
            self.lijst.pop(i)
        self.veranderd.emit()

    def _tik(self):
        nu = time.time()
        for w in list(self.lijst):
            if w[1] <= nu:
                self.lijst.remove(w)
                self._bellen = 12
                self._bel.start(700)
                self.af.emit(w[0])
        self.veranderd.emit()

    def _piep(self):
        self._bellen -= 1
        try:
            import winsound
            winsound.Beep(880, 250)
            winsound.Beep(1175, 250)
        except Exception:
            QApplication.beep()
        if self._bellen <= 0:
            self._bel.stop()

    def stil(self):
        self._bellen = 0
        self._bel.stop()


class WekkerBalk(QWidget):
    def __init__(self, wekkers):
        super().__init__()
        self.w = wekkers
        self.setObjectName("wekkers")
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(12, 6, 12, 6)
        wekkers.veranderd.connect(self.ververs)
        self.knoppen = []
        self.ververs()

    def ververs(self):
        lijst = self.w.lijst
        while len(self.knoppen) < len(lijst):
            b = QPushButton()
            b.setObjectName("wekker")
            i = len(self.knoppen)
            b.clicked.connect(lambda _=False, i=i: self._klik(i))
            self.lay.addWidget(b)
            self.knoppen.append(b)
        for i, b in enumerate(self.knoppen):
            if i < len(lijst):
                b.setText("⏱  %s   %s   ✕" % (lijst[i][0], mmss(lijst[i][1] - time.time())))
                b.show()
            else:
                b.hide()
        self.setVisible(bool(lijst))

    def _klik(self, i):
        if i < len(self.w.lijst) and QMessageBox.question(self, "Kookwekker", "Deze kookwekker stoppen?") \
                == QMessageBox.StandardButton.Yes:
            self.w.stop(i)


# ------------------------------------------------------------------ kookstand
class Kookstand(QDialog):
    def __init__(self, ouder, r, factor):
        super().__init__(ouder)
        self.ouder, self.r, self.factor = ouder, r, factor
        self.setWindowTitle("Kookstand - " + r.get("titel", ""))
        self.stappen = ["__ingr__"] + list(r.get("stappen", [])) + ["__klaar__"]
        self.i = 0
        l = QVBoxLayout(self)
        l.setContentsMargins(40, 24, 40, 24)
        self.kop = QLabel()
        self.kop.setObjectName("kkop")
        l.addWidget(self.kop)
        self.tekst = QLabel()
        self.tekst.setObjectName("kstap")
        self.tekst.setWordWrap(True)
        self.tekst.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.tekst.setTextFormat(Qt.TextFormat.RichText)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(self.tekst)
        l.addWidget(sc, 1)
        self.tijdrij = QHBoxLayout()
        l.addLayout(self.tijdrij)
        self.wbalk = WekkerBalk(ouder.wekkers)
        l.addWidget(self.wbalk)
        rij = QHBoxLayout()
        for tekst, fn in (("◀  Vorige", lambda: self.ga(-1)), ("🔊  Voorlezen", self.lees), ("■  Stil", ouder.stil),
                          ("⏱  Eigen kookwekker", self.eigen_wekker), ("✕  Sluiten (Esc)", self.close)):
            b = QPushButton(tekst)
            b.clicked.connect(fn)
            rij.addWidget(b)
        self.volgende = QPushButton("Volgende  ▶")
        self.volgende.setObjectName("hoofd")
        self.volgende.clicked.connect(lambda: self.ga(1))
        rij.addWidget(self.volgende)
        l.addLayout(rij)
        for toets, fn in (("Right", lambda: self.ga(1)), ("Space", lambda: self.ga(1)), ("Return", lambda: self.ga(1)),
                          ("Left", lambda: self.ga(-1)), ("Backspace", lambda: self.ga(-1)), ("L", self.lees),
                          ("F5", self.lees), ("T", self.eigen_wekker), ("Escape", self.close)):
            QShortcut(QKeySequence(toets), self, activated=fn)
        self.setStyleSheet(ouder.styleSheet() + """
            QDialog { background:#000; } QLabel#kkop { font-size:26px; color:%s; font-weight:700; }
            QLabel#kstap { font-size:%dpx; color:white; line-height:150%%; background:#000; }
            QPushButton { font-size:22px; padding:14px 22px; } QPushButton#tijd { background:%s; color:#000; font-weight:700; }
        """ % (GOUD, max(34, int(ouder.cfg["letter"]) * 2), GOUD))
        self.showFullScreen()
        self.toon()

    def _stap_html(self):
        s = self.stappen[self.i]
        if s == "__ingr__":
            pers = round(int(self.r.get("personen", 4)) * self.factor)
            regels = "".join("<li>%s</li>" % esc(schaal_regel(x, self.factor)) for x in self.r.get("ingredienten", []))
            return "Zet eerst alles klaar (voor %d personen):<ul>%s</ul>" % (pers, regels), \
                "Zet eerst alles klaar. Je hebt nodig: " + ", ".join(schaal_regel(x, self.factor)
                                                                     for x in self.r.get("ingredienten", [])) + "."
        if s == "__klaar__":
            return "Klaar! Eet smakelijk. 🍽️" + ("<p style='font-size:60%%;color:#aaa'>%s</p>" % esc(self.r["notities"])
                                                 if self.r.get("notities") else ""), "Klaar! Eet smakelijk."
        return esc(s), s

    def toon(self):
        n = len(self.stappen) - 2
        self.kop.setText(self.r.get("titel", "") + ("   ·   Klaarzetten" if self.i == 0 else
                                                    "   ·   Klaar" if self.i == len(self.stappen) - 1 else
                                                    "   ·   Stap %d van %d" % (self.i, n)))
        html_, self._spreek = self._stap_html()
        self.tekst.setText(html_)
        while self.tijdrij.count():
            w = self.tijdrij.takeAt(0).widget()
            if w:
                w.deleteLater()
        s = self.stappen[self.i]
        if not s.startswith("__"):
            for label, sec in tijden_in(s):
                b = QPushButton("⏱  Kookwekker %s" % label)
                b.setObjectName("tijd")
                b.clicked.connect(lambda _=False, label=label, sec=sec: self.ouder.wekkers.nieuw(
                    "Stap %d: %s" % (self.i, label), sec))
                self.tijdrij.addWidget(b)
            self.tijdrij.addStretch(1)
        self.volgende.setEnabled(self.i < len(self.stappen) - 1)
        if self.ouder.cfg.get("voorlezen"):
            self.lees()

    def ga(self, d):
        j = self.i + d
        if 0 <= j < len(self.stappen):
            self.i = j
            self.ouder.stil()
            self.toon()

    def lees(self):
        self.ouder.zeg(self._spreek)

    def eigen_wekker(self):
        m, ok = QInputDialog.getInt(self, "Kookwekker", "Hoeveel minuten?", 10, 1, 600)
        if ok:
            self.ouder.wekkers.nieuw("%d min" % m, m * 60)

    def closeEvent(self, e):
        self.ouder.stil()
        e.accept()


# ------------------------------------------------------------------ boodschappenlijst
class Boodschappen(QDialog):
    def __init__(self, ouder, recepten):
        super().__init__(ouder)
        self.setWindowTitle("Boodschappenlijst")
        self.resize(760, 760)
        self.recepten = recepten
        l = QVBoxLayout(self)
        l.addWidget(QLabel("Vink de recepten aan. Aantal personen kun je per recept aanpassen."))
        self.rijen = []
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        binnen = QWidget()
        bl = QVBoxLayout(binnen)
        for r in recepten:
            rij = QHBoxLayout()
            c = QCheckBox(r.get("titel", ""))
            s = QSpinBox()
            s.setRange(1, 50)
            s.setValue(int(r.get("personen", 4)))
            s.setSuffix(" pers.")
            c.toggled.connect(self.maak)
            s.valueChanged.connect(self.maak)
            rij.addWidget(c, 1)
            rij.addWidget(s)
            bl.addLayout(rij)
            self.rijen.append((c, s, r))
        bl.addStretch(1)
        sc.setWidget(binnen)
        sc.setMaximumHeight(260)
        l.addWidget(sc)
        self.lijst = QPlainTextEdit()
        l.addWidget(self.lijst, 1)
        rij = QHBoxLayout()
        for tekst, fn in (("📋  Kopiëren", self.kopieer), ("🖨  Afdrukken / PDF", self.pdf), ("Sluiten", self.accept)):
            b = QPushButton(tekst)
            b.clicked.connect(fn)
            rij.addWidget(b)
        l.addLayout(rij)

    def kies(self, r):
        for c, s, x in self.rijen:
            if x is r:
                c.setChecked(True)

    def maak(self):
        regels = []
        for c, s, r in self.rijen:
            if c.isChecked():
                f = s.value() / max(1, int(r.get("personen", 4)))
                regels.append("— %s (%d pers.)" % (r.get("titel", ""), s.value()))
                regels += ["☐ " + schaal_regel(x, f) for x in r.get("ingredienten", [])]
                regels.append("")
        self.lijst.setPlainText("\n".join(regels))

    def kopieer(self):
        QApplication.clipboard().setText(self.lijst.toPlainText())

    def pdf(self):
        self.parent().naar_pdf("Boodschappen", "<h1>Boodschappenlijst</h1><pre style='font-size:14pt'>%s</pre>"
                               % esc(self.lijst.toPlainText()))


# ------------------------------------------------------------------ hoofdvenster
class Kook(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = lees_cfg()
        self.boek = Kookboek(self.cfg["map"])
        self.stem = None
        self.recepten = []
        self.r = None
        self.wekkers = Wekkers()
        self.wekkers.af.connect(self._wekker_af)
        self.setWindowTitle(APP_NAAM)
        self.setWindowIcon(QIcon(bron(os.path.join("assets", "icon.ico"))))
        self.resize(1400, 900)
        self._bouw()
        self._stijl()
        self.laad()

    def _bouw(self):
        w = QWidget()
        self.setCentralWidget(w)
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)
        balk = QWidget()
        balk.setObjectName("balk")
        b = QHBoxLayout(balk)
        b.setContentsMargins(12, 8, 12, 8)
        for tekst, fn in (("＋  Nieuw recept", self.nieuw), ("✎  Bewerken", self.bewerk), ("🍳  Kookstand", self.kookstand),
                          ("🛒  Boodschappen", self.boodschappen), ("⏱  Kookwekker", self.eigen_wekker)):
            k = QPushButton(tekst)
            if "Kookstand" in tekst:
                k.setObjectName("hoofd")
            k.clicked.connect(fn)
            b.addWidget(k)
        b.addStretch(1)
        for tekst, fn in (("⋯  Meer", self.meer), ("?  Snelgids", self.snelgids)):
            k = QPushButton(tekst)
            k.clicked.connect(fn)
            b.addWidget(k)
        l.addWidget(balk)
        self.wbalk = WekkerBalk(self.wekkers)
        l.addWidget(self.wbalk)
        split = QSplitter()
        links = QWidget()
        links.setObjectName("links")
        ll = QVBoxLayout(links)
        ll.setContentsMargins(10, 10, 10, 10)
        self.zoek = QLineEdit()
        self.zoek.setPlaceholderText("🔍  Zoeken (naam of ingrediënt)")
        self.zoek.textChanged.connect(self.vul)
        ll.addWidget(self.zoek)
        self.cat = QComboBox()
        self.cat.currentIndexChanged.connect(self.vul)
        ll.addWidget(self.cat)
        self.lijst = QListWidget()
        self.lijst.currentRowChanged.connect(self.kies)
        self.lijst.itemDoubleClicked.connect(lambda *_: self.kookstand())
        ll.addWidget(self.lijst, 1)
        self.aantal = QLabel()
        self.aantal.setObjectName("grijs")
        ll.addWidget(self.aantal)
        split.addWidget(links)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(16, 10, 16, 10)
        prij = QHBoxLayout()
        prij.addWidget(QLabel("Personen:"))
        self.pers = QSpinBox()
        self.pers.setRange(1, 50)
        self.pers.valueChanged.connect(self.toon)
        prij.addWidget(self.pers)
        prij.addStretch(1)
        lees = QPushButton("🔊  Lees recept voor")
        lees.clicked.connect(self.lees_recept)
        prij.addWidget(lees)
        stil = QPushButton("■  Stil")
        stil.clicked.connect(self.stil)
        prij.addWidget(stil)
        rl.addLayout(prij)
        self.blad = QTextBrowser()
        self.blad.setObjectName("blad")
        self.blad.setOpenExternalLinks(False)
        rl.addWidget(self.blad, 1)
        split.addWidget(rechts)
        split.setSizes([360, 1040])
        l.addWidget(split, 1)
        self.statusBar().addPermanentWidget(QLabel("v" + APP_VERSION))
        for toets, fn in (("Ctrl+N", self.nieuw), ("Ctrl+E", self.bewerk), ("F11", self.kookstand), ("Ctrl+F", self.zoek.setFocus),
                          ("Ctrl+P", self.pdf_recept), ("Ctrl+=", lambda: self.letter(2)), ("Ctrl++", lambda: self.letter(2)),
                          ("Ctrl+-", lambda: self.letter(-2)), ("F5", self.lees_recept), ("Escape", self.stil)):
            QShortcut(QKeySequence(toets), self, activated=fn)

    def _stijl(self):
        self.setStyleSheet("""
            QMainWindow { background:%(BG)s; } QWidget { color:%(Z)s; font-size:%(L)dpx; }
            QWidget#balk, QWidget#links { background:%(P)s; } QWidget#wekkers { background:#2a2414; }
            QLabel#grijs { color:%(G)s; font-size:15px; }
            QListWidget { background:#121216; border:1px solid #26262e; border-radius:8px; }
            QListWidget::item { padding:9px 8px; } QListWidget::item:selected { background:#2a3a52; color:white; }
            QTextBrowser#blad { background:%(BG)s; border:0; }
            QPushButton { background:#24242c; border:1px solid #3a3a44; border-radius:8px; padding:8px 14px; font-size:16px; }
            QPushButton:hover { border-color:%(A)s; } QPushButton#hoofd { background:%(A)s; color:#0e0e11; font-weight:700; }
            QPushButton#wekker { background:%(GO)s; color:#000; font-weight:700; font-size:18px; }
            QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background:#121216; border:1px solid #3a3a44; border-radius:6px; padding:5px; }
            QDialog { background:%(P)s; } QStatusBar { background:%(P)s; color:%(G)s; }
        """ % dict(BG=BG, P=PANEL, Z=ZILVER, G=GRIJS, A=ACCENT, GO=GOUD, L=max(14, int(self.cfg["letter"]) - 3)))

    # ---- lijst
    def laad(self, kies_bestand=None):
        self.recepten = self.boek.alle()
        cats = sorted({r.get("categorie", "Overig") for r in self.recepten})
        huidig = self.cat.currentText()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem("Alle soorten")
        self.cat.addItems(cats)
        self.cat.setCurrentText(huidig if huidig in cats else "Alle soorten")
        self.cat.blockSignals(False)
        self.vul(kies_bestand=kies_bestand)

    def vul(self, *_, kies_bestand=None):
        z = self.zoek.text().strip().lower()
        c = self.cat.currentText()
        self.zichtbaar = [r for r in self.recepten
                          if (c in ("", "Alle soorten") or r.get("categorie") == c)
                          and (not z or z in r.get("titel", "").lower() or any(z in x.lower() for x in r.get("ingredienten", [])))]
        kies_bestand = kies_bestand or (self.r or {}).get("_bestand")
        self.lijst.blockSignals(True)
        self.lijst.clear()
        rij = 0
        for i, r in enumerate(self.zichtbaar):
            it = QListWidgetItem(r.get("titel", ""))
            it.setToolTip("%s · %s" % (r.get("categorie", ""), r.get("tijd", "")))
            self.lijst.addItem(it)
            if r.get("_bestand") == kies_bestand:
                rij = i
        self.lijst.blockSignals(False)
        self.aantal.setText("%d van %d recepten" % (len(self.zichtbaar), len(self.recepten)))
        if self.zichtbaar:
            self.lijst.setCurrentRow(rij)
            self.kies(rij)
        else:
            self.r = None
            self.blad.setHtml("<p style='color:#8a8a94;font-size:20px'>Geen recepten gevonden. Klik op ＋ Nieuw recept.</p>")

    def kies(self, i):
        if 0 <= i < len(self.zichtbaar):
            self.r = self.zichtbaar[i]
            self.pers.blockSignals(True)
            self.pers.setValue(int(self.r.get("personen", 4)))
            self.pers.blockSignals(False)
            self.toon()

    def factor(self):
        return Fraction(self.pers.value(), max(1, int((self.r or {}).get("personen", 4))))

    def html_recept(self, r, factor, donker=True):
        kl = dict(t="white", g=GOUD, s=ZILVER, m=GRIJS) if donker else dict(t="#111", g="#9a5a00", s="#111", m="#555")
        L = int(self.cfg["letter"])
        foto = self.boek.foto_pad(r)
        fhtml = ("<p><img src='file:///%s' width='420'></p>" % foto.replace("\\", "/")) if foto and os.path.exists(foto) else ""
        ingr = "".join("<li>%s</li>" % esc(schaal_regel(x, factor)) for x in r.get("ingredienten", []))
        stap = "".join("<li style='margin-bottom:10px'>%s</li>" % esc(x) for x in r.get("stappen", []))
        pers = round(int(r.get("personen", 4)) * factor)
        return ("<div style='color:%(s)s;font-size:%(L)dpx'>"
                "<h1 style='color:%(t)s;font-size:%(H)dpx;margin:0'>%(titel)s</h1>"
                "<p style='color:%(m)s'>%(cat)s · %(pers)d personen%(tijd)s</p>%(foto)s"
                "<h2 style='color:%(g)s'>Ingrediënten</h2><ul>%(ingr)s</ul>"
                "<h2 style='color:%(g)s'>Bereiding</h2><ol>%(stap)s</ol>%(not)s</div>") % dict(
            kl, L=L, H=L + 14, titel=esc(r.get("titel", "")), cat=esc(r.get("categorie", "")), pers=pers,
            tijd=(" · " + esc(r["tijd"])) if r.get("tijd") else "", foto=fhtml, ingr=ingr, stap=stap,
            **{"not": ("<h2 style='color:%s'>Notities</h2><p>%s</p>" % (kl["g"], esc(r["notities"]).replace("\n", "<br>"))
                       if r.get("notities") else "")})

    def toon(self):
        if self.r:
            self.blad.setHtml(self.html_recept(self.r, self.factor()))

    def letter(self, d):
        self.cfg["letter"] = max(14, min(40, int(self.cfg["letter"]) + d))
        bewaar_cfg(self.cfg)
        self._stijl()
        self.toon()

    # ---- acties
    def nieuw(self):
        d = Bewerk(self, self.boek)
        if d.exec():
            self.zoek.clear()
            self.laad(d.r["_bestand"])

    def bewerk(self):
        if not self.r:
            return
        d = Bewerk(self, self.boek, self.r)
        if d.exec():
            self.laad(d.r["_bestand"])

    def verwijder(self):
        if self.r and QMessageBox.question(self, "Verwijderen", "Recept '%s' verwijderen?\n\nHet gaat naar de map "
                                           "'_verwijderd' in je kookboek." % self.r.get("titel")) == QMessageBox.StandardButton.Yes:
            self.boek.weg(self.r)
            self.r = None
            self.laad()

    def kookstand(self):
        if self.r:
            Kookstand(self, self.r, self.factor()).exec()

    def boodschappen(self):
        d = Boodschappen(self, self.recepten)
        if self.r:
            d.kies(self.r)
        d.exec()

    def eigen_wekker(self):
        m, ok = QInputDialog.getInt(self, "Kookwekker", "Hoeveel minuten?", 10, 1, 600)
        if ok:
            self.wekkers.nieuw("%d min" % m, m * 60)

    def _wekker_af(self, label):
        self.raise_()
        self.activateWindow()
        self.zeg("De kookwekker is af. " + label)
        QMessageBox.information(self, "⏰  Kookwekker", "⏰  De kookwekker is af!\n\n%s" % label)
        self.wekkers.stil()

    def meer(self):
        from PyQt6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("📄  Recept als PDF (Ctrl+P)", self.pdf_recept)
        m.addAction("🗑  Recept verwijderen", self.verwijder)
        m.addSeparator()
        a = m.addAction("🔊  In de kookstand vanzelf voorlezen")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("voorlezen")))
        a.toggled.connect(lambda v: (self.cfg.__setitem__("voorlezen", v), bewaar_cfg(self.cfg)))
        m.addAction("🗣  Voorleesstem kiezen...", self.kies_stem)
        m.addAction("🐢  Voorleessnelheid...", self.kies_snelheid)
        m.addSeparator()
        m.addAction("📁  Map met recepten openen", lambda: os.startfile(self.boek.map))
        m.exec(self.cursor().pos())

    def kies_stem(self):
        stemmen = ["Cole", "Leon", "Cem", "Lina", "Linda", "Alina"]
        s, ok = QInputDialog.getItem(self, "Voorleesstem", "Stem:", stemmen,
                                     stemmen.index(self.cfg["stem"]) if self.cfg["stem"] in stemmen else 0, False)
        if ok:
            self.cfg["stem"] = s
            bewaar_cfg(self.cfg)
            if self.stem:
                self.stem.kies_stem(s)

    def kies_snelheid(self):
        keuzes = ["Heel rustig (70%)", "Rustig (80%)", "Normaal (90%)", "Vlot (100%)", "Snel (110%)"]
        waarden = [0.7, 0.8, 0.9, 1.0, 1.1]
        nu = min(range(5), key=lambda i: abs(waarden[i] - float(self.cfg["snelheid"])))
        s, ok = QInputDialog.getItem(self, "Voorleessnelheid", "Hoe snel mag ik voorlezen?", keuzes, nu, False)
        if ok:
            self.cfg["snelheid"] = waarden[keuzes.index(s)]
            bewaar_cfg(self.cfg)
            self.zeg("Zo lees ik voor. Twee eetlepels olijfolie.")

    def naar_pdf(self, naam, html_):
        p, _ = QFileDialog.getSaveFileName(self, "Opslaan als PDF", os.path.join(documenten(), veilige_naam(naam) + ".pdf"),
                                           "PDF (*.pdf)")
        if not p:
            return
        from PyQt6.QtPrintSupport import QPrinter
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Segoe UI", 12))
        doc.setHtml(html_)
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        pr.setOutputFileName(p)
        pr.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter))
        doc.print(pr)
        try:
            os.startfile(p)
        except Exception:
            pass

    def pdf_recept(self):
        if self.r:
            oud = self.cfg["letter"]
            self.cfg["letter"] = 13
            h = self.html_recept(self.r, self.factor(), donker=False)
            self.cfg["letter"] = oud
            self.naar_pdf(self.r.get("titel", "Recept"), h)

    # ---- voorlezen
    def zeg(self, tekst):
        if self.stem is None:
            try:
                from stem import Stem
                self.stem = Stem(self.cfg["stem"], "nl", float(self.cfg["snelheid"]))
                self.stem.warm_op()
                self.statusBar().showMessage("Voorleesstem laden... (de eerste keer wordt hij gedownload)", 8000)
            except Exception as e:
                self.statusBar().showMessage("Voorlezen is niet beschikbaar: %s" % e, 8000)
                self.stem = False
        if self.stem:
            self.stem.snelheid = float(self.cfg["snelheid"])
            # korte stukjes samenvoegen: de stem klinkt beter bij hele zinnen
            zinnen, buf = [], ""
            for zin in re.split(r"(?<=[.!?])\s+", uitspreekbaar(tekst)):
                buf = (buf + " " + zin).strip()
                if len(buf) >= 40:
                    zinnen.append(buf)
                    buf = ""
            if buf:
                zinnen.append(buf)
            for z in zinnen:
                self.stem.zeg(z)

    def stil(self):
        if self.stem:
            self.stem.stil()

    def lees_recept(self):
        if not self.r:
            return
        self.stil()
        f = self.factor()
        delen = [self.r.get("titel", "") + ", voor %d personen." % round(int(self.r.get("personen", 4)) * f),
                 "Je hebt nodig: " + ", ".join(schaal_regel(x, f) for x in self.r.get("ingredienten", [])) + ".",
                 "En nu de bereiding."]
        delen += ["Stap %d. %s" % (i + 1, s) for i, s in enumerate(self.r.get("stappen", []))]
        self.zeg(" ".join(delen))

    def snelgids(self):
        p = bron("DraveKookboek-Snelgids.pdf")
        if os.path.exists(p):
            os.startfile(p)
        else:
            QMessageBox.information(self, "Snelgids", "Kies een recept en klik op Kookstand.")

    def closeEvent(self, e):
        if self.wekkers.lijst and QMessageBox.question(self, APP_NAAM, "Er loopt nog een kookwekker. Toch afsluiten?") \
                != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        self.stil()
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAAM)
    w = Kook()
    w.show()
    try:  # Dravenlock: stille update-check (uit te zetten; Ctrl+Shift+U = met de hand)
        import drave_update
        drave_update.start(w, "DraveKookboek", APP_VERSION)
    except Exception:
        pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
