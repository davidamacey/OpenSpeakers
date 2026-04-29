"""Abstract base class for all TTS model implementations.

Every TTS model must subclass TTSModelBase and implement:
  - load(device)   — load weights to GPU/CPU
  - unload()       — free GPU memory
  - generate(req)  — synthesize speech from text

Voice-cloning models also implement:
  - clone_voice(audio_path, name) → dict metadata
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GenerateRequest:
    """Parameters for a single TTS synthesis request."""

    text: str
    voice_id: str | None = None  # built-in or cloned voice identifier
    speed: float = 1.0  # playback speed multiplier (0.5–2.0)
    pitch: float = 0.0  # semitone shift (-12 to +12)
    language: str = "en"  # BCP-47 language code
    extra: dict = field(default_factory=dict)  # model-specific extras


@dataclass
class GenerateResult:
    """Output of a TTS synthesis request."""

    audio_bytes: bytes
    sample_rate: int
    duration_seconds: float
    format: str = "wav"  # wav | mp3 | ogg


class TTSModelBase(ABC):
    """Base class for all TTS model implementations.

    Class attributes (set on each subclass, not instance):
        model_id:               unique slug, e.g. "vibevoice"
        model_name:             human-readable name
        description:            one-line description
        supports_voice_cloning: whether clone_voice() is implemented
        supports_streaming:     whether streaming generation is supported
        supported_languages:    list of BCP-47 codes
        hf_repo:                HuggingFace repo ID for download info
        vram_gb_estimate:       approximate VRAM usage when loaded
    """

    model_id: str = ""
    model_name: str = ""
    description: str = ""
    supports_voice_cloning: bool = False
    supports_streaming: bool = False
    supports_speed: bool = False  # True = speed param is actively used
    supports_pitch: bool = False  # True = pitch param is actively used
    supports_dialogue: bool = False  # True = multi-speaker [S1]/[S2] or Speaker 0:/1:
    dialogue_format: str = ""  # "dia" | "vibevoice" — model-specific syntax
    help_text: str = ""  # Selection guidance: speed, quality, use cases
    supported_languages: list[str] = ["en"]
    hf_repo: str = ""
    vram_gb_estimate: float = 4.0
    standby: bool = False  # True = keep loaded between requests

    _loaded: bool = False

    @abstractmethod
    def load(self, device: str = "cuda") -> None:
        """Load model weights to the specified device."""

    @abstractmethod
    def unload(self) -> None:
        """Unload model from GPU and free memory."""

    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult:
        """Synthesize speech for the given request.

        Must be called only while the model is loaded.
        """

    def stream_generate(self, request: GenerateRequest):
        """Yield raw PCM16 audio bytes as they are generated.

        Only available when supports_streaming is True.
        Each yielded value is a bytes object containing 16-bit signed PCM samples
        at the model's native sample rate (24000 Hz).
        """
        raise NotImplementedError(f"{self.model_id} does not support streaming generation")

    def clone_voice(self, audio_path: str, name: str = "") -> dict:  # noqa: ARG002
        """Create a voice profile from reference audio.

        Returns a dict of model-specific metadata to be stored alongside
        the voice profile. Override in subclasses that support cloning.
        """
        raise NotImplementedError(f"{self.model_id} does not support voice cloning")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get_info(self) -> dict:
        """Return a JSON-serialisable dict of model metadata."""
        return {
            "id": self.model_id,
            "name": self.model_name,
            "description": self.description,
            "supports_voice_cloning": self.supports_voice_cloning,
            "supports_streaming": self.supports_streaming,
            "supports_speed": self.supports_speed,
            "supports_pitch": self.supports_pitch,
            "supports_dialogue": self.supports_dialogue,
            "dialogue_format": self.dialogue_format,
            "help_text": self.help_text,
            "supported_languages": self.supported_languages,
            "hf_repo": self.hf_repo,
            "vram_gb_estimate": self.vram_gb_estimate,
            "is_loaded": self.is_loaded,
            "standby": self.standby,
        }
