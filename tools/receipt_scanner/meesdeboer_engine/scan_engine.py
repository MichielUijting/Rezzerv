"""De lezer: één bonfoto (of PDF) in, gestructureerde bongegevens uit.

Draaide eerst als eigen service (scanner/), die rezzerv/scanning.py byte-
voor-byte doorproxyde over http. Nu in-process: één image, één proces, geen
REZZERV_SCANNER_URL meer om verkeerd te zetten. Prijs daarvoor: dit proces
heeft nu ook OpenCV, een ONNX-model en zijn eigen Claude-calls nodig, dus de
image is zwaarder dan een kaal Flask+SQLite-app anders zou zijn.

Twee stappen, elk een losse functie zodat de capture-UI ertussen kan
bijsturen: eerst DocAligner-hoekdetectie + perspectiefcorrectie
(decode_image, detect, extract_crop), dan de rechtgetrokken foto
rechtstreeks als afbeelding naar Claude (parse_receipt_from_image) — geen
OCR-tussenstap. Een PDF slaat stap één over en gaat als tekst naar Claude
(parse_receipt_from_pdf).
"""

import io
import base64
from datetime import datetime
from decimal import Decimal
from typing import Literal

import anthropic
import cv2
import numpy as np
import pydantic
from capybara import pad
from docaligner import DocAligner
from pydantic import BaseModel, Field
from pypdf import PdfReader


class ScanError(Exception):
    """Een leesfout met de HTTP-status er al aan vast, zodat een route-
    handler maar op dit ene type hoeft te vangen en niet zelf per faalmodus
    hoeft te beslissen welke status erbij hoort."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


model = DocAligner(model_cfg="fastvit_sa24")

# key komt uit ANTHROPIC_API_KEY (via rezzerv/wsgi.py's load_dotenv, een al
# gezette env-var, of een `ant auth login`-profiel — in die volgorde).
# Anthropic() zelf raakt hier nooit in de fout: ontbreekt de sleutel, dan
# faalt pas de eerste écht aanroep (zie _call_claude), en de rest van de app
# moet ook zonder sleutel gewoon opstarten.
claude = anthropic.Anthropic()
CLAUDE_MODEL = "claude-sonnet-5"

# Padding rond het beeld vóór inferentie, zoals in de officiële DocAligner-
# demo. Het heatmap-model kan geen piek leggen op de beeldrand zelf; zonder
# deze marge vallen hoekpunten die (bijna) op de rand liggen weg. Op de
# testset maakt dit het verschil tussen 4/6 en 6/6 gedetecteerde bonnetjes.
PAD = 100

# Vaste werkbreedte waarnaar elk beeld eerst wordt geschaald vóór padding.
# PAD is een vast aantal pixels; op een hoge-resolutie foto (bv. een volle
# 1920x1080 camera-capture) met een strak in beeld gefotografeerd bonnetje
# is diezelfde 100px na de interne resize van het model naar 256x256 een
# veel kleinere relatieve marge dan op een klein frame — getest: op 640px
# breed altijd 4/4 hoekpunten, op 1080px/1920px zakte dat naar 3 of 2 punten
# bij strakke framing. Door hier altijd naar dezelfde werkbreedte te
# schalen gedraagt live-preview (die toevallig al ~640px stuurt) en de
# losse foto-capture (die de volle resolutie stuurt) zich identiek.
WORK_WIDTH = 640


def decode_image(raw_bytes: bytes) -> np.ndarray:
    data = np.frombuffer(raw_bytes, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Kon afbeelding niet decoderen")
    return img


def order_points(pts: np.ndarray) -> np.ndarray:
    """Herordent 4 punten naar [top-left, top-right, bottom-right, bottom-left].

    DocAligner's puntvolgorde volgt de kanalen van het heatmap-model, niet
    gegarandeerd de geometrische ligging in het beeld. In plaats daarvan
    nemen we eerst de convex hull: die geeft de 4 punten gegarandeerd terug
    als 4 losse punten in geldige cyclische volgorde (geen duplicaten, geen
    zelfkruising) — een naïeve sum/diff-heuristiek per hoek apart kan bij
    rotaties rond de 45-60 graden dezelfde punt tweemaal kiezen en de
    perspective transform singulier maken.
    Het hoekpunt met de kleinste y (dus bovenin de brongfoto) wordt de
    starthoek en komt zo bovenaan in de uitsnede terecht. Bij extreme
    rotaties kan de gekozen starthoek nog steeds 90 graden verschuiven
    t.o.v. de leesrichting — dat vangt de auto-rotate in extract_crop en de
    Roteer-knop in de UI op.
    """
    pts = pts.astype(np.float32)
    hull = cv2.convexHull(pts).reshape(-1, 2)
    if len(hull) != 4:
        return pts  # gedegenereerde (bijna-collineaire) invoer; niets te herordenen
    # puur op y (niet x+y): bij een sterk gedraaide bon in beeld kan de
    # x-component de verkeerde hoek laten "winnen" ook al ligt een andere
    # hoek overduidelijk hoger in het beeld
    start = np.argmin(hull[:, 1])
    return np.roll(hull, -start, axis=0).astype(np.float32)


def detect(img_bgr):
    """Eén enkele ML-pass. Vóór de pad-fix was een tweede crop+refine-pass
    nodig om hoekpunten te redden die op de beeldrand wegvielen. Met padding
    vindt deze ene pass alle 4 hoekpunten al net zo precies (getest: <7px
    verschil t.o.v. de oude 2-pass variant op foto's van 3000-5000px breed)
    in de helft van de tijd.
    """
    h, w = img_bgr.shape[:2]
    scale = WORK_WIDTH / w
    small = cv2.resize(img_bgr, (WORK_WIDTH, max(1, round(h * scale))))

    padded = pad(small, PAD)
    poly = model(img=padded, do_center_crop=False)
    if len(poly) != 4:
        return None
    corners = (np.array(poly, dtype=np.float32) - PAD) / scale
    return order_points(corners)


def extract_crop(img_bgr: np.ndarray, pts: np.ndarray) -> bytes:
    """Perspectiefcorrigeerde uitsnede uit `img_bgr`, als JPEG-bytes."""
    pts = order_points(pts)
    tl, tr, br, bl = pts
    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)
    out_w = max(int(max(width_top, width_bottom)), 50)
    out_h = max(int(max(height_left, height_right)), 50)

    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(pts, dst)
    warped = cv2.warpPerspective(img_bgr, M, (out_w, out_h))

    # Bonnetjes zijn vrijwel altijd smalle, staande stroken. Bij rotaties
    # rond de 45-60 graden is er geen eenduidig geometrisch "boven-links"
    # meer te bepalen (order_points kan dan alsnog 90 graden mis zitten),
    # dus als het resultaat breder dan hoog is, roteren we het automatisch
    # rechtop. De ↻ Roteer-knop in de UI blijft het handmatige vangnet.
    if warped.shape[1] > warped.shape[0]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

    ok, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise ScanError("encoderen mislukt", 500)
    return buf.tobytes()


# ---------- vision-LLM structurering (geen OCR-tussenstap) ----------
# Het `kind`-veld onderscheidt gewone productregels van het losse subtotaal/
# zegel-blok. Dat gebeurt bewust bínnen `lines` en niet als een tweede
# top-level veld ernaast: structured outputs strandde met zo'n extra veld op
# "Grammar compilation timed out" / "Schema is too complex", reproduceerbaar
# op zowel Haiku als Sonnet. Eén lijst met een discriminator blijft wel
# binnen wat de grammatica aankan.
class ReceiptLineItem(BaseModel):
    kind: Literal["product", "adjustment"] = "product"
    raw_label: str
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    line_total: float | None = None
    discount_amount: float | None = None


class StructuredReceipt(BaseModel):
    store_name: str | None = None
    store_branch: str | None = None
    purchase_at: datetime | None = None  # herkenbaar op de bon, anders null — pydantic parseert de ISO 8601-string van de LLM naar een echt datetime-object
    currency: str = "EUR"
    total_amount: float | None = None
    lines: list[ReceiptLineItem] = Field(default_factory=list)


# gedeeld met PARSE_SYSTEM_PROMPT_PDF hieronder: alleen de openingszin
# verschilt tussen de vision- en de pdf-route (afbeelding vs. platte tekst),
# de rest van de regels (kind/discount/teken-logica) is identiek
PARSE_SYSTEM_PROMPT_RULES = (
    "Regels: gebruik alleen bedragen/aantallen die letterlijk op de bon "
    "staan (nooit rekenen of aanvullen); bij twijfel over een veld, laat "
    "het null; sla btw-regels, betaalmethodes en subtotaalregels zelf over "
    "in `lines` (alleen product/artikel- en aanpassingsregels, zie "
    "hieronder); "
    "elke regel heeft een `kind`: 'product' voor een gewone product-/"
    "artikelregel, 'adjustment' voor een losse regel die NIET bij één "
    "specifieke productregel hoort. "
    "BESLISREGEL voor dit onderscheid (belangrijk, dit gaat vaak fout): kijk "
    "naar de POSITIE. Staat de regel DIRECT onder één specifieke "
    "productregel, met niets ertussen (typisch: 'korting', 'bonus', "
    "'actie', 'geeft meer voordeel!', een giftcard-regel die overduidelijk "
    "bij dat ene artikel hoort)? Dan is het GEEN eigen regel, ook al lijkt "
    "het label op een zegel/actie - verwerk het bedrag in `discount_amount` "
    "van die productregel (de regel er direct BOVEN) en maak er nooit een "
    "apart kind='adjustment'-item van. "
    "Staat de regel LOS - niet direct onder één identificeerbaar artikel, "
    "vaak in een blokje na een 'subtotaal'-regel (zegels, actiekortingen, "
    "cadeaubonnen, klantenkaartpunten, gespaarde zegels) - dan is het wél "
    "kind='adjustment'. Voorbeelden: '1X ZEGEL/DANIO -2,05', "
    "'14X PLUSPUNTEN 0,28'. "
    "voor kind='adjustment' vul alleen `raw_label` en `line_total` - laat "
    "quantity/unit_price/discount_amount null; "
    "sla SAMENVATTINGSREGELS helemaal over: regels als 'UW VOORDEEL', "
    "'Waarvan ...' of een uitsplitsing daaronder vatten kortingen samen "
    "die elders op de bon al als eigen regel staan - die tellen dubbel "
    "als je ze opneemt, dus nooit in `lines` zetten; "
    "TEKEN van `line_total` bij kind='adjustment': lees het teken ALTIJD "
    "letterlijk over van de bon, gok het NOOIT op basis van wat voor soort "
    "regel het is. Zegels/spaaracties zijn niet per definitie een korting - "
    "sommige (bv. het kopen/sparen van PLUS-zegels) kosten juist geld en "
    "staan dus POSITIEF op de bon, andere (het inwisselen van een zegel/"
    "actie als korting) staan NEGATIEF. Kopieer exact het teken (of het "
    "ontbreken ervan) zoals gedrukt, verzin het niet zelf; "
    "`discount_amount` (bij kind='product') is altijd een POSITIEF getal "
    "(de grootte van de korting), ook als de bon 'm met een minteken toont; "
    "voor kind='product' is `line_total` altijd het volledige regelbedrag "
    "(aantal × unit_price, of gewoon de prijs bij aantal 1) - vul dit veld "
    "altijd, ook als er maar 1 stuk is en het bedrag gelijk is aan "
    "unit_price; "
    "`total_amount` is het bedrag achter het expliciete 'totaal'-label op de "
    "bon, nooit de som van de regels."
)

PARSE_SYSTEM_PROMPT = (
    "Je krijgt een foto van een Nederlandse kassabon. Haal er de "
    "winkelgegevens en productregels uit volgens het gegeven schema, "
    "rechtstreeks van de afbeelding (er is geen OCR-tussenstap - lees de "
    "afbeelding zelf, ook als tekst er onscherp of klein uitziet). "
) + PARSE_SYSTEM_PROMPT_RULES

PARSE_SYSTEM_PROMPT_PDF = (
    "Je krijgt de tekst uit een PDF van een Nederlandse kassabon of "
    "factuur, letterlijk uit het PDF-bestand geëxtraheerd (geen OCR, dus "
    "geen scanfouten - al kan de volgorde/witruimte door de extractie iets "
    "afwijken van de originele opmaak op de pagina). Haal er de "
    "winkelgegevens en productregels uit volgens het gegeven schema. "
    "De artikelen staan meestal als tabelrijen in de tekst: een aantal, "
    "dan de omschrijving, dan (na veel spaties) het bedrag - bv. "
    "'1   POEDERSUIKER   1,19'. Elke zo'n rij is een kind='product'-regel "
    "in `lines`; neem ze ALLEMAAL op. Rijen zonder bedrag met alleen een "
    "kaart-/klantnummer (bv. 'BONUSKAART xx1234', 'AIRMILES NR.') zijn "
    "geen producten en horen nergens in `lines`. "
) + PARSE_SYSTEM_PROMPT_RULES


def totals_match(receipt: StructuredReceipt, tolerance: Decimal = Decimal("0.05")) -> bool:
    if receipt.total_amount is None:
        return False
    # line_total is het brutobedrag op de productregel (zie system prompt);
    # een eronder staande kortingsregel is al in discount_amount van diezelfde
    # regel verwerkt en moet daarom hier per regel worden afgetrokken. Maar
    # in de praktijk vult het model line_total soms al NETTO (na korting)
    # terwijl discount_amount ook gevuld blijft — dan zou aftrekken de
    # korting dubbel tellen. Vangnet: vergelijk line_total met aantal x
    # unit_price (de brutoprijs); als line_total al overeenkomt met
    # gross-discount, is 'm al netto en wordt er niet nogmaals afgetrokken.
    # kind='adjustment'-regels (zegels/acties/punten) tellen met hun eigen
    # teken direct mee, geen aftrek nodig. Extra vangnetten (in de praktijk
    # gezien): (1) line_total soms null met alleen unit_price gevuld ->
    # afleiden uit aantal x unit_price; (2) discount_amount soms negatief
    # meegegeven (letterlijk overgenomen mintekens van de bon) -> absolute
    # waarde nemen, nooit optellen i.p.v. aftrekken.
    line_sum = Decimal("0")
    for line in receipt.lines:
        if line.kind == "adjustment":
            if line.line_total is not None:
                line_sum += Decimal(str(line.line_total))
            continue
        amount = line.line_total
        if amount is None and line.unit_price is not None:
            qty = line.quantity if line.quantity is not None else 1
            amount = qty * line.unit_price
        if amount is None:
            continue
        net = Decimal(str(amount))
        if line.discount_amount is not None:
            discount = abs(Decimal(str(line.discount_amount)))
            gross = None
            if line.unit_price is not None:
                qty = Decimal(str(line.quantity)) if line.quantity is not None else Decimal("1")
                gross = qty * Decimal(str(line.unit_price))
            already_net = gross is not None and abs(net - (gross - discount)) <= tolerance
            if not already_net:
                net -= discount
        line_sum += net
    return abs(line_sum - Decimal(str(receipt.total_amount))) <= tolerance


# Claude schaalt elk beeld intern sowieso terug tot een model-afhankelijk
# maximum (Sonnet 5: 2576px lange zijde bij high-res vision) — grotere
# beelden versturen kost dus alleen extra upload-/verwerkingstijd en tot 3x
# meer beeld-tokens, zonder betere leeskwaliteit. 1600px is ruim voldoende
# voor bontekst (in tegenstelling tot bv. fijne productfoto-details) en
# blijft ruim boven wat nodig is om ook onscherpe tekst nog te lezen — dat
# was juist de reden om over te stappen op vision i.p.v. OCR.
MAX_IMAGE_DIMENSION = 1600


def build_image_content_block(image_bytes: bytes, media_type: str) -> dict:
    img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is not None:
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest > MAX_IMAGE_DIMENSION:
            scale = MAX_IMAGE_DIMENSION / longest
            img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                image_bytes = buf.tobytes()
                media_type = "image/jpeg"
    data = base64.standard_b64encode(image_bytes).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def _call_claude(system_prompt: str, user_content) -> StructuredReceipt:
    """Roept Claude aan volgens het StructuredReceipt-schema en vangt alle
    foutafhandeling op één plek af — gedeeld door de vision- en de pdf-route,
    die verder alleen in system_prompt/user_content verschillen."""
    try:
        response = claude.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            # systeeminstructies zijn statisch en deze endpoints worden
            # herhaaldelijk aangeroepen — cache_control is hier veilig ook
            # als de prompt onder het cache-minimum zit (dan gewoon geen
            # cache-hit, geen foutmelding)
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_content}],
            output_format=StructuredReceipt,
        )
        return response.parsed_output
    except anthropic.RateLimitError as e:
        print(f"[claude] RateLimitError: {e.message}")
        raise ScanError("LLM tijdelijk overbelast, probeer zo opnieuw", 503) from e
    except anthropic.APIStatusError as e:
        # volledige foutmelding altijd loggen — de client krijgt alleen de
        # statuscode, anders is dit op afstand niet te debuggen
        print(f"[claude] APIStatusError {e.status_code}: {e.message}")
        raise ScanError(f"LLM-fout ({e.status_code}): {e.message}", 502) from e
    except anthropic.APIConnectionError as e:
        print(f"[claude] APIConnectionError: {e}")
        raise ScanError("geen verbinding met de LLM-API", 502) from e
    except TypeError as e:
        # de SDK gooit TypeError als er geen enkele credential te vinden is
        raise ScanError(
            "geen Anthropic API-key: zet ANTHROPIC_API_KEY in .env, of draai `ant auth login`",
            503,
        ) from e
    except pydantic.ValidationError as e:
        # messages.parse() valideert de modeloutput tegen het schema; als
        # Claude leeg of kapot JSON teruggeeft (bv. door een afgekapte
        # generatie) gooit de SDK dit voordat wij een response-object zien —
        # zonder deze except crasht de request met een onbeheerde 500
        print(f"[claude] ValidationError (waarschijnlijk lege/kapotte modeloutput): {e}")
        raise ScanError("onverwerkbaar antwoord van het model, probeer opnieuw", 502) from e


def parse_receipt_from_image(image_bytes: bytes, mimetype: str) -> dict:
    content_block = build_image_content_block(image_bytes, mimetype or "image/jpeg")
    receipt = _call_claude(PARSE_SYSTEM_PROMPT, [
        content_block,
        {"type": "text", "text": "Extraheer de bongegevens volgens het schema uit deze foto."},
    ])
    return {
        # mode="json" serialiseert purchase_at (een datetime-object) terug
        # naar een ISO 8601-string i.p.v. Python's eigen repr
        "receipt": receipt.model_dump(mode="json"),
        "totals_match": totals_match(receipt),
    }


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    # extraction_mode="layout" i.p.v. de default: veel PDF-generators
    # tekenen een tabel kolom voor kolom (eerst alle omschrijvingen, dan
    # alle bedragen) i.p.v. rij voor rij. De default modus volgt die
    # tekenvolgorde 1-op-1, waardoor productregels en prijzen losraken van
    # elkaar in de geëxtraheerde tekst. "layout" reconstrueert de visuele
    # posities zodat elke rij weer op één regel staat.
    return "\n".join(
        page.extract_text(extraction_mode="layout") or "" for page in reader.pages
    ).strip()


def parse_receipt_from_pdf(pdf_bytes: bytes) -> dict:
    try:
        pdf_text = extract_pdf_text(pdf_bytes)
    except Exception as e:
        # pypdf gooit uiteenlopende exception-types op kapotte/versleutelde
        # PDF's — breed vangen is hier bewust, want elke variant leidt tot
        # dezelfde nette foutmelding i.p.v. een 500
        print(f"[parse_receipt_from_pdf] PDF-tekst extractie mislukt: {e}")
        raise ScanError("kon dit bestand niet als PDF lezen", 422) from e
    if not pdf_text:
        # bv. een gescande PDF zonder echte tekstlaag — daar is dit pad niet
        # voor bedoeld (dat zou de vision-route via een foto/screenshot
        # nodig hebben, niet tekstextractie)
        raise ScanError(
            "geen tekst gevonden in deze PDF (mogelijk een scan zonder "
            "tekstlaag — probeer een foto van de bon i.p.v. de PDF)",
            422,
        )

    receipt = _call_claude(
        PARSE_SYSTEM_PROMPT_PDF,
        "Extraheer de bongegevens volgens het schema uit deze PDF-tekst:\n\n" + pdf_text,
    )
    return {
        "receipt": receipt.model_dump(mode="json"),
        "totals_match": totals_match(receipt),
    }
