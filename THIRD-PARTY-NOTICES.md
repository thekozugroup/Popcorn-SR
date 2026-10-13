# Third-party notices

Popcorn SR source is AGPL-3.0-or-later unless a file states otherwise.

## BasicSR network architecture

`popcorn_sr/rrdbnet.py` adapts `basicsr/archs/rrdbnet_arch.py` from [BasicSR](https://github.com/XPixelGroup/BasicSR). Copyright 2018-2022 BasicSR Authors. Licensed under Apache License 2.0, included in `licenses/BasicSR-Apache-2.0.txt`. Changes remove registry/training initialization and use standard PyTorch layer composition. Checkpoint compatibility is retained; no pretrained weights are embedded.

## Real-ESRGAN

The optional official RealESRGAN_x4plus checkpoint is downloaded from [Real-ESRGAN v0.1.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.1.0) only when the operator runs `scripts/fetch-model.py`. Copyright (c) 2021, Xintao Wang. BSD-3-Clause terms are included in `licenses/Real-ESRGAN-BSD-3-Clause.txt`. Model SHA-256: `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`.

## NVIDIA runtimes

NVIDIA VFX/RTX Video, DLSS, PyTorch NGC images, CUDA and NVENC APIs retain NVIDIA's licenses. Popcorn SR does not bundle their proprietary models/DLLs/shared libraries in its source or default image. `Dockerfile.ai` installs pinned CUDA PyTorch wheels and their dependencies, which retain their respective terms. Operators install VFX separately and must review the applicable SDK terms before redistribution.

## NVIDIA VFX Python API examples

The optional VSR and TrueHDR adapters follow the public Python API contract in [NVIDIA VFX Python Samples](https://github.com/NVIDIA-Maxine/nvidia-vfx-python-samples/tree/65faa030c1469dceb3c7b1781a01258ea4223647), copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. MIT attribution is included in `licenses/NVIDIA-VFX-Samples-MIT.txt`. Popcorn SR provides its own timestamped system-FFmpeg pipeline and precision validation. No NVIDIA runtime, models or sample media are included.

## Reference projects

[glarsson/fast-rtxvsr](https://github.com/glarsson/fast-rtxvsr) is an MIT CLI wrapper; no implementation was copied. [Merserk/Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) has source-available proprietary licensing. No source or binaries were copied. The optional Windows adapter invokes an operator-installed CLI. A reference does not grant redistribution rights.

## FFmpeg and package dependencies

FFmpeg is installed from the base distribution's packages, under those build-specific LGPL/GPL terms. Image package-manager metadata and source repositories identify the corresponding source. Python/JS dependencies retain their own licenses; lockfiles list the exact versions. The default UI ships compiled Tailwind CSS only; browser testing packages do not ship in the runtime image.

## Web interface

Astryx Core, Neutral theme and CLI 0.6.8 are MIT-licensed, copyright Meta Platforms, Inc. and affiliates. React/React DOM 19 are MIT-licensed, copyright Meta Platforms, Inc. and affiliates. StyleX is MIT-licensed; Lucide icons are ISC-licensed. Their licenses remain with the bundled dependencies; see `licenses/astryx-MIT.txt`, `licenses/react-MIT.txt`, `licenses/stylex-MIT.txt` and `licenses/lucide-ISC.txt`. Tailwind CSS and Vite retain their MIT licenses.

## Independent native adapters and diagnostics

The C++ sources and resource helpers under `native/` are independently written Popcorn SR source under `native/LICENSE` (MIT). They build against operator-provisioned NVIDIA SDK headers/wrappers and use separately installed drivers/runtimes. The NVIDIA SDK is not relicensed or included in the public source or default image. The optional Vulkan build check downloads pinned NVIDIA and Khronos headers into a temporary directory and removes them after compilation. The NGX image installs the distribution's Vulkan loader package, with its upstream terms and source identified by the package metadata.

## Popcorn family mark

The three-circle mark in `web/main.jsx` and `web/public/popcorn-sr.svg` adapts [Popcorn Batch's icon](https://github.com/thekozugroup/Popcorn-Batch/blob/54170f2684f734712b6159ccc7592f3237fa6b71/web/src/app/icon.svg), from the same Kozu Group family. Popcorn Batch source is Apache-2.0; its license is included in `licenses/Popcorn-Batch-Apache-2.0.txt`. SR changes the highlighted circle from top to lower-right and its color from blue-500 to teal-500, and applies the SR name and theme colors.
