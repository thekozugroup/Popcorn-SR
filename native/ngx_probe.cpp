// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// Popcorn SR capability diagnostic. Build against a separately installed NVIDIA SDK.
// This reports initialization only; it never advertises a working video engine.
#include <cstddef>
#include <cstdio>
#include <cwchar>
#include <clocale>
#include <dlfcn.h>
#include <string>
#include "nvsdk_ngx_params.h"

static void log_sink(const char*, NVSDK_NGX_Logging_Level, NVSDK_NGX_Feature) {}

template <typename T> T function(void* library, const char* name) {
    return reinterpret_cast<T>(dlsym(library, name));
}

#ifdef POPCORN_CUDA_SMOKE
#include "cuda_smoke.hpp"
#endif

int main(int argc, char** argv) {
    std::setlocale(LC_ALL, "");
    if (argc != 3 && (argc != 4 || std::string(argv[3]) != "--render")) {
        std::fprintf(stderr, "Usage: ngx-probe SDK-library-folder scratch-folder [--render]\n");
        return 2;
    }
    void* cuda = dlopen("libcuda.so.1", RTLD_NOW | RTLD_LOCAL);
    void* ngx = dlopen("libnvidia-ngx.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!cuda || !ngx) {
        std::puts("{\"error\":\"NVIDIA driver libraries unavailable\",\"video_render_verified\":false}");
        return 1;
    }
    auto cuda_init = function<int (*)(unsigned int)>(cuda, "cuInit");
    auto retain = function<int (*)(void**, int)>(cuda, "cuDevicePrimaryCtxRetain");
    auto set_context = function<int (*)(void*)>(cuda, "cuCtxSetCurrent");
    auto release = function<int (*)(int)>(cuda, "cuDevicePrimaryCtxRelease");
    using Init = NVSDK_NGX_Result (*)(const char*, NVSDK_NGX_EngineType, const char*, const wchar_t*, NVSDK_NGX_Version, const NVSDK_NGX_FeatureCommonInfo*);
    auto init = function<Init>(ngx, "NVSDK_NGX_CUDA_Init_ProjectID");
    auto caps = function<NVSDK_NGX_Result (*)(NVSDK_NGX_Parameter**)>(ngx, "NVSDK_NGX_CUDA_GetCapabilityParameters");
    auto destroy = function<NVSDK_NGX_Result (*)(NVSDK_NGX_Parameter*)>(ngx, "NVSDK_NGX_CUDA_DestroyParameters");
    auto shutdown = function<NVSDK_NGX_Result (*)()>(ngx, "NVSDK_NGX_CUDA_Shutdown");
    auto allocate = function<NVSDK_NGX_Result (*)(NVSDK_NGX_Parameter**)>(ngx, "NVSDK_NGX_CUDA_AllocateParameters");
    auto create = function<NVSDK_NGX_Result (*)(NVSDK_NGX_Feature, const NVSDK_NGX_Parameter*, NVSDK_NGX_Handle**)>(ngx, "NVSDK_NGX_CUDA_CreateFeature");
    auto release_feature = function<NVSDK_NGX_Result (*)(NVSDK_NGX_Handle*)>(ngx, "NVSDK_NGX_CUDA_ReleaseFeature");
    if (!cuda_init || !retain || !set_context || !release || !init || !caps || !destroy || !shutdown) {
        std::puts("{\"error\":\"Required NVIDIA API unavailable\",\"video_render_verified\":false}");
        return 1;
    }
    void* context = nullptr;
    int cu_result = cuda_init(0);
    if (cu_result == 0) cu_result = retain(&context, 0);
    if (cu_result == 0) cu_result = set_context(context);
    if (cu_result != 0) {
        std::printf("{\"cuda_result\":%d,\"video_render_verified\":false}\n", cu_result);
        if (context) release(0);
        return 1;
    }
    // Paths are operator supplied. UTF-8 conversion respects the process locale.
    std::wstring paths[2];
    for (int i = 0; i < 2; ++i) {
        const char* input = argv[i + 1];
        std::mbstate_t state{};
        std::size_t length = std::mbsrtowcs(nullptr, &input, 0, &state);
        if (length == static_cast<std::size_t>(-1)) { release(0); return 2; }
        paths[i].resize(length + 1);
        input = argv[i + 1];
        state = {};
        std::mbsrtowcs(paths[i].data(), &input, length + 1, &state);
    }
    const wchar_t* sdk_path = paths[0].c_str();
    NVSDK_NGX_FeatureCommonInfo info{};
    info.PathListInfo = {&sdk_path, 1};
    info.LoggingInfo = {log_sink, NVSDK_NGX_LOGGING_LEVEL_OFF, true};
    NVSDK_NGX_Result initialized = init("fb597f3f-5797-44d5-a4e6-59b757758233", NVSDK_NGX_ENGINE_TYPE_CUSTOM, "PopcornSR", paths[1].c_str(), NVSDK_NGX_Version_API, &info);
    std::printf("{\"api\":\"CUDA\",\"init_result\":\"0x%08x\",\"video_render_verified\":false", static_cast<unsigned int>(initialized));
    if (initialized == NVSDK_NGX_Result_Success) {
        NVSDK_NGX_Parameter* parameters = nullptr;
        NVSDK_NGX_Result result = caps(&parameters);
        std::printf(",\"capability_result\":\"0x%08x\",\"parameters\":{", static_cast<unsigned int>(result));
        const char* names[] = {"SuperSampling.Available", "SuperSampling.FeatureInitResult", "SuperSampling.NeedsUpdatedDriver", "SuperSampling.MinDriverVersionMajor", "SuperSampling.MinDriverVersionMinor", "VideoSuperResolution.Available", "VideoSuperResolution.FeatureInitResult", "FrameGeneration.Available", "FrameGeneration.FeatureInitResult", "FrameInterpolation.FeatureInitResult"};
        if (result == NVSDK_NGX_Result_Success && parameters) {
            bool first = true;
            for (const char* name : names) {
                int value = 0;
                NVSDK_NGX_Result got = parameters->Get(name, &value);
                std::printf("%s\"%s\":{\"query_result\":\"0x%08x\",\"value\":%d}", first ? "" : ",", name, static_cast<unsigned int>(got), value);
                first = false;
            }
            destroy(parameters);
        }
        std::printf("}");
        if (allocate && create && release_feature) {
            NVSDK_NGX_Parameter* creation = nullptr;
            if (allocate(&creation) == NVSDK_NGX_Result_Success && creation) {
                creation->Set(NVSDK_NGX_Parameter_Width, 128u);
                creation->Set(NVSDK_NGX_Parameter_Height, 96u);
                creation->Set(NVSDK_NGX_Parameter_OutWidth, 256u);
                creation->Set(NVSDK_NGX_Parameter_OutHeight, 192u);
                creation->Set(NVSDK_NGX_Parameter_PerfQualityValue, static_cast<int>(NVSDK_NGX_PerfQuality_Value_MaxPerf));
                creation->Set(NVSDK_NGX_Parameter_DLSS_Feature_Create_Flags, static_cast<int>(NVSDK_NGX_DLSS_Feature_Flags_AutoExposure | NVSDK_NGX_DLSS_Feature_Flags_MVLowRes));
                NVSDK_NGX_Handle* handle = nullptr;
                NVSDK_NGX_Result made = create(NVSDK_NGX_Feature_SuperSampling, creation, &handle);
                std::printf(",\"sr_create_result\":\"0x%08x\"", static_cast<unsigned int>(made));
                if (made == NVSDK_NGX_Result_Success && handle) {
#ifdef POPCORN_CUDA_SMOKE
                    if (argc == 4) render_smoke(cuda, ngx, handle, creation);
#else
                    if (argc == 4) std::printf(",\"render_error\":\"Rebuild with POPCORN_CUDA_SMOKE and CUDA headers\"");
#endif
                    release_feature(handle);
                }
                destroy(creation);
            }
        }
        shutdown();
    }
    std::puts("}");
    release(0);
    dlclose(ngx);
    dlclose(cuda);
    return initialized == NVSDK_NGX_Result_Success ? 0 : 1;
}
