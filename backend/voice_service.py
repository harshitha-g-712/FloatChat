"""
ArgoLens – Voice Interaction & Speech Processing Service
=========================================================
Provides:
  1. Marine Acoustic Transcript Normalizer (corrects domain homophones from speech-to-text)
  2. Phonetic Speech Preprocessor (expands scientific acronyms & units for natural TTS)
  3. Voice System Diagnostics & Capabilities
"""

import re
from typing import Dict, Any

# Domain replacements for speech recognition homophones
MARINE_SPEECH_REPLACEMENTS = [
    (r"\bthermo\s*cline[s]?\b", "thermocline"),
    (r"\bhalo\s*cline[s]?\b", "halocline"),
    (r"\bpycno\s*cline[s]?\b", "pycnocline"),
    (r"\bmixed\s*layer\s*depth\b", "mixed layer depth"),
    (r"\bm\s*l\s*d\b", "MLD"),
    (r"\bb\s*l\s*t\b", "BLT"),
    (r"\bs\s*o\s*f\s*a\s*r\b", "SOFAR"),
    (r"\bso\s*far\s*axis\b", "SOFAR axis"),
    (r"\bargo\s*float[s]?\b", "ARGO float"),
    (r"\bcargo\s*float[s]?\b", "ARGO float"),
    (r"\bp\s*s\s*u\b", "PSU"),
    (r"\bd\s*bars?\b", "dbar"),
    (r"\bdeep\s*bars?\b", "dbar"),
    (r"\bdeci\s*bars?\b", "dbar"),
    (r"\bbay\s*of\s*bangle\b", "Bay of Bengal"),
    (r"\bbay\s*of\s*bengal\b", "Bay of Bengal"),
    (r"\barabian\s*sea\b", "Arabian Sea"),
    (r"\bisopycnal[s]?\b", "isopycnal"),
    (r"\bsigma\s*theta\b", "sigma-theta"),
]

DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"
}


def normalize_marine_speech(raw: str) -> str:
    """
    Normalizes raw speech recognition transcripts by correcting common marine
    acoustic confusions and converting spoken platform digits into numbers.
    """
    if not raw:
        return ""
    text = raw.strip()

    # Apply acoustic homophone mappings
    for pattern, repl in MARINE_SPEECH_REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # Convert sequences of spoken digits (e.g. "two nine zero two seven five eight" -> "2902758")
    def _repl_digits(match):
        words = match.group(0).lower().split()
        return "".join(DIGIT_WORDS.get(w, w) for w in words)

    digit_pattern = r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine)(?:\s+(?:zero|one|two|three|four|five|six|seven|eight|nine)){6}\b"
    text = re.sub(digit_pattern, _repl_digits, text, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", text).strip()


def prepare_text_for_speech(text: str) -> str:
    """
    Transforms formatted scientific text into natural spoken English for Text-to-Speech (TTS).
    Expands units, removes citations/markdown, and optimizes oceanographic acronym pronunciation.
    """
    if not text:
        return ""
    clean = text

    # Remove markdown links [text](url) -> text
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    # Remove citation tags like [S1], [S2]
    clean = re.sub(r"\[S\d+\]", "", clean)
    # Remove markdown formatting characters
    clean = re.sub(r"[*_#`~]", "", clean)

    # Pronunciation overrides
    clean = re.sub(r"\bARGO\b", "Argo", clean)
    clean = re.sub(r"\bArgoLens\b", "Argo Lens", clean)
    clean = re.sub(r"\bSOFAR\b", "Sofar", clean)
    clean = re.sub(r"\bUNESCO\b", "Unesco", clean)
    clean = re.sub(r"\bCTD\b", "C T D", clean)
    clean = re.sub(r"\bMLD\b", "M L D", clean)
    clean = re.sub(r"\bSST\b", "S S T", clean)
    clean = re.sub(r"\bBLT\b", "B L T", clean)
    clean = re.sub(r"\bQC\b", "Q C", clean)
    clean = re.sub(r"\bT-S\b", "T S", clean, flags=re.IGNORECASE)

    # Units and symbols
    clean = re.sub(r"°C\b", " degrees Celsius", clean)
    clean = re.sub(r"\bpsu\b", " practical salinity units", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bdbar\b", " decibars", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bapprox\.", "approximately", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\bvs\.\b", "versus", clean, flags=re.IGNORECASE)
    clean = re.sub(r"(\d+)-(\d+)", r"\1 to \2", clean)
    clean = re.sub(r"\bσ\b", "sigma", clean)
    clean = re.sub(r"\bθ\b", "theta", clean)

    return re.sub(r"\s+", " ", clean).strip()


def get_voice_capabilities() -> Dict[str, Any]:
    """Returns active voice system configuration and supported features."""
    return {
        "speech_recognition": {
            "engine": "Web Speech API (webkitSpeechRecognition / SpeechRecognition)",
            "normalizer": "Marine Acoustic Transcript Normalizer",
            "supported_languages": ["en-US", "en-IN"],
            "features": ["Continuous listening", "Interim results", "Spoken digit conversion"]
        },
        "speech_synthesis": {
            "engine": "Web Speech Synthesis (SpeechSynthesisUtterance)",
            "preprocessor": "Oceanographic Phonetic Normalizer",
            "features": ["Automatic answer readout", "Listen/Stop toggle per message", "Acronym phonetic expansion"]
        },
        "marine_terms_supported": [
            "thermocline", "halocline", "pycnocline", "mixed layer depth",
            "MLD", "BLT", "SOFAR", "ARGO float", "PSU", "dbar", "Bay of Bengal", "isopycnal"
        ]
    }
