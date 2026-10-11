"""Oscuramento di volti e targhe prima di salvare qualsiasi immagine.

Regola: FAIL-CLOSED. Se l'oscuramento non è disponibile o fallisce, si restituisce
None e il chiamante salva SOLO i metadati, mai l'immagine.
"""


def redact(jpeg: bytes) -> bytes | None:
    # TODO (R2): YuNet per i volti (OpenCV Zoo, MIT) + yolo-v9-t-384-license-plate
    # (open-image-models, MIT); riempimento pieno dei riquadri allargati del 20%;
    # scartare l'immagine se una persona occupa >15% del ritaglio.
    return None
