// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// Independent CUDA/NGX video bridge. Build with operator-provided SDK headers.
#include <cuda.h>
#include "nvsdk_ngx_params.h"
#include <dlfcn.h>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include <codecvt>
#include <locale>

namespace {
thread_local std::string last_error;
std::mutex ownership;
bool occupied = false;
bool initialized_once = false;
void log_sink(const char*, NVSDK_NGX_Logging_Level, NVSDK_NGX_Feature) {}

template <typename T> T symbol(void* library, const char* name) {
    auto address = dlsym(library, name);
    if (!address) throw std::runtime_error(std::string("Missing NVIDIA API: ") + name);
    return reinterpret_cast<T>(address);
}
void cuda_ok(CUresult code, const char* operation) {
    if (code != CUDA_SUCCESS) throw std::runtime_error(std::string(operation) + " failed (CUDA " + std::to_string(code) + ")");
}
void ngx_ok(NVSDK_NGX_Result code, const char* operation) {
    if (code != NVSDK_NGX_Result_Success) throw std::runtime_error(std::string(operation) + " failed (NGX " + std::to_string(static_cast<uint32_t>(code)) + ")");
}
struct Session {
    void *cuda{}, *ngx{};
    CUcontext context{};
    bool initialized{};
    NVSDK_NGX_Parameter* parameters{};
    NVSDK_NGX_Handle* feature{};
    CUarray arrays[4]{};
    CUtexObject textures[4]{};
    CUsurfObject surface{};
    unsigned width{}, height{}, out_width{}, out_height{};
    decltype(&cuCtxSetCurrent) set_context{};
    decltype(&cuDevicePrimaryCtxRelease) release_context{};
    decltype(&cuArrayDestroy) array_destroy{};
    decltype(&cuTexObjectDestroy) texture_destroy{};
    decltype(&cuSurfObjectDestroy) surface_destroy{};
    decltype(&cuMemcpy2D) copy{};
    decltype(&cuCtxSynchronize) synchronize{};
    NVSDK_NGX_Result (*destroy_parameters)(NVSDK_NGX_Parameter*){};
    NVSDK_NGX_Result (*release_feature)(NVSDK_NGX_Handle*){};
    NVSDK_NGX_Result (*shutdown)(){};
    NVSDK_NGX_Result (*evaluate)(const NVSDK_NGX_Handle*, const NVSDK_NGX_Parameter*, void*){};

    void clear_feature() {
        if (context && set_context) set_context(context);
        if (feature && release_feature) release_feature(feature);
        if (parameters && destroy_parameters) destroy_parameters(parameters);
        if (surface && surface_destroy) surface_destroy(surface);
        feature = nullptr; parameters = nullptr; surface = 0;
        for (int i = 0; i < 4; ++i) {
            if (textures[i] && texture_destroy) texture_destroy(textures[i]);
            if (arrays[i] && array_destroy) array_destroy(arrays[i]);
            textures[i] = 0; arrays[i] = nullptr;
        }
    }
    ~Session() {
        clear_feature();
        if (initialized && shutdown) shutdown();
        if (context && release_context) release_context(0);
        if (ngx) dlclose(ngx);
        if (cuda) dlclose(cuda);
    }

    void upload(int index, const float* values, unsigned channels) {
        CUDA_MEMCPY2D transfer{};
        transfer.srcMemoryType = CU_MEMORYTYPE_HOST;
        transfer.srcHost = values;
        transfer.srcPitch = width * channels * sizeof(float);
        transfer.dstMemoryType = CU_MEMORYTYPE_ARRAY;
        transfer.dstArray = arrays[index];
        transfer.WidthInBytes = transfer.srcPitch;
        transfer.Height = height;
        cuda_ok(copy(&transfer), "Frame upload");
    }
};
}

extern "C" {
// ABI 1: interleaved float RGBA input/output; pixel-unit current-to-previous XY motion.
unsigned popcorn_dlss_abi_version() { return 1; }
const char* popcorn_dlss_error() { return last_error.c_str(); }

void* popcorn_dlss_create(unsigned width, unsigned height, unsigned out_width, unsigned out_height,
                          int mode, unsigned preset, const char* runtime_path, const char* scratch_path) {
    std::lock_guard<std::mutex> lock(ownership);
    last_error.clear();
    try {
        if (occupied || initialized_once) throw std::runtime_error("Start a new process for another DLSS session; NGX cannot safely reinitialize here");
        if (!width || !height || width > 8192 || height > 8192 || out_width < width || out_height < height ||
            out_width > 8192 || out_height > 8192 || !runtime_path || !scratch_path ||
            (mode != 0 && mode != 1 && mode != 2 && mode != 3 && mode != 5) ||
            (preset != 0 && preset != 10 && preset != 11 && preset != 12 && preset != 13))
            throw std::runtime_error("Invalid DLSS configuration");
        auto session = std::make_unique<Session>();
        auto& s = *session;
        s.width = width; s.height = height; s.out_width = out_width; s.out_height = out_height;
        s.cuda = dlopen("libcuda.so.1", RTLD_NOW | RTLD_LOCAL);
        s.ngx = dlopen("libnvidia-ngx.so.1", RTLD_NOW | RTLD_LOCAL);
        if (!s.cuda || !s.ngx) throw std::runtime_error("NVIDIA CUDA/NGX driver libraries unavailable");
        auto init_cuda = symbol<decltype(&cuInit)>(s.cuda, "cuInit");
        auto retain = symbol<decltype(&cuDevicePrimaryCtxRetain)>(s.cuda, "cuDevicePrimaryCtxRetain");
        s.set_context = symbol<decltype(s.set_context)>(s.cuda, "cuCtxSetCurrent");
        s.release_context = symbol<decltype(s.release_context)>(s.cuda, "cuDevicePrimaryCtxRelease");
        s.array_destroy = symbol<decltype(s.array_destroy)>(s.cuda, "cuArrayDestroy");
        s.texture_destroy = symbol<decltype(s.texture_destroy)>(s.cuda, "cuTexObjectDestroy");
        s.surface_destroy = symbol<decltype(s.surface_destroy)>(s.cuda, "cuSurfObjectDestroy");
        s.copy = symbol<decltype(s.copy)>(s.cuda, "cuMemcpy2D_v2");
        s.synchronize = symbol<decltype(s.synchronize)>(s.cuda, "cuCtxSynchronize");
        s.destroy_parameters = symbol<decltype(s.destroy_parameters)>(s.ngx, "NVSDK_NGX_CUDA_DestroyParameters");
        s.release_feature = symbol<decltype(s.release_feature)>(s.ngx, "NVSDK_NGX_CUDA_ReleaseFeature");
        s.shutdown = symbol<decltype(s.shutdown)>(s.ngx, "NVSDK_NGX_CUDA_Shutdown");
        s.evaluate = symbol<decltype(s.evaluate)>(s.ngx, "NVSDK_NGX_CUDA_EvaluateFeature");
        cuda_ok(init_cuda(0), "CUDA initialization");
        cuda_ok(retain(&s.context, 0), "CUDA context allocation");
        cuda_ok(s.set_context(s.context), "CUDA context selection");
        using Init = NVSDK_NGX_Result (*)(const char*, NVSDK_NGX_EngineType, const char*, const wchar_t*, NVSDK_NGX_Version, const NVSDK_NGX_FeatureCommonInfo*);
        auto init = symbol<Init>(s.ngx, "NVSDK_NGX_CUDA_Init_ProjectID");
        std::wstring_convert<std::codecvt_utf8<wchar_t>> converter;
        const auto runtime = converter.from_bytes(runtime_path);
        const auto scratch = converter.from_bytes(scratch_path);
        const wchar_t* runtime_pointer = runtime.c_str();
        NVSDK_NGX_FeatureCommonInfo info{};
        info.PathListInfo = {&runtime_pointer, 1};
        info.LoggingInfo = {log_sink, NVSDK_NGX_LOGGING_LEVEL_OFF, true};
        ngx_ok(init("fb597f3f-5797-44d5-a4e6-59b757758233", NVSDK_NGX_ENGINE_TYPE_CUSTOM, "PopcornSR",
                    scratch.c_str(), NVSDK_NGX_Version_API, &info), "NGX initialization");
        s.initialized = true;
        initialized_once = true;
        auto allocate = symbol<NVSDK_NGX_Result (*)(NVSDK_NGX_Parameter**)>(s.ngx, "NVSDK_NGX_CUDA_AllocateParameters");
        ngx_ok(allocate(&s.parameters), "NGX parameter allocation");
        s.parameters->Set(NVSDK_NGX_Parameter_Width, width);
        s.parameters->Set(NVSDK_NGX_Parameter_Height, height);
        s.parameters->Set(NVSDK_NGX_Parameter_OutWidth, out_width);
        s.parameters->Set(NVSDK_NGX_Parameter_OutHeight, out_height);
        s.parameters->Set(NVSDK_NGX_Parameter_PerfQualityValue, mode);
        s.parameters->Set(NVSDK_NGX_Parameter_DLSS_Feature_Create_Flags,
                          int(NVSDK_NGX_DLSS_Feature_Flags_AutoExposure | NVSDK_NGX_DLSS_Feature_Flags_MVLowRes));
        for (const char* key : {NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_DLAA,
                               NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_Quality,
                               NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_Balanced,
                               NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_Performance,
                               NVSDK_NGX_Parameter_DLSS_Hint_Render_Preset_UltraPerformance}) s.parameters->Set(key, preset);
        auto create = symbol<NVSDK_NGX_Result (*)(NVSDK_NGX_Feature, const NVSDK_NGX_Parameter*, NVSDK_NGX_Handle**)>(s.ngx, "NVSDK_NGX_CUDA_CreateFeature");
        ngx_ok(create(NVSDK_NGX_Feature_SuperSampling, s.parameters, &s.feature), "DLSS feature creation");
        auto array_create = symbol<decltype(&cuArray3DCreate)>(s.cuda, "cuArray3DCreate_v2");
        auto texture_create = symbol<decltype(&cuTexObjectCreate)>(s.cuda, "cuTexObjectCreate");
        auto surface_create = symbol<decltype(&cuSurfObjectCreate)>(s.cuda, "cuSurfObjectCreate");
        unsigned channels[] = {4, 4, 1, 2};
        for (int i = 0; i < 4; ++i) {
            CUDA_ARRAY3D_DESCRIPTOR description{};
            description.Width = i == 1 ? out_width : width;
            description.Height = i == 1 ? out_height : height;
            description.Format = CU_AD_FORMAT_FLOAT;
            description.NumChannels = channels[i];
            description.Flags = CUDA_ARRAY3D_SURFACE_LDST;
            cuda_ok(array_create(&s.arrays[i], &description), "CUDA array allocation");
            CUDA_RESOURCE_DESC resource{};
            resource.resType = CU_RESOURCE_TYPE_ARRAY;
            resource.res.array.hArray = s.arrays[i];
            if (i == 1) { cuda_ok(surface_create(&s.surface, &resource), "CUDA surface allocation"); continue; }
            CUDA_TEXTURE_DESC texture{};
            texture.addressMode[0] = texture.addressMode[1] = CU_TR_ADDRESS_MODE_CLAMP;
            texture.filterMode = CU_TR_FILTER_MODE_POINT;
            cuda_ok(texture_create(&s.textures[i], &resource, &texture, nullptr), "CUDA texture allocation");
        }
        // Captured video has no game-engine depth. This experimental path uses flat depth.
        std::vector<float> depth(static_cast<size_t>(width) * height, 0.5f);
        s.upload(2, depth.data(), 1);
        s.parameters->Set(NVSDK_NGX_Parameter_Color, static_cast<void*>(&s.textures[0]));
        s.parameters->Set(NVSDK_NGX_Parameter_Output, static_cast<void*>(&s.surface));
        s.parameters->Set(NVSDK_NGX_Parameter_Depth, static_cast<void*>(&s.textures[2]));
        s.parameters->Set(NVSDK_NGX_Parameter_MotionVectors, static_cast<void*>(&s.textures[3]));
        s.parameters->Set(NVSDK_NGX_Parameter_Jitter_Offset_X, 0.0f);
        s.parameters->Set(NVSDK_NGX_Parameter_Jitter_Offset_Y, 0.0f);
        s.parameters->Set(NVSDK_NGX_Parameter_MV_Scale_X, 1.0f);
        s.parameters->Set(NVSDK_NGX_Parameter_MV_Scale_Y, 1.0f);
        s.parameters->Set(NVSDK_NGX_Parameter_DLSS_Render_Subrect_Dimensions_Width, width);
        s.parameters->Set(NVSDK_NGX_Parameter_DLSS_Render_Subrect_Dimensions_Height, height);
        s.parameters->Set(NVSDK_NGX_Parameter_DLSS_Pre_Exposure, 1.0f);
        s.parameters->Set(NVSDK_NGX_Parameter_DLSS_Exposure_Scale, 1.0f);
        occupied = true;
        return session.release();
    } catch (const std::exception& error) { last_error = error.what(); return nullptr; }
}

int popcorn_dlss_process(void* handle, const float* rgba, const float* motion, float* output, int reset) {
    last_error.clear();
    try {
        if (!handle || !rgba || !motion || !output) throw std::runtime_error("Missing DLSS frame buffer");
        auto& s = *static_cast<Session*>(handle);
        cuda_ok(s.set_context(s.context), "CUDA context selection");
        s.upload(0, rgba, 4);
        s.upload(3, motion, 2);
        s.parameters->Set(NVSDK_NGX_Parameter_Reset, reset ? 1 : 0);
        ngx_ok(s.evaluate(s.feature, s.parameters, nullptr), "DLSS frame evaluation");
        cuda_ok(s.synchronize(), "DLSS synchronization");
        CUDA_MEMCPY2D transfer{};
        transfer.srcMemoryType = CU_MEMORYTYPE_ARRAY;
        transfer.srcArray = s.arrays[1];
        transfer.dstMemoryType = CU_MEMORYTYPE_HOST;
        transfer.dstHost = output;
        transfer.dstPitch = s.out_width * 4 * sizeof(float);
        transfer.WidthInBytes = transfer.dstPitch;
        transfer.Height = s.out_height;
        cuda_ok(s.copy(&transfer), "DLSS output readback");
        return 0;
    } catch (const std::exception& error) { last_error = error.what(); return -1; }
}

void popcorn_dlss_destroy(void* handle) {
    std::lock_guard<std::mutex> lock(ownership);
    if (handle) {
        delete static_cast<Session*>(handle);
        occupied = false;
    }
}
}
