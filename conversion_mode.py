"""Opaque-preservation mode enum for Judgment native port.

For structures where endian semantics are not yet understood, the converter
must explicitly classify handling rather than silently heuristic-falling back to
empty or mis-swapped bytes.

Modes:
  KNOWN                - field-wise convert (tagged or binary with known layout)
  OPAQUE_ENDIAN_NEUTRAL- byte-oriented payload where endian is proven neutral (no swap needed)
  OPAQUE_PRESERVE_UNVERIFIED - extent is structurally identifiable and preserved byte-for-byte,
                               but endianness is UNKNOWN (may contain DWORDs, floats, indices);
                               copy experimentally, semantic qualification required
  OPAQUE_ENDIAN_SENSITIVE - known endian-sensitive without conversion model; fail closed
  TRANSIENT            - deliberately omitted with documented justification;
                         only allowed after runtime evidence shows omission does not
                         affect gameplay (cover acquisition, mantle, AI, etc.)

Example for CoverSlot:
  known prefix (owner, cover types, vectors, actions, firelinks, etc.) -> KNOWN
  unknown residual (high-entropy ~168-184B, extent proven via next-slot pattern) ->
      OPAQUE_PRESERVE_UNVERIFIED (endianness=UNKNOWN, policy=PRESERVE).
  Copying it preserves package-level invariants (exact landing q==end) but does NOT
  prove the blob is endian-neutral — it may contain DWORDs/floats/indices. The 16/16
  exact landing proves the boundary, not the encoding.

  OPAQUE_ENDIAN_NEUTRAL -> known safe to copy
  OPAQUE_ENDIAN_SENSITIVE -> known unsafe without conversion
  OPAQUE_PRESERVE_UNVERIFIED -> copy experimentally, qualification required
"""
from enum import Enum, auto

class ConversionMode(Enum):
    KNOWN = auto()
    OPAQUE_ENDIAN_NEUTRAL = auto()
    OPAQUE_PRESERVE_UNVERIFIED = auto()  # endianness=UNKNOWN, policy=PRESERVE
    OPAQUE_ENDIAN_SENSITIVE = auto()
    TRANSIENT = auto()

# Per-field classification for CoverSlot.  Known fields are those proven against
# SP_00_Museum_Base_Exit_S and described in coverslot_expand.py header.
COVER_SLOT_KNOWN = {
    "SlotOwner", "ForceCoverType", "CoverType", "LocationDescription",
    "LocationOffset", "RotationOffset", "Actions", "FireLinks",
    "ExposedCoverPackedProperties", "TurnTargetPackedProperties",
    "SlipRefs", "OverlapClaimsList",
    "bLeanLeft", "bLeanRight", "bForceCanPopUp", "bCanPopUp", "bCanMantle",
    "bCanClimbUp", "bForceCanCoverSlip_Left", "bForceCanCoverSlip_Right",
    "bCanCoverSlip_Left", "bCanCoverSlip_Right", "bCanSwatTurn_Left",
    "bCanSwatTurn_Right", "bEnabled", "bAllowPopup", "bAllowMantle",
    "bAllowCoverSlip", "bAllowClimbUp", "bAllowSwatTurn", "bForceNoGroundAdjust",
    "bPlayerOnly", "bPreferLeanOverPopup",
}

# Residual classification - extent proven (16/16 landing), encoding not proven.
# Was incorrectly labelled OPAQUE_ENDIAN_NEUTRAL; corrected to UNVERIFIED.
COVER_SLOT_RESIDUAL_MODE = ConversionMode.OPAQUE_PRESERVE_UNVERIFIED

def classify_cover_slot_residual():
    return COVER_SLOT_RESIDUAL_MODE
