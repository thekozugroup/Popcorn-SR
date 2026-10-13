// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// A single synthetic frame establishes SDK execution only, not video quality.
#include <cuda.h>
#include <cmath>
#include <vector>
#include <stdexcept>

static void render_smoke(void* cuda, void* ngx, NVSDK_NGX_Handle* handle, NVSDK_NGX_Parameter* params) {
    auto array_create = function<CUresult (*)(CUarray*, const CUDA_ARRAY3D_DESCRIPTOR*)>(cuda, "cuArray3DCreate_v2");
    auto array_destroy = function<CUresult (*)(CUarray)>(cuda, "cuArrayDestroy");
    auto tex_create = function<CUresult (*)(CUtexObject*, const CUDA_RESOURCE_DESC*, const CUDA_TEXTURE_DESC*, const CUDA_RESOURCE_VIEW_DESC*)>(cuda, "cuTexObjectCreate");
    auto tex_destroy = function<CUresult (*)(CUtexObject)>(cuda, "cuTexObjectDestroy");
    auto copy = function<CUresult (*)(const CUDA_MEMCPY2D*)>(cuda, "cuMemcpy2D_v2");
    auto sync = function<CUresult (*)()>(cuda, "cuCtxSynchronize");
    auto evaluate = function<NVSDK_NGX_Result (*)(const NVSDK_NGX_Handle*, const NVSDK_NGX_Parameter*, void*)>(ngx, "NVSDK_NGX_CUDA_EvaluateFeature");
    auto surface_create = function<CUresult (*)(CUsurfObject*, const CUDA_RESOURCE_DESC*)>(cuda, "cuSurfObjectCreate");
    auto surface_destroy = function<CUresult (*)(CUsurfObject)>(cuda, "cuSurfObjectDestroy");
    if (!array_create || !array_destroy || !tex_create || !tex_destroy || !copy || !sync || !evaluate || !surface_create || !surface_destroy) {
        std::printf(",\"render_error\":\"Required CUDA entrypoint unavailable\"");
        return;
    }
    CUarray arrays[4]{};
    CUtexObject textures[4]{};
    CUsurfObject output_surface{};
    int widths[4] = {128, 256, 128, 128};
    int heights[4] = {96, 192, 96, 96};
    int channels[4] = {4, 4, 1, 2};
    std::vector<float> storage[4];
    try {
        for (int i = 0; i < 4; ++i) {
            CUDA_ARRAY3D_DESCRIPTOR description{};
            description.Width = widths[i];
            description.Height = heights[i];
            description.Format = CU_AD_FORMAT_FLOAT;
            description.NumChannels = channels[i];
            description.Flags = CUDA_ARRAY3D_SURFACE_LDST;
            if (array_create(&arrays[i], &description) != CUDA_SUCCESS) throw std::runtime_error("Array allocation failed");
            CUDA_RESOURCE_DESC resource{};
            resource.resType = CU_RESOURCE_TYPE_ARRAY;
            resource.res.array.hArray = arrays[i];
            if (i == 1 && surface_create) { if (surface_create(&output_surface, &resource) != CUDA_SUCCESS) throw std::runtime_error("Surface allocation failed"); }
            CUDA_TEXTURE_DESC texture{};
            texture.addressMode[0] = CU_TR_ADDRESS_MODE_CLAMP;
            texture.addressMode[1] = CU_TR_ADDRESS_MODE_CLAMP;
            texture.filterMode = CU_TR_FILTER_MODE_POINT;
            if (tex_create(&textures[i], &resource, &texture, nullptr) != CUDA_SUCCESS) throw std::runtime_error("Texture allocation failed");
            storage[i].resize(widths[i] * heights[i] * channels[i]);
            for (int y = 0; y < heights[i]; ++y) for (int x = 0; x < widths[i]; ++x) for (int c = 0; c < channels[i]; ++c) {
                float value = i == 0 ? (c == 0 ? static_cast<float>(x) / widths[i] : c == 1 ? static_cast<float>(y) / heights[i] : c == 2 ? 0.2f : 1.0f) : i == 1 ? std::nanf("") : i == 2 ? 0.5f : 0.0f;
                storage[i][(y * widths[i] + x) * channels[i] + c] = value;
            }
            CUDA_MEMCPY2D transfer{};
            transfer.srcMemoryType = CU_MEMORYTYPE_HOST;
            transfer.srcHost = storage[i].data();
            transfer.srcPitch = widths[i] * channels[i] * sizeof(float);
            transfer.dstMemoryType = CU_MEMORYTYPE_ARRAY;
            transfer.dstArray = arrays[i];
            transfer.WidthInBytes = transfer.srcPitch;
            transfer.Height = heights[i];
            if (copy(&transfer) != CUDA_SUCCESS) throw std::runtime_error("Upload failed");
        }
        params->Set(NVSDK_NGX_Parameter_Color, static_cast<void*>(&textures[0]));
        params->Set(NVSDK_NGX_Parameter_Output, static_cast<void*>(&output_surface));
        params->Set(NVSDK_NGX_Parameter_Depth, static_cast<void*>(&textures[2]));
        params->Set(NVSDK_NGX_Parameter_MotionVectors, static_cast<void*>(&textures[3]));
        params->Set(NVSDK_NGX_Parameter_Reset, 1);
        params->Set(NVSDK_NGX_Parameter_Jitter_Offset_X, 0.0f);
        params->Set(NVSDK_NGX_Parameter_Jitter_Offset_Y, 0.0f);
        params->Set(NVSDK_NGX_Parameter_MV_Scale_X, 1.0f);
        params->Set(NVSDK_NGX_Parameter_MV_Scale_Y, 1.0f);
        params->Set(NVSDK_NGX_Parameter_DLSS_Render_Subrect_Dimensions_Width, 128u);
        params->Set(NVSDK_NGX_Parameter_DLSS_Render_Subrect_Dimensions_Height, 96u);
        params->Set(NVSDK_NGX_Parameter_DLSS_Pre_Exposure, 1.0f);
        params->Set(NVSDK_NGX_Parameter_DLSS_Exposure_Scale, 1.0f);
        NVSDK_NGX_Result result = evaluate(handle, params, nullptr);
        int synchronized = sync();
        std::printf(",\"sr_evaluate_result\":\"0x%08x\",\"cuda_sync_result\":%d", static_cast<unsigned int>(result), synchronized);
        if (result == NVSDK_NGX_Result_Success && synchronized == CUDA_SUCCESS) {
            CUDA_MEMCPY2D download{};
            download.srcMemoryType = CU_MEMORYTYPE_ARRAY;
            download.srcArray = arrays[1];
            download.dstMemoryType = CU_MEMORYTYPE_HOST;
            download.dstHost = storage[1].data();
            download.dstPitch = widths[1] * channels[1] * sizeof(float);
            download.WidthInBytes = download.dstPitch;
            download.Height = heights[1];
            int copied = copy(&download);
            std::size_t finite = 0;
            double sum = 0;
            for (float value : storage[1]) if (std::isfinite(value)) { ++finite; sum += value; }
            std::printf(",\"readback_result\":%d,\"finite_values\":%zu,\"expected_values\":%zu,\"output_sum\":%.6f,\"pixel_render_verified\":%s", copied, finite, storage[1].size(), sum, copied == CUDA_SUCCESS && finite == storage[1].size() && sum > 0 ? "true" : "false");
        }
    } catch (const std::exception& error) {
        std::printf(",\"render_error\":\"%s\"", error.what());
    }
    if (output_surface) surface_destroy(output_surface);
    for (int i = 0; i < 4; ++i) {
        if (textures[i]) tex_destroy(textures[i]);
        if (arrays[i]) array_destroy(arrays[i]);
    }
}
