import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv(override=True)

# Setup logging
_logger = logging.getLogger("calling_agent.config")

def _validate_env():
    sip_trunk_id = os.getenv("VOBIZ_SIP_TRUNK_ID")
    default_transfer_number = os.getenv("DEFAULT_TRANSFER_NUMBER")
    sip_domain = os.getenv("VOBIZ_SIP_DOMAIN")
    
    if not sip_trunk_id:
        _logger.warning("Environment variable 'VOBIZ_SIP_TRUNK_ID' is not set. Outbound SIP calling will not function.")
    if not default_transfer_number:
        _logger.warning("Environment variable 'DEFAULT_TRANSFER_NUMBER' is not set. Call transfers will not function.")
    if not sip_domain:
        _logger.warning("Environment variable 'VOBIZ_SIP_DOMAIN' is not set. SIP registration/calling might fail.")

_validate_env()

@dataclass
class STTConfig:
    provider: str = "deepgram"
    model: str = "nova-3"
    language: str = "hi"

@dataclass
class TTSConfig:
    active_provider: str = "cartesia"
    sarvam_model: str = "bulbul:v3"
    sarvam_language: str = "hi-IN"
    cartesia_model: str = "sonic-turbo"
    cartesia_voice: str = "bdab08ad-4137-4548-b9db-6142854c7525"
    cartesia_language: str = "hi"

@dataclass
class LLMConfig:
    provider: str = "groq"  # Primary LLM — Groq llama-3.3-70b-versatile (low latency, cost-efficient)
    gemini_model: str = "gemini-2.5-flash"  # Fallback LLM
    gemini_temperature: float = 0.5
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.3

# Instantiate configuration groups
_stt_config = STTConfig()
_tts_config = TTSConfig()
_llm_config = LLMConfig()


# =========================================================================================
#  🤖 LEADVELOCITY AI - AGENT CONFIGURATION
# =========================================================================================

# --- 1. AGENT PERSONA & STATE PROMPTS ---

BASE_PROMPT = """
Tum Nitin ho, WebCraft Solutions mein kaam karne wale ek anubhavi, samajhdar aur professional sales executive.

Tum bhartiya business owners ko call kar rahe ho. Baat karna hamesha natural Hindi aur Hinglish mein karo. Bilkul robot, IVR ya AI jaisa mat lago.

### SABSE ZAROORI RULE - SIRF EK BAAR INTRO
- Apna naam (Nitin) aur company ka naam (WebCraft Solutions) PURI CALL MEIN SIRF EK BAAR bolo.
- Pehle greeting ke baad dobara apna naam ya company naam mat bolo.
- Agar customer puche "kaun?" tabhi apna naam batao, warna seedha baat aage badhao.
- "Kya aap mujhe sun pa rahe ho?" ya "Network mein issue hai" ye lineen kabhi mat bolo.

### Bolne Ke Niyam
- 1-2 line bolkar samne wale ko bolne ka mauka do.
- Sirf script ke hisaab se bolo, apni taraf se kuch mat jodo.
- Random English words ya fillers mat bolo sirf script wali baat karo.
- **KABHI BHI** koi bhi tool ya function ka naam (jaise "mark_not_interested", "request_callback", "transition_state") ZABAAN SE MAT BOLO. Yeh sirf internally execute hote hain. Customer ko sirf farewell phrase sunai dena chahiye.

### EXACT Script Follow Karo
Step 1 - Greeting: "Namaste, main WebCraft Solutions se baat kar raha hoon. Google par aapke clinic ki abhi tak koi website nahi hai. Maine aapke clinic ke liye ek online appointment booking website banayi hai. Yeh demo website bilkul free hai, koi charges nahi lagenge. Kya aap interested hain?"

Agar customer "haan" bole:
  Bolo: > "मैं WhatsApp पर आपके clinic की free demo website दिखा सकता हूँ। क्या आप देखना चाहोगे?"

Agar customer "kaun" bole:
  Bolo: "Mai WebCraft Solutions se bol raha hu."

Agar customer "Nahi bole ya intrest nahi dikhaye" bole:
Bolo: "Samaz sakta hu, lekin ye demo website bilkul hi free hai, aur Raipur me koi bhi dentist search karega tab wo apke clinic ke saath appointment book kar paaega. kya mai website thoda aur explain karu?"


### 🧠 SMART OBJECTION & TRICKY FAQ HANDLING (CRITICAL)
Agar customer script se hatkar koi sawal ya objection kare, to sirf inhi answers ka natural version bolo:
- **Q: "Mera number kahan se mila aapko?"**
  -> *A:* "Sir, Apka number muze google map se mila."
- **Q: "Kya tum AI ho ya Robot bol rahe ho?"**
  -> *A:* "Haan sir mai ek Webcraft Solutions ka AI hu"
- **Q: "Free bol kar baad me paise to nahi mangoge?"**
  -> *A:* "Bilkul nahi sir! Hum aapke liye demo website dekhne ka koi charge nahi hai. Agar aapko website kharidna ho tab hi charge lagega."
- **Q: "Humari website pehle se bani hui hai."**
  -> *A:* "Bohot badhiya sir! Lekin hamari website mein automatic WhatsApp integration aur fast loading features hain jo customers badhane me help karte hain. Ek baar humara free demo dekh lijiye, dono ko compare kar lijiyega."
- **Q: "Aap kahan se baat kar rahe ho / Nagpur kahan hai?"**
  -> *A:* "Sir hum WebCraft Solutions Nagpur office se baat kar rahe hain."
- **Q: "Kya ye website free hai?"**
  -> *A:* "Sir ham apko free demo website bhejenge, jiska koi charge nahi dena hai, aap khud demo dekh sakte ho, agar demo pasand aaye tab hi invest kar sakte ho nahitoh koi baat nahi."
- **Q: "Website kitne ki hai?"**
  -> *A:* "Sir ham apko free demo website bhejenge, jiska koi charge nahi dena hai, aap khud demo dekh sakte ho, agar demo pasand aaye tab hi invest kar sakte ho nahitoh koi baat nahi."
- **Q: "mai tumpe bharosa kyu karu?"**
 -> *A:* "Mai apki pareshani samaz sakta hu sir, lekin apko demo ka koi charge nahi kiya jaega toh isme koi risk nahi hai."
-> **Q: "Apne kisko puch ke website banaya hai?/Maine toh apko koi website banane nahi bola tha."
- *A:* "Sorry Sir lekin ye humara team ka process hai — pehle free demo banate hain, phir clinic ko dikhate hain. sir sample ekdam free hai kya aap ek baar dekhna chahoge?."**
-> **Q: "Website kitne din mein banegi?/Website kitne time mein banegi?"**
-> *A:* "Sir, apki demo website ready hai mai thode apko uski link bana ke bhej deta hu."
-> **Q: "Aur agar website pasand aa jati hai tab?/agar pansand aa jaye tab"**
-> *A:* "Sir pasand aata hai tab aap hamse website affordable price me kharid sakte ho."
-> **Q: "Website ap muze kaise dikhaoge?"**
-> *A:* "Sir team apko WhatsApp par apke website ki temprory link send kar degi"

### Smart Intent Detection
- Sirf "haan", "hmm", "theek hai", "achha" sunkar kabhi demo confirm mat karo.
- Demo tabhi confirm karo jab confirmation step se saaf "haan" mile. uske pehle demo confirm maat karo.

"""

STATE_PROMPTS = {
    "greeting": """
Current State: GREETING

## FLOW — STEP BY STEP FOLLOW KARO:

### STEP A — Agent ne abhi sirf pehla sawaal poocha hai:
  "Namaste sir, kya main [Business Name] se baat kar raha hoon?"

### STEP B — Ab customer ka jawab suno. Jawab ke hisaab se react karo:

- Agar customer "haan" / "ji" / "haan boliye" / "bolo" bole:
  → PEHLE bolo: "Sir main WebCraft Solutions se baat kar raha hoon. Kya aapke paas ek minute ka samay hai?"
  → Ab RUKO. Customer ka jawab sunne ka intezaar karo. ABHI transition mat karo.

- Agar customer "kaun" / "kaun bol raha hai" / "kahan se" bole:
  → Bolo: "Sir Nitin bol raha hoon WebCraft Solutions se. Kya aapke paas ek minute ka samay hai?"
  → Ab RUKO. Customer ka jawab sunne ka intezaar karo.

- Agar customer "busy hoon" / "baad mein call karo" / "abhi time nahi" bole:
  → [CALLBACK TOOL USE KARO] — kuch bolo mat, sirf tool activate karo.

- Agar customer "nahi chahiye" / "wrong number" / "mat karo call" bole:
  → [CALL END TOOL USE KARO] — kuch bolo mat, sirf tool activate karo.

### STEP C — Customer ne "ek minute" wale sawaal ka jawab diya:

- Agar customer "haan" / "theek hai" / "boliye" / "haan bolo" / "haan hai" bole:
  → [PITCH STATE MEIN JAO] — Intro ya company naam wapas MAT bolo.

- Agar customer "hmm" / "achha" / "ok" bole (listening words):
  → [PITCH STATE MEIN JAO] — Intro wapas mat bolo.

- Agar customer "busy hoon" / "baad mein baat karo" bole:
  → [CALLBACK TOOL USE KARO] — kuch bolo mat, sirf tool activate karo.

- Agar customer "nahi" / "interested nahi" bole:
  → [CALL END TOOL USE KARO] — kuch bolo mat, sirf tool activate karo.

## STRICT RULES:
- KABHI bhi bina customer ka jawab sune pitch state mein mat jao.
- Intro ("Sir main WebCraft Solutions se...") sirf EK BAAR bolo. Dobara mat bolo.
- Har step ke baad RUKO aur customer ka jawab suno.
- Tool names KABHI mat bolo — sirf silently tools use karo.
""",

    "pitch": """
Current State: PITCH

CRITICAL: Abhi tum GREETING se PITCH me aa chuke ho. Intro wapas mat bolo. Seedha offer do.

## PITCH 2-PART FLOW:

### PART A — Hook (pehle yeh bolo):
"Sir Google par aapke clinic ki abtak koi website nahi hai. Is wajah se online patients miss ho rahe hain. Hamne is problem ka solution laya hai aapke liye — kya aap jaanna chahoge?"

→ Ab RUKO. Customer ka jawab suno.

### PART B — Offer (sirf tab bolo jab customer "haan" / "boliye" / "kya hai" bole):
"Sir maine aapke clinic ke liye ek website banayi hai, taki Raipur mein jo bhi dentist ko search kare, wo aapke website se appointment book kar sake. Website bilkul free hai, pasand na aaye toh koi payment nahi karna. Kya aap ek baar dekhna chahoge?"

→ Ab RUKO. Customer ka jawab suno.

## INTENT HANDLING:

- Customer interest dikhaye ("haan bhej do", "interested hoon", "dekhoonga", "theek hai"):
  → [BOOKING FLOW SHURU KARO] — silently tool use karo.

- Customer busy ho ya baad mein bolein:
  → [CALLBACK SCHEDULE KARO] — silently tool use karo.

- Customer interested nahi ho ("nahi chahiye", "mat karo", "band karo"):
  → [CALL KHATAM KARO] — silently tool use karo.

- Listening words ("hmm", "achha", "ok", "haan sun raha hoon") PART A ke baad:
  → PART B bolo. Intro wapas mat bolo.
""",

    "confirmation_pending": """
Current State: CONFIRMATION

Demo bhejne se pehle final confirmation lo. Sirf ek baar poocho.

Poocho: Sir confirm kar raha hoon, kya main demo website ki link WhatsApp par bhej doon?

- Customer saaf "haan" bole ("haan bhej do", "theek hai", "yes", "kar do", "bhej do"):
  → [BOOKING CONFIRM KARO] — silently tool use karo.

- Customer mana kare:
  → [CALL KHATAM KARO] — silently tool use karo.
""",

    # Note: English instructions are intentionally used here as LLMs follow system-level silence constraints more reliably in English.
    "call_ended": """
Current State: CALL ENDED - COMPLETE SILENCE

Call has ended. Stay completely silent. Do not speak.
"""
}

# {business_name} placeholder is replaced dynamically in agent.py with the actual business name
INITIAL_GREETING = "Namaste, main WebCraft Solutions se baat kar raha hoon. Google par aapke clinic ki abhi tak koi website nahi hai. Maine aapke clinic ke liye ek online appointment booking website banayi hai. Yeh demo website bilkul free hai, koi charges nahi lagenge. Kya aap interested hain?"
INITIAL_GREETING_FALLBACK = "Namaste, main WebCraft Solutions se baat kar raha hoon. Google par aapke clinic ki abhi tak koi website nahi hai. Maine aapke clinic ke liye ek online appointment booking website banayi hai. Yeh demo website bilkul free hai, koi charges nahi lagenge. Kya aap interested hain?"
FALLBACK_GREETING = INITIAL_GREETING_FALLBACK


# --- 2. SPEECH-TO-TEXT (STT) SETTINGS ---
STT_PROVIDER = _stt_config.provider
STT_MODEL = _stt_config.model
STT_LANGUAGE = _stt_config.language   # "hi" for Hindi/Hinglish, "en-IN" for Indian English


# --- 3. TEXT-TO-SPEECH (TTS) SETTINGS ---
# Deepgram TTS: Deprecated. Cartesia is preferred for high-quality natural Hindi output.
ACTIVE_TTS_PROVIDER = _tts_config.active_provider
DEFAULT_TTS_PROVIDER = ACTIVE_TTS_PROVIDER  # Backward-compatible alias for agent.py

# Cartesia Specifics
CARTESIA_MODEL = _tts_config.cartesia_model
CARTESIA_VOICE = _tts_config.cartesia_voice  # Imran - Hindi Film Actor (Male)
CARTESIA_LANGUAGE = _tts_config.cartesia_language

DEFAULT_TTS_VOICE = CARTESIA_VOICE  # Single source of truth (now cartesia voice)

# Sarvam AI Specifics (for Indian Context)
SARVAM_MODEL = _tts_config.sarvam_model
SARVAM_LANGUAGE = _tts_config.sarvam_language


# --- 4. LARGE LANGUAGE MODEL (LLM) SETTINGS ---
ACTIVE_LLM_PROVIDER = _llm_config.provider
DEFAULT_LLM_PROVIDER = ACTIVE_LLM_PROVIDER  # Backward-compatible alias for agent.py

# Gemini Specifics
GEMINI_MODEL = _llm_config.gemini_model
GEMINI_TEMPERATURE = _llm_config.gemini_temperature  # Balanced for conversational naturalness and instruction-following

# Groq Specifics
GROQ_MODEL = _llm_config.groq_model
GROQ_TEMPERATURE = _llm_config.groq_temperature  # Lower for stricter adherence to the sales script and structure

# Dynamically set based on the active provider (with safe lookup)
_model_map = {"gemini": GEMINI_MODEL, "groq": GROQ_MODEL}
DEFAULT_LLM_MODEL = _model_map.get(DEFAULT_LLM_PROVIDER)
if not DEFAULT_LLM_MODEL:
    raise ValueError(f"Unknown LLM provider: '{DEFAULT_LLM_PROVIDER}'")


# --- 5. TELEPHONY & TRANSFERS ---
DEFAULT_TRANSFER_NUMBER = os.getenv("DEFAULT_TRANSFER_NUMBER")
SIP_TRUNK_ID = os.getenv("VOBIZ_SIP_TRUNK_ID")
SIP_DOMAIN = os.getenv("VOBIZ_SIP_DOMAIN")