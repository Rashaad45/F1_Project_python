"""Builds F1_Projects_Documentation.docx from the project code and outputs.
Run after run_all.py so every figure exists:   python docs/build_documentation.py
"""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "A_F1_Engineering_Physics_and_Signal_Processing"
B = ROOT / "B_F1_Data_Analytics_Telemetry"
RED = RGBColor(0xB0, 0x10, 0x10)
GREY = RGBColor(0x55, 0x55, 0x55)

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Cm(2.2))
sec.top_margin = sec.bottom_margin = Cm(2.0)

st = doc.styles
st["Normal"].font.name = "Calibri"
st["Normal"].font.size = Pt(11)
st["Normal"].paragraph_format.space_after = Pt(6)
st["Normal"].paragraph_format.line_spacing = 1.12
for name, size, col in (("Title", 28, RED), ("Heading 1", 18, RED), ("Heading 2", 14, RGBColor(0x20, 0x20, 0x20)),
                        ("Heading 3", 12, RGBColor(0x40, 0x40, 0x40))):
    s = st[name]
    s.font.name = "Calibri"
    s.font.size = Pt(size)
    s.font.bold = True
    s.font.color.rgb = col
    s.element.rPr.rFonts.set(qn("w:asciiTheme"), "") if s.element.rPr is not None and s.element.rPr.rFonts is not None else None
    s.paragraph_format.space_before = Pt(14 if name != "Heading 3" else 10)
    s.paragraph_format.space_after = Pt(6)
    s.paragraph_format.keep_with_next = True


def _font(run, name):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), name)


def _shade(par, fill):
    ppr = par._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def rich(par, text):
    """**bold** and `code` inline markup."""
    import re
    for part in re.split(r"(\*\*.+?\*\*|`.+?`|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*]))", text):
        if not part:
            continue
        if part.startswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            par.add_run(part[1:-1]).italic = True
        elif part.startswith("`"):
            r = par.add_run(part[1:-1])
            _font(r, "Consolas")
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(0x8B, 0x00, 0x00)
        else:
            par.add_run(part)
    return par


def H(text, level=1):
    return doc.add_heading(text, level)


def P(text):
    return rich(doc.add_paragraph(), text)


def BUL(items, style="List Bullet"):
    for it in items:
        rich(doc.add_paragraph(style=style), it)


def NUM(items):
    """Numbered list that restarts at 1: a new w:num pointing at the
    'List Number' abstract numbering, with a startOverride of 1."""
    numbering = doc.part.numbering_part.element
    style_numid = doc.styles["List Number"].element.pPr.numPr.numId.val
    abstract = numbering.num_having_numId(style_numid).abstractNumId.val
    num = numbering.add_num(abstract)
    ov = OxmlElement("w:lvlOverride")
    ov.set(qn("w:ilvl"), "0")
    so = OxmlElement("w:startOverride")
    so.set(qn("w:val"), "1")
    ov.append(so)
    num.append(ov)
    for it in items:
        par = rich(doc.add_paragraph(style="List Number"), it)
        numPr = par._p.get_or_add_pPr().get_or_add_numPr()
        numPr.get_or_add_ilvl().val = 0
        numPr.get_or_add_numId().val = num.numId


def EQ(*lines, note=None):
    for ln in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(ln)
        _font(r, "Cambria Math")
        r.font.size = Pt(12)
    if note:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(note)
        r.italic = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = GREY


def CODE(text):
    for i, ln in enumerate(text.strip("\n").split("\n")):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_after = Pt(0)
        pf.space_before = Pt(4) if i == 0 else Pt(0)
        pf.line_spacing = 1.0
        pf.left_indent = Cm(0.3)
        _shade(p, "F2F2F2")
        r = p.add_run(ln if ln else " ")
        _font(r, "Consolas")
        r.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def FIG(path, caption, width=16.0):
    if not Path(path).exists():
        P(f"[figure missing: {path} - run run_all.py first]")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Cm(width))
    c = doc.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.add_run(caption)
    r.italic = True
    r.font.size = Pt(9.5)
    r.font.color.rgb = GREY


def TABLE(rows, widths=None, header=True):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            par = cell.paragraphs[0]
            par.paragraph_format.space_after = Pt(1)
            rich(par, str(val))
            for r in par.runs:
                r.font.size = Pt(9.5)
                if header and i == 0:
                    r.bold = True
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            if header and i == 0:
                tcpr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:fill"), "B01010")
                tcpr.append(shd)
            if widths:
                cell.width = Cm(widths[j])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def PAGEBREAK():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def field(par, instr):
    r = par.add_run()
    for tag, attr in (("w:fldChar", "begin"), ("w:instrText", None), ("w:fldChar", "separate")):
        el = OxmlElement(tag)
        if attr:
            el.set(qn("w:fldCharType"), attr)
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        r._r.append(el)
    t = par.add_run("Right-click and choose Update Field to build the table of contents.")
    t.italic = True
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    par.add_run()._r.append(end)


# footer page numbers
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run()
for tag, attr, txt in (("w:fldChar", "begin", None), ("w:instrText", None, "PAGE"), ("w:fldChar", "end", None)):
    el = OxmlElement(tag)
    if attr:
        el.set(qn("w:fldCharType"), attr)
    else:
        el.set(qn("xml:space"), "preserve")
        el.text = txt
    r._r.append(el)
# ask Word to refresh the TOC when the file is opened
# (the TOC is filled in by Word - see docs/README note; or right-click > Update Field)

# =====================================================================
# TITLE
# =====================================================================
doc.add_paragraph().paragraph_format.space_after = Pt(60)
t = doc.add_paragraph(style="Title")
t.add_run("Formula 1 Engineering & Data Analytics")
p = doc.add_paragraph()
r = p.add_run("Six portfolio projects: code, mathematics, algorithms and syntax explained")
r.font.size = Pt(15)
r.font.color.rgb = GREY
doc.add_paragraph()
TABLE([
    ["Folder", "Projects", "Theme"],
    ["A - Engineering: Physics & Signal Processing",
     "A1 Engine sound & RPM estimation\nA2 Delta-time indicator\nA3 Braking distance model",
     "DSP, physics, mathematical modelling"],
    ["B - Data Analytics: Telemetry",
     "B1 Circuit mapping (Beginner)\nB2 Tyre degradation (Intermediate)\nB3 Telemetry comparison (Advanced)",
     "pandas, statistics, visualisation"],
], widths=[5.2, 6.6, 4.8])
P("Language: **Python 3.11** (numpy, pandas, scipy, matplotlib, openpyxl).  Data: **OpenF1 API** "
  "(real 2024 F1 timing & telemetry), cached as CSV.  Reference repositories cloned: "
  "**theOehrly/Fast-F1** and **br-g/openf1**.")
PAGEBREAK()

H("Contents", 1)
field(doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u')
PAGEBREAK()

# =====================================================================
# 1 OVERVIEW
# =====================================================================
H("1. Overview", 1)
H("1.1 How the screenshots were classified", 2)
P("The six screenshots contain two separate social-media posts, each describing three projects. They were "
  "grouped by the **kind of skill** they develop:")
TABLE([
    ["Post (screenshots)", "Projects listed", "Classified as"],
    ["'Formula 1 engineering is more accessible than you might think' (13.36.00, 13.36.00 (1), 13.36.02)",
     "1. Analyse engine sounds (Audacity)\n2. Delta-time indicator (Python/Excel)\n3. F1 braking distances (d = v²/2a)",
     "**Folder A** - Engineering: physics & signal processing"],
    ["'Three projects for different skill levels' (13.36.04 (1)-(3))",
     "1. Circuit mapping & speed (Beginner)\n2. Tyre degradation (Intermediate)\n3. Telemetry comparison (Advanced)",
     "**Folder B** - Data analytics with telemetry"],
], widths=[5.6, 6.0, 5.0])

H("1.2 Folder structure", 2)
CODE("""
F1 Project/
├── README.md, requirements.txt, run_all.py
├── F1_Projects_Documentation.docx          <- this document
├── screenshots/                            <- original WhatsApp images
├── external_repos/
│   ├── Fast-F1/                            <- git clone theOehrly/Fast-F1
│   └── openf1/                             <- git clone br-g/openf1
├── A_F1_Engineering_Physics_and_Signal_Processing/
│   ├── f1data.py                           <- cached OpenF1 client
│   ├── data/                               <- CSV dataset (auto-downloaded)
│   ├── 01_engine_sound_analysis/  engine_sound_analysis.py  outputs/
│   ├── 02_delta_time_indicator/   delta_time_indicator.py   outputs/
│   └── 03_braking_distance/       braking_distance.py       outputs/
└── B_F1_Data_Analytics_Telemetry/
    ├── f1data.py, data/
    ├── 01_circuit_mapping/        circuit_mapping.py        outputs/
    ├── 02_tyre_degradation/       tyre_degradation.py       outputs/
    └── 03_telemetry_comparison/   telemetry_comparison.py   outputs/
""")

H("1.3 Installing and running", 2)
CODE("""
pip install -r requirements.txt
python run_all.py                              # all six projects
cd B_F1_Data_Analytics_Telemetry/03_telemetry_comparison
python telemetry_comparison.py --drivers VER PER --circuit Silverstone
""")
P("Every script accepts command-line options (`--year`, `--circuit`, `--driver` …), so the same code "
  "analyses any 2023+ session. Results in this document use the **2024 Italian Grand Prix (Monza)**.")

H("1.4 Dataset & the FastF1 / OpenF1 decision", 2)
P("The posts recommend **FastF1**, which was cloned into `external_repos/Fast-F1`. When tested, FastF1 3.9 "
  "asked for an F1-account login and returned *no* timing or telemetry without one: the official live-timing "
  "archive is now authenticated. **OpenF1** (cloned into `external_repos/openf1`) publishes the same "
  "underlying data through a free REST API, so all projects use it through one small module, `f1data.py`.")
TABLE([
    ["OpenF1 endpoint", "What it contains", "Used by"],
    ["sessions / drivers", "session_key, driver number ↔ acronym", "all"],
    ["laps", "lap time, three sector times, speed traps, pit-out flag", "A2, B2"],
    ["stints", "tyre compound, first/last lap of stint, tyre age at fit", "B2"],
    ["car_data (~3.7 Hz)", "speed, RPM, throttle, brake, gear, DRS", "A1, A3, B1, B3"],
    ["location (~3.7 Hz)", "x, y, z car position (units of 0.1 m)", "B1, B3"],
], widths=[4.2, 8.4, 3.0])
H("How f1data.py works", 3)
CODE('''
def _get(endpoint, params, cache_name):
    path = DATA_DIR / f"{cache_name}.csv"
    if path.exists():                       # 1. cache hit -> no network
        return pd.read_csv(path)
    url = f"{BASE_URL}/{endpoint}?{query}"  # 2. build URL, e.g. date>=...
    for attempt in range(5):                # 3. retry with back-off
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                rows = json.loads(r.read().decode())
            break
        except Exception:
            time.sleep(2 ** attempt)        #    1, 2, 4, 8 s
    df = pd.DataFrame(rows)                 # 4. JSON list -> table
    df.to_csv(path, index=False)            # 5. save = dataset
    return df
''')
BUL([
    "**Caching pattern**: the first run downloads, later runs read the CSV. The `data/` folders (~0.5 MB) are the project dataset and make results reproducible offline.",
    "**Exponential back-off** (`2 ** attempt`) is the standard way to survive rate limits (HTTP 429).",
    "`lap_telemetry()` merges car data and position with `pd.merge_asof(..., direction='nearest')`, a join on the *closest timestamp*, because the two streams are sampled at different instants.",
    "Distance is computed by integrating speed (trapezoidal rule, see below), since OpenF1 does not provide it.",
])
EQ("sᵢ = sᵢ₋₁ + ½ (vᵢ + vᵢ₋₁)(tᵢ − tᵢ₋₁)", note="Trapezoidal rule: area under the speed-time curve = distance travelled")

H("1.5 Python syntax primer (used throughout)", 2)
TABLE([
    ["Syntax", "Meaning"],
    ["`from __future__ import annotations`", "lets type hints like `str | None` work on older Python"],
    ["`argparse.ArgumentParser()`", "command-line options: `ap.add_argument('--year', type=int, default=2024)`"],
    ["`sys.path.insert(0, str(ROOT.parent))`", "lets a script in a sub-folder `import f1data` from its parent folder"],
    ["`Path(__file__).resolve().parent`", "folder of the current script, so paths work from any working directory"],
    ["`f\"{x:.3f}\"`, `f\"{d:+.3f}\"`", "f-strings: 3 decimals; `+` forces a sign (useful for deltas)"],
    ["`np.array`, vectorisation", "`v ** 2 / (2 * a)` is computed for a whole array at once - no Python loop"],
    ["Boolean masks", "`df[df['speed'] > 300]` keeps rows where the condition is True; combine with `&`, `|`, `~`"],
    ["`df.groupby(key)[col].transform(f)`", "apply f per group but return a column aligned with the original rows"],
    ["`df.merge(other, on='col')`", "SQL-style join of two tables"],
    ["`np.interp(x_new, x, y)`", "linear interpolation of y(x) at new points - used to resample laps"],
    ["`lambda x: ...`", "small anonymous function, e.g. the objective of an optimiser"],
    ["`fig, ax = plt.subplots(r, c)`", "matplotlib figure with a grid of axes; `ax[i, j].plot(...)`"],
], widths=[6.0, 10.6])
PAGEBREAK()

# =====================================================================
# A1
# =====================================================================
H("2. Folder A - Engineering: Physics & Signal Processing", 1)
H("A1. Engine sound analysis and RPM estimation", 2)
H("Objective", 3)
P("Show how the dominant audio frequencies change with acceleration and gear shifts (a spectrogram, as in "
  "Audacity) and estimate engine RPM from sound alone, then **measure how accurate the estimate is**.")
H("Data", 3)
P("A real RPM trace (Leclerc, Monza 2024 qualifying, 79.461 s) is used to *synthesise* an onboard-style "
  "engine recording (`outputs/synthetic_onboard.wav`, openable in Audacity). Because the true RPM is "
  "known, the estimator can be scored. Real recordings can be analysed with "
  "`python engine_sound_analysis.py --wav my_onboard.wav` (export from Audacity as WAV).")
H("Mathematics", 3)
P("**Engine orders.** A four-stroke cylinder fires once every two crank revolutions, so an N-cylinder engine fires N/2 times per revolution:")
EQ("f_rot = RPM / 60          f_fire = (RPM / 60) · (N / 2)",
   "V6 (N = 6):   f_fire = RPM / 20     →   11 000 rpm ↔ 550 Hz",
   note="The firing frequency (engine order 3) and its multiples dominate the sound")
P("**Synthesis with a time-varying frequency.** A sine wave whose frequency changes must use the integral of frequency as its phase:")
EQ("φ(t) = 2π ∫₀ᵗ f_rot(τ) dτ  ≈  2π · cumsum(f_rot) / f_s",
   "y(t) = Σₖ aₖ sin(k·φ(t) + θₖ) + noise(t)")
P("Noise, a gearbox-whine tone that is not locked to the engine, and an **exhaust resonance** that makes the "
  "2× firing harmonic *louder* than the fundamental above 11 500 rpm are all added. Real onboard audio does "
  "this, and it breaks naive methods.")
P("**Short-Time Fourier Transform (STFT).** The signal is cut into overlapping windowed frames and each frame is Fourier-transformed:")
EQ("X(m, k) = Σₙ x[n] · w[n − mH] · e^(−j2πkn/N)",
   "N = 4096 (Hann window),  H = 512,  f_s = 22 050 Hz",
   "Δf = f_s / N = 5.4 Hz      Δt = H / f_s = 23 ms",
   note="Time-frequency trade-off: a longer window gives finer frequency resolution but blurs fast RPM changes")
P("**Harmonic-sum RPM estimator.** For each candidate RPM r (4 000 to 13 500 in 10-rpm steps) and every frame m:")
EQ("score(r, m) = Σ_{h=1..4} (1/h) · log(1 + |X(m, h·f_fire(r))|)",
   "RPM̂(m) = argmax_r score(r, m)")
P("Adding several harmonics means a candidate wins only if *all* its harmonics are present. If the loudest "
  "peak is really the 2nd harmonic, the true RPM still scores higher because its 1st, 2nd, 3rd and 4th "
  "harmonics all line up. The log compresses dynamic range so one loud peak cannot dominate. A **median "
  "filter** (9 frames) then removes isolated outliers without smoothing real steps.")
P("**Gear-shift detection** uses the signature *RPM was rising for 0.6 s, then dropped > 450 rpm within 0.25 s*. "
  "The 'rising' condition rejects braking zones, where RPM also falls.")
H("Algorithm", 3)
NUM([
    "Load the RPM and gear trace for the lap (`load_real_rpm`).",
    "Upsample RPM from 3.7 Hz to 22 050 Hz with `np.interp`, smooth, integrate to phase, sum harmonics + noise (`synthesize_engine`).",
    "Compute the STFT magnitude with `scipy.signal.stft` (`spectrogram`).",
    "Evaluate the harmonic-sum score on the RPM grid; take argmax per frame; median-filter (`estimate_rpm`).",
    "Baseline: take the loudest bin between 150 and 1400 Hz and assume it is f_fire (`naive_peak_rpm`).",
    "Detect upshifts; compare everything with telemetry (MAE, MAPE); plot.",
])
H("Key code and syntax", 3)
CODE('''
cands = np.arange(rpm_min, rpm_max + step, step)        # candidate RPMs
score = np.zeros((cands.size, S.shape[1]))              # (candidates x frames)
for h in harmonics:
    fh  = h * cands / 60 * n_cyl / 2                    # frequency of harmonic h
    idx = np.round(fh / (f[1] - f[0])).astype(int)      # Hz -> FFT bin index
    score += logS[idx, :] / h                           # fancy indexing: rows idx
rpm = cands[np.argmax(score, axis=0)]                   # best candidate per frame
''')
BUL([
    "`logS[idx, :]` uses **NumPy fancy indexing**: one call picks the right FFT bin for every candidate in every frame (≈950 × 3 400 values) with no Python loop over time.",
    "`np.argmax(score, axis=0)` finds the maximum down each column, i.e. per time frame.",
    "`np.cumsum(f_rot) / fs` is the discrete version of the phase integral.",
    "`wavfile.write(path, fs, y)` saves the float32 signal so it can be opened in Audacity.",
])
H("Results", 3)
TABLE([
    ["Method", "Mean abs. error", "MAPE", "Frames within 3 %"],
    ["Naive loudest peak", "4 183 rpm", "35.2 %", "65 %"],
    ["Harmonic-sum + median", "**12.9 rpm**", "**0.12 %**", "**100 %**"],
], widths=[5.5, 3.8, 3.0, 4.3])
P("Upshift detection from audio: 17 events found, 13 matching the 18 upshifts in the gear channel within 0.7 s.")
FIG(A / "01_engine_sound_analysis/outputs/engine_spectrogram_rpm.png",
    "Figure A1 - Spectrogram with tracked firing frequency (top), RPM estimates vs telemetry (middle), gear (bottom)")
H("Limitations & extensions", 3)
BUL(["Real recordings add Doppler shift, camera-microphone resonances and other cars; tune `rpm_min/max` and harmonics accordingly.",
     "Extension: a Viterbi or Kalman tracker to enforce physically plausible RPM rates of change."])
P("**Resume bullet:** *Built a Python DSP pipeline (STFT, harmonic-sum pitch tracking) that recovers F1 engine "
  "RPM from audio with 0.12 % error, versus 35 % for peak picking, validated against real telemetry.*")
PAGEBREAK()

# =====================================================================
# A2
# =====================================================================
H("A2. Delta-time indicator (timing screen)", 2)
H("Objective", 3)
P("Compare each driver's sector times with a reference lap, show whether each sector is faster or slower, "
  "and colour sectors like the official F1 timing screen: **purple** = fastest of the session, **green** = "
  "the driver's personal best, **yellow** = slower than their personal best.")
H("Mathematics", 3)
EQ("Δᵢ = tᵢ(driver) − tᵢ(reference)          (negative = faster)",
   "Cumulative delta after sector k:   D_k = Σ_{i≤k} Δᵢ",
   "Theoretical best lap = min S1 + min S2 + min S3")
P("Laps are filtered with the **107 % rule**: laps slower than 1.07 × the fastest lap are out-laps or "
  "cool-down laps, not push laps.")
H("Algorithm & conditional logic", 3)
NUM([
    "Download all laps; join driver acronyms (`merge`).",
    "Keep laps with three sector times, not pit-out, and inside 107 %.",
    "`overall_best = valid[SECT].min()` gives the purple threshold for each sector; `personal_best = groupby(driver).min()` gives the green threshold.",
    "Take each driver's fastest lap (`groupby(...).idxmin()`), sort by lap time; reference = pole lap or `--ref`.",
    "For each sector apply the if / elif / else rule below, compute Δ to reference.",
    "Output: ANSI-coloured terminal table, matplotlib timing screen, cumulative-delta plot, Excel file with cell fills.",
])
CODE('''
if np.isclose(t, overall_best[s]):          # fastest of anyone, any lap
    colour = "purple"
elif np.isclose(t, personal_best.loc[drv, s]):  # driver's own best
    colour = "green"
else:
    colour = "yellow"
''')
BUL([
    "`np.isclose` is used instead of `==` because floating-point numbers such as 26.223 may not compare exactly.",
    "The order of the checks matters: a purple sector is also a personal best, so purple must be tested first.",
    "ANSI escape codes (`\\033[95m` = magenta) colour text in a terminal; `\\033[0m` resets.",
    "Excel: `openpyxl.styles.PatternFill('solid', fgColor='9B30FF')` fills a cell; `number_format='+0.000;-0.000'` always shows the sign.",
    "Drawing the screen: `plt.Rectangle` patches with `ax.text` on top, and `ax.axis('off')` hides axes.",
])
H("Results (Monza 2024 qualifying)", 3)
P("Reference: NOR 1:19.327 (pole). PIA +0.109, RUS +0.113, LEC +0.134. Sainz set the purple first sector "
  "(26.223, 0.269 s faster than Norris) but lost it in sectors 2 and 3. The session's theoretical best lap is "
  "**79.055 s**, 0.27 s quicker than pole. The purple S3 (26.253) came from a lap that was not anyone's "
  "fastest lap, which is exactly what the real timing screen shows.")
FIG(A / "02_delta_time_indicator/outputs/timing_screen.png", "Figure A2a - Generated timing screen", 15.5)
FIG(A / "02_delta_time_indicator/outputs/delta_vs_reference.png", "Figure A2b - Cumulative delta at each timing line", 12.5)
P("**Resume bullet:** *Developed a Python/Excel F1 timing dashboard that computes sector deltas against a "
  "reference lap and applies purple/green/yellow conditional formatting, with automated Excel export (openpyxl).*")
PAGEBREAK()

# =====================================================================
# A3
# =====================================================================
H("A3. Braking distance: from d = v²/2a to a telemetry-identified aero model", 2)
H("Objective", 3)
P("Build the calculator requested in the post, then go further: show *why* the constant-deceleration model "
  "is wrong for an F1 car and identify a better model from real telemetry.")
H("Part 1: constant deceleration", 3)
P("From the kinematic equation v² = v₀² − 2ad, setting v = 0:")
EQ("d = v₀² / (2a)          t = v₀ / a          (v₀ in m/s = km/h ÷ 3.6)")
TABLE([
    ["Deceleration", "1 g", "2 g", "3 g", "4 g", "5 g", "6 g"],
    ["Distance from 300 km/h [m]", "354.0", "177.0", "118.0", "88.5", "70.8", "59.0"],
    ["Time to stop [s]", "8.49", "4.25", "2.83", "2.12", "1.70", "1.42"],
], widths=[5.0, 1.9, 1.9, 1.9, 1.9, 1.9, 1.9])
P("Distance is inversely proportional to deceleration (doubling a halves d) and grows with the *square* of speed.")
H("Part 2: aerodynamic model", 3)
P("An F1 car's downforce pushes the tyres into the track (more grip), and drag slows the car directly. Both grow with v²:")
EQ("m·dv/dt = −[ μ(mg + ½ρC_LA·v²) + ½ρC_DA·v² ]",
   "a(v) = c₀ + c₁v²,      c₀ = μg,      c₁ = ρ(μC_LA + C_DA) / (2m)")
P("Using the chain rule dv/dt = (dv/ds)(ds/dt) = v·dv/ds and separating variables:")
EQ("v dv / (c₀ + c₁v²) = −ds",
   "d(v₀→v₁) = 1/(2c₁) · ln[(c₀ + c₁v₀²) / (c₀ + c₁v₁²)]",
   "t(v₀→0) = arctan(v₀√(c₁/c₀)) / √(c₀c₁)")
P("The closed form is checked numerically with `scipy.integrate.solve_ivp` (adaptive Runge-Kutta 4(5)) on "
  "the state y = [s, v], dy/dt = [v, −(c₀ + c₁v²)], stopped by an *event function* when v reaches v₁. Both "
  "give 147.6 m from 300 km/h.")
H("Part 3: identifying c₀ and c₁ from telemetry (system identification)", 3)
NUM([
    "Braking zones = runs of samples with brake on that lose ≥ 40 km/h; 'heavy' zones lose ≥ 100 km/h.",
    "Half-sample correction: the brake came on between the last 'off' and first 'on' sample, so the midpoint is used (≈ 12 m bias removed at 330 km/h).",
    "Inside heavy zones, deceleration between consecutive samples: aᵢ = (vᵢ² − vᵢ₊₁²) / (2Δsᵢ), at v² = (vᵢ² + vᵢ₊₁²)/2.",
    "Fit a = c₀ + c₁v² by **linear least squares**. It is linear in the unknowns even though it is quadratic in v.",
])
EQ("X = [1  v²],    θ = [c₀  c₁]ᵀ,    θ̂ = argmin ‖Xθ − a‖²  =  (XᵀX)⁻¹Xᵀa",
   "R² = 1 − Σ(aᵢ − âᵢ)² / Σ(aᵢ − ā)²")
CODE('''
X = np.column_stack([np.ones(len(smp)), smp["v2_mid"]])
(c0, c1), *_ = np.linalg.lstsq(X, smp["a"], rcond=None)   # least squares
z["aero_model_d_m"] = aero_distance(v0s, v1s, c0, c1)     # vectorised
''')
BUL(["`(c0, c1), *_ = ...` is tuple unpacking: `lstsq` returns 4 values, and `*_` discards the last three.",
     "`stop.terminal = True` attaches an attribute to a function so `solve_ivp` halts at the event."])
H("Results (Norris, Monza 2024 Q)", 3)
TABLE([
    ["Model (fitted on 3 heavy stops)", "Parameters", "Distance RMSE"],
    ["Constant deceleration", "a = 2.70 g", "29.0 m"],
    ["Aero model a = c₀ + c₁v²", "c₀ = 8.79 m/s², c₁ = 0.00585 m⁻¹ (R² = 0.58)", "**3.1 m**"],
], widths=[5.6, 7.0, 3.0])
P("Measured deceleration is ≈ 3 to 5 g above 250 km/h but only ≈ 0.5 to 1.5 g near 100 km/h, so a single constant "
  "cannot fit. The aero model predicts 5.0 g at 300 km/h, matching the > 5 g peak quoted in the post. Light "
  "trail-braking zones (fast corners) are over-predicted by the straight-line model because grip is shared "
  "between braking and cornering (the friction circle). The fitted μ and implied C_LA are *effective* "
  "values. They also absorb brake-pressure modulation and the 3.7 Hz sampling (~25 m between points at 330 km/h).")
FIG(A / "03_braking_distance/outputs/braking_analysis.png",
    "Figure A3 - Calculator curves, deceleration vs speed fit, heaviest stop (Turn 1), model vs measurement")
P("**Resume bullet:** *Derived and validated an aerodynamic braking model (closed form + RK45) and identified "
  "its parameters from F1 telemetry by least squares, reducing braking-distance error from 29 m to 3 m "
  "compared with a constant-deceleration model.*")
PAGEBREAK()

# =====================================================================
# B1
# =====================================================================
H("3. Folder B - Data Analytics: Telemetry", 1)
H("B1. Circuit mapping and speed visualisation (Beginner)", 2)
H("Objective", 3)
P("Draw the circuit from recorded car coordinates, colour it by speed, and mark the top-speed point and braking zones.")
H("Mathematics", 3)
P("**Rotation.** To orient the map, every point is multiplied by a 2-D rotation matrix:")
EQ("[x′]   [cos θ  −sin θ] [x]",
   "[y′] = [sin θ   cos θ] [y]")
P("**Choosing θ with PCA.** The covariance matrix of the centred coordinates has eigenvectors pointing along "
  "the directions of greatest spread. Rotating the major eigenvector onto the x-axis makes the longest "
  "dimension of the track horizontal:")
EQ("C = cov([x, y]),   C·v = λ·v,   θ = −atan2(v_major,y , v_major,x)")
P("**Statistics:** lap length = final integrated distance; average speed = L / lap time; full-throttle share "
  "= Σ Δt where throttle ≥ 98 % divided by total time.")
H("Algorithm", 3)
NUM(["Fastest lap → telemetry with x, y (0.1 m units → divide by 10).",
     "Rotate with the PCA angle.",
     "Build line segments between consecutive points: array of shape (N−1, 2, 2).",
     "`LineCollection` colours each segment by the mean speed of its two endpoints.",
     "Brake onsets = samples where brake switches 0 → on: `np.where(~b[:-1] & b[1:])`.",
     "Second map coloured by gear; speed-vs-distance trace with braking zones shaded."])
CODE('''
pts = xy.reshape(-1, 1, 2)                               # (N, 1, 2)
seg = np.concatenate([pts[:-1], pts[1:]], axis=1)        # (N-1, 2, 2)
lc  = LineCollection(seg, cmap="plasma", norm=plt.Normalize(vmin, vmax), lw=6)
lc.set_array(seg_speed)                                  # value per segment
ax.add_collection(lc);  fig.colorbar(lc, ax=ax)
''')
BUL(["`reshape(-1, 1, 2)`: `-1` means 'work out this dimension for me'.",
     "`~b[:-1] & b[1:]` compares each sample with the next one: True exactly where the brake is first pressed (an edge detector).",
     "`ax.set_aspect('equal')` keeps 1 m in x equal to 1 m in y, so the circuit is not distorted."])
H("Results (Norris, pole lap)", 3)
TABLE([["Lap length (integrated)", "Average speed", "Top speed", "Min speed", "Full throttle", "Braking zones"],
       ["5 719 m (official 5 793 m, −1.3 %)", "259.5 km/h", "347 km/h", "73 km/h", "75 % of time", "7"]])
FIG(B / "01_circuit_mapping/outputs/circuit_speed_map.png", "Figure B1a - Monza coloured by speed, brake points labelled with entry speed")
FIG(B / "01_circuit_mapping/outputs/circuit_gear_map.png", "Figure B1b - Gear used around the lap", 13)
P("**Resume bullet:** *Visualised F1 telemetry as speed- and gear-coloured circuit maps (matplotlib "
  "LineCollection, PCA alignment), extracting lap statistics such as top speed, braking points and "
  "full-throttle percentage.*")
PAGEBREAK()

# =====================================================================
# B2
# =====================================================================
H("B2. Tyre degradation analysis (Intermediate)", 2)
H("Objective", 3)
P("Measure how much slower each tyre compound gets per lap, and explain a real strategy outcome: at Monza "
  "2024, **Leclerc won on a one-stop** while Piastri two-stopped.")
H("Data preparation", 3)
NUM([
    "Join laps with stints: a lap belongs to the stint whose [lap_start, lap_end] contains it. Tyre age = tyre_age_at_start + (lap − lap_start).",
    "Remove lap 1, pit-out laps and in-laps (last lap of every stint except the final one).",
    "Remove neutralised laps (safety car / VSC): laps whose field median is > 105 % of the race median.",
    "Remove outliers per stint (traffic, mistakes) with a robust **MAD** rule.",
    "Fuel-correct lap times.",
])
H("Mathematics", 3)
P("**Robust outlier rule.** The median absolute deviation is not distorted by the outliers it is trying to find (unlike the standard deviation):")
EQ("MAD = median(|xᵢ − median(x)|),      keep  xᵢ < median + 3 · 1.4826 · MAD",
   note="1.4826 · MAD estimates σ for normally distributed data")
P("**Fuel correction.** A car burns ≈ 105 kg over a race and each kilogram costs ≈ 0.03 s per lap. Without "
  "correction, the fuel burn-off (≈ −0.06 s/lap) hides tyre wear:")
EQ("t_corr = t − 0.03 · m_fuel(lap),      m_fuel = 105 · (1 − (lap − 1)/N_laps)")
P("**Degradation per stint**: ordinary least squares on t_corr = β₀ + β₁·age (`scipy.stats.linregress`):")
EQ("β₁ = Σ(aᵢ − ā)(tᵢ − t̄) / Σ(aᵢ − ā)²",
   "95 % CI:  β₁ ± t₀.₉₇₅,ₙ₋₂ · SE(β₁)")
P("**Pooled degradation per compound with fixed effects.** Cars differ in pace, so pooling raw points would "
  "mix car speed with tyre wear. Subtracting each driver-stint's own mean (*demeaning*) removes the "
  "differences in intercept and leaves only the shared slope:")
EQ("t̃ᵢ = tᵢ − t̄_stint,   ãᵢ = aᵢ − ā_stint,      β̂ = Σ ãᵢ t̃ᵢ / Σ ãᵢ²")
P("**Gap between two drivers** at the start of lap n is the difference in their lap-start timestamps; the "
  "finishing gap uses start + duration of the final lap.")
H("Key code and syntax", 3)
CODE('''
m = laps.merge(st, on="driver_number")
m = m[(m["lap_number"] >= m["lap_start"]) & (m["lap_number"] <= m["lap_end"])]
g   = c.groupby(["name_acronym", "stint_number"])["lap_duration"]
mad = g.transform(lambda s: np.median(np.abs(s - s.median())))
r   = stats.linregress(g["tyre_age"], g["lap_time_corr"])   # slope, stderr, rvalue
gap = (t2 - t1).dt.total_seconds()                          # Timedelta -> float
''')
BUL(["Merge then filter is a simple *interval join*: every lap is first paired with every stint of that driver, then only the matching one is kept.",
     "`transform` returns a value per original row, so the MAD threshold can be compared row by row.",
     "`.dt.total_seconds()` is the pandas accessor for datetime/timedelta columns."])
H("Results (Monza 2024 race)", 3)
TABLE([["Compound", "Pooled degradation (fuel-corrected)", "Laps"],
       ["HARD", "+0.045 ± 0.004 s/lap", "657"],
       ["MEDIUM", "+0.040 ± 0.014 s/lap", "228"]], widths=[3.5, 8, 3])
P("Leclerc ran Medium → Hard for 37 laps (degradation 0.051 s/lap, R² = 0.85). Piastri's second stop gave "
  "him fresh Hards and a median pace 0.41 s/lap quicker. The gap chart shows him cutting Leclerc's lead from "
  "18.5 s to **2.6 s at the flag** (official 2.664 s). His second stop swung the gap by ≈ 24 s, and the fresher "
  "tyres then won back about 16 s. That was not enough.")
FIG(B / "02_tyre_degradation/outputs/degradation_scatter.png", "Figure B2a - Lap time vs tyre age with per-stint fits; degradation distribution")
FIG(B / "02_tyre_degradation/outputs/strategy_gap.png", "Figure B2b - LEC vs PIA gap and race pace", 15)
FIG(B / "02_tyre_degradation/outputs/strategy_chart.png", "Figure B2c - All tyre strategies", 13)
H("Caveat (from the post)", 3)
P("Slower laps do not automatically prove tyre wear: traffic, dirty air, fuel, track evolution and driver "
  "management all matter. The cleaning steps and fuel correction reduce, but do not remove, these effects. "
  "That is why the confidence intervals are reported.")
P("**Resume bullet:** *Quantified F1 tyre degradation with fuel-corrected, fixed-effects regression over 885 "
  "race laps (Hard: 0.045 ± 0.004 s/lap) and explained how a one-stop strategy beat a two-stop.*")
PAGEBREAK()

# =====================================================================
# B3
# =====================================================================
H("B3. Telemetry comparison (Advanced)", 2)
H("Objective", 3)
P("Compare two qualifying laps (Norris vs Leclerc, Monza 2024) to show *where* on the track time is gained "
  "or lost: speed traces, throttle and brake, and a delta-time trace.")
H("The alignment problem", 3)
P("Telemetry is sampled in **time**, at different instants for each car, but drivers must be compared at the "
  "same **place** on track. Both laps are therefore converted to functions of distance and resampled onto a "
  "common grid every 5 m.")
EQ("sᵢ = v₀t₀ + Σ trapezoid(v, t)        (v₀t₀ = metres covered before the first sample)",
   "s′ = s · L_ref / L_i        (stretch each lap to the same length)",
   "t_A(s), t_B(s), v_A(s) … via linear interpolation on s = 0, 5, 10, … m")
P("**Delta time** and its slope:")
EQ("Δt(s) = t_B(s) − t_A(s)",
   "dΔt/ds = 1/v_B(s) − 1/v_A(s)",
   note="Δt rises wherever B is slower at that point: the slope tells you where time is lost")
P("**Mini-sectors**: the lap is cut into 25 equal pieces. In each piece, the driver with the smaller "
  "time t(s_end) − t(s_start) 'owns' it, and the map is coloured accordingly.")
H("Key code and syntax", 3)
CODE('''
s = lap_distance(tel, lap_time) * L_ref / lap_length(tel, lap_time)
out["t"] = np.interp(grid, np.r_[0, s, L_ref],
                           np.r_[0, tel["t"].to_numpy(), lap_time])
delta = B["t"] - A["t"]
ms = np.digitize(grid, edges[1:-1])            # mini-sector index per grid point
ax.fill_between(grid, 0, delta, where=delta > 0, alpha=0.3)
''')
BUL(["`np.r_[0, s, L_ref]` concatenates scalars and arrays, pinning t = 0 at the line and t = lap time at the end. As a result, Δt starts at exactly 0 and ends at exactly the official gap.",
     "`np.digitize(x, bins)` returns which bin each value falls into.",
     "`fill_between(..., where=mask)` shades only the regions where the condition is true."])
H("Results", 3)
TABLE([["", "NOR (pole)", "LEC (P4)"],
       ["Lap time", "79.327 s", "79.461 s (+0.134)"],
       ["Top speed", "347 km/h", "**351 km/h**"],
       ["Min speed, Ascari / Parabolica", "**194 / 215 km/h**", "191 / 209 km/h"],
       ["Mini-sectors won", "10", "15"]], widths=[6, 4.5, 4.5])
P("Leclerc's lower-drag Ferrari was faster on every straight (he wins more mini-sectors and leads by 0.07 s "
  "at the end of the main straight). Norris braked later and carried 3 to 6 km/h more minimum speed through the "
  "Lesmos, Ascari and Parabolica. The delta trace jumps at each of those corners: corners decided pole, not "
  "straights.")
FIG(B / "03_telemetry_comparison/outputs/telemetry_comparison.png", "Figure B3a - Speed, delta, throttle, brake and gear vs distance")
FIG(B / "03_telemetry_comparison/outputs/minisector_map.png", "Figure B3b - Mini-sector dominance map", 12)
P("**Resume bullet:** *Engineered a distance-aligned telemetry comparison tool (interpolation, delta-time, "
  "mini-sector analysis) that pinpoints where F1 drivers gain time, reproducing the official 0.134 s gap.*")

# =====================================================================
# 4 summary
# =====================================================================
H("4. Putting it on your resume", 1)
P("Suggested project entry:")
p = doc.add_paragraph()
_shade(p, "FBEAEA")
rich(p, "**F1 Engineering & Telemetry Analytics Portfolio** | Python, NumPy, pandas, SciPy, Matplotlib, OpenF1 API")
BUL([
    "Built six analysis tools on real 2024 Formula 1 timing and telemetry data, with a cached API client and a reproducible CSV dataset.",
    "Signal processing: STFT + harmonic-sum tracker estimating engine RPM from audio with 0.12 % error.",
    "Physics: identified an aerodynamic braking model from telemetry by least squares (3 m vs 29 m error).",
    "Statistics: fuel-corrected, fixed-effects tyre degradation regression with 95 % confidence intervals.",
    "Visualisation: speed-coloured track maps, timing screen with Excel export, and distance-aligned delta-time comparison.",
])
H("Ideas to extend", 2)
BUL(["Run the scripts on other circuits (`--circuit Silverstone`, `Monaco`, `Spa-Francorchamps`) and compare.",
     "Record a real onboard clip with Audacity and use `--wav`.",
     "Add a tyre-strategy simulator: optimise pit lap(s) from the fitted degradation, pit-loss and fuel models.",
     "Turn B3 into an interactive Streamlit / Plotly dashboard.",
     "With an F1 account, port `f1data.py` to FastF1 (see `external_repos/Fast-F1/examples`)."])

out = ROOT / "F1_Projects_Documentation.docx"
doc.save(out)
print(f"Saved {out}")
