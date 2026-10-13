// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// Generated-frame readback diagnostic, using an operator-provisioned NVIDIA SDK.
#pragma once
#include "vulkan_frames.hpp"
#include "nvsdk_ngx_helpers_dlssg_vk.h"
#include <array>
#include <cstdio>
#include <vector>

namespace popcorn_dlssg {
inline NVSDK_NGX_Resource_VK resource(popcorn_vk::Image& image, bool writable) {
    NVSDK_NGX_Resource_VK result{};
    result.Type = NVSDK_NGX_RESOURCE_VK_TYPE_VK_IMAGEVIEW; result.ReadWrite = writable;
    result.Resource.ImageViewInfo = {image.view, image.handle, {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}, image.format, image.width, image.height};
    return result;
}

inline bool smoke(VkPhysicalDevice physical, VkDevice device, uint32_t family, NVSDK_NGX_Handle* feature, NVSDK_NGX_Parameter* parameters) {
    constexpr uint32_t width = 256, height = 192;
    constexpr std::size_t pixels = width * height, bytes = pixels * 4;
    popcorn_vk::Image color(physical, device, width, height, VK_FORMAT_R8G8B8A8_UNORM);
    popcorn_vk::Image depth(physical, device, width, height, VK_FORMAT_R32_SFLOAT);
    popcorn_vk::Image motion(physical, device, width, height, VK_FORMAT_R32G32_SFLOAT);
    popcorn_vk::Image output(physical, device, width, height, VK_FORMAT_R8G8B8A8_UNORM);
    popcorn_vk::Buffer upload(physical, device, bytes * 4);
    popcorn_vk::Buffer readback(physical, device, bytes);
    popcorn_vk::Buffer disabled(physical, device, 4);
    popcorn_vk::Commands commands(device, family);
    auto color_resource = resource(color, false), depth_resource = resource(depth, false);
    auto motion_resource = resource(motion, false), output_resource = resource(output, true);
    NVSDK_NGX_Resource_VK disable_resource{};
    disable_resource.Type = NVSDK_NGX_RESOURCE_VK_TYPE_VK_BUFFER; disable_resource.ReadWrite = true;
    disable_resource.Resource.BufferInfo = {disabled.handle, 4};
    NVSDK_NGX_VK_DLSSG_Eval_Params inputs{};
    inputs.pBackbuffer = &color_resource; inputs.pHudless = &color_resource;
    inputs.pDepth = &depth_resource; inputs.pMVecs = &motion_resource;
    inputs.pOutputInterpFrame = &output_resource; inputs.pOutputDisableInterpolation = &disable_resource;
    NVSDK_NGX_DLSSG_Opt_Eval_Params settings{};
    for (int index = 0; index < 4; ++index) {
        settings.cameraViewToClip[index][index] = 1.0f;
        settings.clipToCameraView[index][index] = 1.0f;
        settings.clipToLensClip[index][index] = 1.0f;
        settings.clipToPrevClip[index][index] = 1.0f;
        settings.prevClipToClip[index][index] = 1.0f;
    }
    // Recorded video has a flat image plane, estimated object motion and no
    // engine-provided camera/depth. This is an explicit experimental adaptation.
    settings.mvecScale[0] = settings.mvecScale[1] = 1.0f;
    settings.cameraUp[1] = settings.cameraRight[0] = settings.cameraFwd[2] = 1.0f;
    settings.cameraNear = 0.1f; settings.cameraFar = 1000.0f;
    settings.cameraFOV = 1.04719755f; settings.cameraAspectRatio = static_cast<float>(width) / height;
    settings.orthoProjection = true; settings.motionVectorsInvalidValue = -100000.0f;
    settings.mvecsSubrectSize = settings.depthSubrectSize = settings.hudLessSubrectSize = {width, height};
    settings.backbufferSubrectSize = settings.outputInterpSubrectSize = {width, height};
    settings.multiFrameCount = 1; settings.multiFrameIndex = 1;
    std::vector<unsigned char> previous(bytes), current(bytes), sentinel(bytes, 0xa5);
    auto* host = static_cast<unsigned char*>(upload.mapped);
    bool verified = true;
    bool object_open = false;
    int completed = 0;
    std::printf(",\"frame_evaluations\":["); std::fflush(stdout);
    try {
    for (int frame = 0; frame < 3; ++frame) {
        for (uint32_t y = 0; y < height; ++y) for (uint32_t x = 0; x < width; ++x) {
            auto pixel = static_cast<std::size_t>(y * width + x) * 4;
            uint32_t shifted = (x + width - frame * 4) % width;
            current[pixel] = static_cast<unsigned char>((shifted * 7 + y * 3) % 256);
            current[pixel + 1] = static_cast<unsigned char>((shifted * 3 + y * 11) % 256);
            current[pixel + 2] = static_cast<unsigned char>((shifted * 13 + y * 5) % 256);
            current[pixel + 3] = 255;
        }
        std::memcpy(host, current.data(), bytes);
        auto* depths = reinterpret_cast<float*>(host + bytes);
        auto* vectors = reinterpret_cast<float*>(host + bytes * 2);
        for (std::size_t pixel = 0; pixel < pixels; ++pixel) {
            depths[pixel] = 0.5f; vectors[pixel * 2] = frame ? -4.0f : 0.0f; vectors[pixel * 2 + 1] = 0.0f;
        }
        // The output image is seeded on the GPU, not just in a host buffer.
        std::memcpy(readback.mapped, sentinel.data(), bytes);
        std::memset(disabled.mapped, 0xff, 4);
        commands.begin();
        commands.buffer_barrier(upload, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        commands.buffer_barrier(readback, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        commands.buffer_barrier(disabled, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_SHADER_WRITE_BIT);
        commands.upload(color, upload, 0); commands.upload(depth, upload, bytes);
        commands.upload(motion, upload, bytes * 2); commands.upload(output, readback);
        settings.reset = frame == 0;
        auto result = NGX_VK_EVALUATE_DLSSG(commands.handle, feature, parameters, &inputs, &settings);
        std::printf("%s{\"frame\":%d,\"reset\":%s,\"evaluate_result\":\"0x%08x\"", frame ? "," : "", frame, settings.reset ? "true" : "false", static_cast<unsigned int>(result));
        object_open = true;
        if (result != NVSDK_NGX_Result_Success) {
            std::printf(",\"pixels_checked\":false}"); object_open = false; ++completed; verified = false; break;
        }
        commands.download(output, readback);
        commands.buffer_barrier(disabled, VK_ACCESS_SHADER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
        commands.finish();
        auto* returned = static_cast<unsigned char*>(readback.mapped);
        std::size_t written = 0, different_current = 0, different_previous = 0;
        for (std::size_t pixel = 0; pixel < pixels; ++pixel) {
            written += std::memcmp(returned + pixel * 4, sentinel.data() + pixel * 4, 4) != 0;
            different_current += std::memcmp(returned + pixel * 4, current.data() + pixel * 4, 3) != 0;
            different_previous += std::memcmp(returned + pixel * 4, previous.data() + pixel * 4, 3) != 0;
        }
        unsigned int flag = *static_cast<unsigned char*>(disabled.mapped);
        std::printf(",\"pixels_checked\":true,\"pixels_written\":%zu,\"pixels_total\":%zu,\"different_from_current\":%zu,\"different_from_previous\":%zu,\"disable_interpolation\":%u}", written, pixels, different_current, different_previous, flag);
        object_open = false; ++completed;
        if (written != pixels || (frame && (flag != 0 || different_current == 0 || different_previous == 0))) verified = false;
        previous = current;
        std::fflush(stdout);
    }
    } catch (const std::exception& error) {
        if (object_open) std::printf(",\"error\":\"%s\"}", error.what());
        else std::printf("%s{\"error\":\"%s\"}", completed ? "," : "", error.what());
        verified = false;
    }
    std::printf("]");
    return verified;
}
}
