"""morphfilm — CPU morph-film engine for the SiteQuiVend portfolio.

The engine turns photographic plates into a finished vertical commercial:

``imageops``  loading, cinema grade, grain, bloom, halation, vignette
``camera``    overscanned plate, sub-pixel camera move, parallax, focus drift
``anchors``   native measurements projected through the exact camera inverse
``features``  circle / ellipse detection scored by median gradient
``morph``     spin, zoom, portal, bloom, flow and radial transitions
``atmos``     steam, dust, flares, travelling specular sweeps
``score``     original music and sound design, synthesised from scratch
``film``      timeline, per-frame render, end card, mux, QC helpers
``films``     the two edits: shots, moves, morph parameters, prompts
``derive``    deterministic plate derivations

Everything runs on CPU with numpy/OpenCV; ffmpeg is the only external binary.
"""
