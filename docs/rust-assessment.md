# Where Rust fits

Rust is a useful candidate for the processing worker's frame buffers and job supervision. A full rewrite would add build and packaging complexity without a measured benefit for the lightweight NAS manager or web interface. No Rust component is shipped or performance improvement claimed in this iteration.

## Current boundaries

| Component | Current work | Recommendation |
|---|---|---|
| Web interface | React and official Astryx components | Keep the existing browser stack; Rust would not simplify this screen |
| NAS manager | FastAPI, SQLite, authenticated streaming and separate output publication | Keep it until profiling identifies a problem; it does not upscale pictures |
| Processing supervisor | Python asynchronous heartbeats, storage checks, child-process termination and recovery | Candidate for a small Rust service if concurrency or recovery requirements grow |
| Frame handling | PyAV/NumPy buffers, motion estimation, a bounded NUT pipe to FFmpeg | Best initial Rust candidate: own bounded reusable buffers and reduce measured conversion/copy costs |
| NVIDIA integration | Independent C++ CUDA/Vulkan bridges plus proprietary NVIDIA runtimes | Keep a narrow native boundary; a Rust wrapper can manage ownership, but cannot make the SDK memory-safe |

`popcorn_sr/video_pipe.py` already streams frames through an OS pipe and bounds retained encoder errors. `popcorn_sr/dlss_sr.py` checks pixel/motion shapes and types, owns one session, reuses allocated arrays and calls the bridge through `ctypes`. `native/dlss_sr.cpp` and `native/dlssg.cpp` contain GPU resource/session work. These facts narrow the opportunity: benchmark buffer conversion, motion estimation and transfer before choosing a rewrite. Encoding and NVIDIA inference already execute outside ordinary Python bytecode.

Rust's safe ownership model can prevent invalid buffer lifetimes in Rust-managed code. Foreign functions and raw pointers still require a small, audited unsafe boundary. A wrapper cannot establish safety for incorrectly sized buffers or faulty foreign code by itself. See the [Rust book](https://doc.rust-lang.org/book/ch20-01-unsafe-rust.html) and [official FFI guide](https://doc.rust-lang.org/nomicon/ffi.html).

## Adoption gate

Start with one worker-only component, preserve the HTTP and recipe contracts, and benchmark the same source/settings on the same hardware. Record elapsed time, peak resident memory, scratch bytes and output timing/media preservation. Require buffer-length checks at the native boundary, bounded queues, deterministic cancellation and cleanup, and regression tests for invalid input, source changes and native errors. Repeat physical NVIDIA acceptance before replacing the current path. Rust alone will not fix whole-video intermediate storage or supply an unavailable NVIDIA SDK.

## Measured NAS boundary

A generated two-second 3840×2160 H.264 return exposed a memory failure in the manager's external FFmpeg playback check. On Spark with 20 visible CPUs, a 0.5 CPU quota and a 512 MiB container limit, automatic decoder threading caused one memory kill and rejected the valid return. Bounding decoder threads to two reduced the actual manager's peak to about 167 MiB and accepted the same clip, with its original and downloaded bytes preserved. This was verified against committed package `3f66291031108c9fff6187a7eaaa405be27f9487`.

The measured correction was thread/buffer control in an existing native program. It supports keeping the lightweight manager stack while profiling the worker's buffer ownership and conversion costs before introducing Rust. These numbers describe validation of that generated clip; inference throughput and perceptual quality need their own measurements.
