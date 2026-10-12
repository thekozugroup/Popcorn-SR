# Third-party notices

Popcorn SR source is AGPL-3.0-or-later unless a file states otherwise.

## BasicSR network architecture

`popcorn_sr/rrdbnet.py` adapts `basicsr/archs/rrdbnet_arch.py` from [BasicSR](https://github.com/XPixelGroup/BasicSR). Copyright 2018-2022 BasicSR Authors. Licensed under Apache License 2.0, included in `licenses/BasicSR-Apache-2.0.txt`. Changes remove registry/training initialization and use standard PyTorch layer composition. Checkpoint compatibility is retained; no pretrained weights are embedded.

## Real-ESRGAN

The optional official RealESRGAN_x4plus checkpoint is downloaded from [Real-ESRGAN v0.1.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.1.0) only when the operator runs `scripts/fetch-model.py`. Copyright (c) 2021, Xintao Wang. BSD-3-Clause terms are included in `licenses/Real-ESRGAN-BSD-3-Clause.txt`. Model SHA-256: `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`.

## NVIDIA runtimes

NVIDIA VFX/RTX Video, DLSS, PyTorch NGC images, CUDA and NVENC APIs retain NVIDIA's licenses. Popcorn SR does not bundle their proprietary models/DLLs/shared libraries in its source or default image. `Dockerfile.ai` uses the operator-selected NVIDIA container base, subject to that image's own terms. Operators install VFX separately and must review the applicable SDK terms before redistribution.

## Reference projects

[glarsson/fast-rtxvsr](https://github.com/glarsson/fast-rtxvsr) is an MIT CLI wrapper; no implementation was copied. [Merserk/Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) has source-available proprietary licensing. No source or binaries were copied. The optional Windows adapter invokes an operator-installed CLI. A reference does not grant redistribution rights.

## FFmpeg and package dependencies

FFmpeg is installed from the base distribution's packages, under those build-specific LGPL/GPL terms. Image package-manager metadata and source repositories identify the corresponding source. Python/JS dependencies retain their own licenses; lockfiles list the exact versions. The default UI ships compiled Tailwind CSS only; browser testing packages do not ship in the runtime image.

## Web interface

Astryx Core, Neutral theme and CLI 0.6.8 are MIT-licensed, copyright Meta Platforms, Inc. and affiliates. React/React DOM 19 are MIT-licensed, copyright Meta Platforms, Inc. and affiliates. StyleX is MIT-licensed; Lucide icons are ISC-licensed. Their licenses remain with the bundled dependencies; see `licenses/astryx-MIT.txt`, `licenses/react-MIT.txt`, `licenses/stylex-MIT.txt` and `licenses/lucide-ISC.txt`. Tailwind CSS and Vite retain their MIT licenses.
