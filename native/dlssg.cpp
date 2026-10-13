// SPDX-License-Identifier: MIT
// Copyright (c) 2026 thekozugroup
// Native SDR video Frame Generation. NVIDIA headers/runtime are operator supplied.
#include <vulkan/vulkan.h>
#include "nvsdk_ngx_helpers_dlssg_vk.h"
#include "vulkan_frames.hpp"
#include <algorithm>
#include <cmath>
#include <cwchar>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {
std::mutex api_lock;
bool initialized_once = false;
thread_local std::string error;
void quiet(const char*, NVSDK_NGX_Logging_Level, NVSDK_NGX_Feature) {}
void ngx_check(NVSDK_NGX_Result result, const char* operation) {
    if (result != NVSDK_NGX_Result_Success) throw std::runtime_error(std::string(operation) + ": NGX result " + std::to_string(static_cast<unsigned int>(result)));
}
std::wstring wide(const char* text) {
    if (!text || !*text) throw std::runtime_error("NVIDIA runtime and scratch paths are required");
    std::mbstate_t state{}; const char* input = text;
    auto length = std::mbsrtowcs(nullptr, &input, 0, &state);
    if (length == static_cast<std::size_t>(-1)) throw std::runtime_error("Invalid UTF-8 path");
    std::wstring value(length + 1, L'\0'); input = text; state = {};
    std::mbsrtowcs(value.data(), &input, value.size(), &state);
    return value;
}

struct Frames {
    uint32_t width, height;
    std::size_t pixels, bytes;
    popcorn_vk::Image color, depth, motion, output;
    popcorn_vk::Buffer upload, readback, disabled;
    popcorn_vk::Commands commands;
    NVSDK_NGX_Resource_VK color_resource{}, depth_resource{}, motion_resource{}, output_resource{}, disabled_resource{};
    NVSDK_NGX_VK_DLSSG_Eval_Params inputs{};
    NVSDK_NGX_DLSSG_Opt_Eval_Params settings{};
    Frames(VkPhysicalDevice physical, VkDevice device, uint32_t family, uint32_t w, uint32_t h, uint32_t count)
        : width(w), height(h), pixels(static_cast<std::size_t>(w) * h), bytes(pixels * 4),
          color(physical, device, w, h, VK_FORMAT_R8G8B8A8_UNORM), depth(physical, device, w, h, VK_FORMAT_R32_SFLOAT),
          motion(physical, device, w, h, VK_FORMAT_R32G32_SFLOAT), output(physical, device, w, h, VK_FORMAT_R8G8B8A8_UNORM),
          upload(physical, device, bytes * 4), readback(physical, device, bytes), disabled(physical, device, 4), commands(device, family) {
        auto describe = [](popcorn_vk::Image& image, bool writable) {
            NVSDK_NGX_Resource_VK resource{};
            resource.Type = NVSDK_NGX_RESOURCE_VK_TYPE_VK_IMAGEVIEW; resource.ReadWrite = writable;
            resource.Resource.ImageViewInfo = {image.view, image.handle, {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}, image.format, image.width, image.height};
            return resource;
        };
        color_resource = describe(color, false); depth_resource = describe(depth, false);
        motion_resource = describe(motion, false); output_resource = describe(output, true);
        disabled_resource.Type = NVSDK_NGX_RESOURCE_VK_TYPE_VK_BUFFER; disabled_resource.ReadWrite = true;
        disabled_resource.Resource.BufferInfo = {disabled.handle, 4};
        inputs.pBackbuffer = inputs.pHudless = &color_resource; inputs.pDepth = &depth_resource; inputs.pMVecs = &motion_resource;
        inputs.pOutputInterpFrame = &output_resource; inputs.pOutputDisableInterpolation = &disabled_resource;
        for (int index = 0; index < 4; ++index) {
            settings.cameraViewToClip[index][index] = settings.clipToCameraView[index][index] = 1.0f;
            settings.clipToLensClip[index][index] = settings.clipToPrevClip[index][index] = settings.prevClipToClip[index][index] = 1.0f;
        }
        // A recorded frame has no game-engine geometry. Use a flat image plane
        // and estimated backward object motion, with no fabricated camera motion.
        settings.mvecScale[0] = settings.mvecScale[1] = 1.0f;
        settings.cameraUp[1] = settings.cameraRight[0] = settings.cameraFwd[2] = 1.0f;
        settings.cameraNear = 0.1f; settings.cameraFar = 1000.0f; settings.cameraFOV = 1.04719755f;
        settings.cameraAspectRatio = static_cast<float>(width) / height; settings.orthoProjection = true;
        settings.motionVectorsInvalidValue = -100000.0f;
        settings.mvecsSubrectSize = settings.depthSubrectSize = settings.hudLessSubrectSize = {width, height};
        settings.backbufferSubrectSize = settings.outputInterpSubrectSize = {width, height};
        settings.multiFrameCount = count;
        auto* depths = reinterpret_cast<float*>(static_cast<unsigned char*>(upload.mapped) + bytes);
        std::fill(depths, depths + pixels, 0.5f);
    }
    unsigned char process(NVSDK_NGX_Handle* feature, NVSDK_NGX_Parameter* parameters, const unsigned char* rgba,
                          const float* vectors, unsigned char* returned, bool reset, uint32_t index) {
        for (std::size_t value = 0; value < pixels * 2; ++value) if (!std::isfinite(vectors[value])) throw std::runtime_error("Invalid motion-vector pixels");
        auto* host = static_cast<unsigned char*>(upload.mapped);
        std::memcpy(host, rgba, bytes); std::memcpy(host + bytes * 2, vectors, pixels * 8);
        std::memset(readback.mapped, 0xa5, bytes);
        // The SDK's disable decision applies to the frame pair. MFG can write it
        // only on the first intermediate; retain that value for later indices.
        if (index == 1) std::memset(disabled.mapped, 0xff, 4);
        commands.begin();
        commands.buffer_barrier(upload, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        commands.buffer_barrier(readback, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
        commands.buffer_barrier(disabled, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_SHADER_WRITE_BIT);
        commands.upload(color, upload); commands.upload(depth, upload, bytes);
        commands.upload(motion, upload, bytes * 2); commands.upload(output, readback);
        settings.reset = reset; settings.multiFrameIndex = index;
        ngx_check(NGX_VK_EVALUATE_DLSSG(commands.handle, feature, parameters, &inputs, &settings), "DLSSG evaluation failed");
        commands.download(output, readback);
        commands.buffer_barrier(disabled, VK_ACCESS_SHADER_WRITE_BIT, VK_ACCESS_HOST_READ_BIT);
        commands.finish();
        auto flag = *static_cast<unsigned char*>(disabled.mapped);
        if (flag > 1) throw std::runtime_error("NVIDIA did not write a valid interpolation flag");
        // This catches an entirely untouched output; full-image correctness is
        // established by separate pixel/quality checks, not this coarse sentinel.
        auto* pixels_out = static_cast<unsigned char*>(readback.mapped);
        if (std::all_of(pixels_out, pixels_out + bytes, [](unsigned char byte) { return byte == 0xa5; })) throw std::runtime_error("NVIDIA did not write frame pixels");
        std::memcpy(returned, pixels_out, bytes);
        return flag;
    }
};

struct DLSSG {
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    NVSDK_NGX_Parameter* parameters = nullptr;
    NVSDK_NGX_Handle* feature = nullptr;
    std::unique_ptr<Frames> frames;
    bool initialized = false;
    uint32_t count = 1, maximum = 1, next_index = 1;
    ~DLSSG() {
        if (device) vkDeviceWaitIdle(device);
        if (feature) NVSDK_NGX_VULKAN_ReleaseFeature(feature);
        frames.reset();
        if (parameters) NVSDK_NGX_VULKAN_DestroyParameters(parameters);
        if (initialized) NVSDK_NGX_VULKAN_Shutdown1(device);
        if (device) vkDestroyDevice(device, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
    }
    void initialize(uint32_t width, uint32_t height, uint32_t generated, const char* runtime, const char* scratch) {
        using popcorn_vk::check;
        if (initialized_once) throw std::runtime_error("Use one NGX session per process lifetime");
        if (width < 16 || height < 16 || width > 16384 || height > 16384 || !generated) throw std::runtime_error("Invalid Frame Generation dimensions/count");
        auto library = wide(runtime), data = wide(scratch); const wchar_t* path = library.c_str();
        NVSDK_NGX_FeatureCommonInfo common{}; common.PathListInfo = {&path, 1};
        common.LoggingInfo = {quiet, NVSDK_NGX_LOGGING_LEVEL_OFF, true};
        constexpr const char* project = "fb597f3f-5797-44d5-a4e6-59b757758233";
        NVSDK_NGX_FeatureDiscoveryInfo discovery{};
        discovery.SDKVersion = NVSDK_NGX_Version_API; discovery.FeatureID = NVSDK_NGX_Feature_FrameGeneration;
        discovery.Identifier.IdentifierType = NVSDK_NGX_Application_Identifier_Type_Project_Id;
        discovery.Identifier.v.ProjectDesc = {project, NVSDK_NGX_ENGINE_TYPE_CUSTOM, "PopcornSR"};
        discovery.ApplicationDataPath = data.c_str(); discovery.FeatureInfo = &common;
        uint32_t needed_count = 0, available_count = 0; VkExtensionProperties* needed = nullptr;
        ngx_check(NVSDK_NGX_VULKAN_GetFeatureInstanceExtensionRequirements(&discovery, &needed_count, &needed), "NGX instance discovery failed");
        check(vkEnumerateInstanceExtensionProperties(nullptr, &available_count, nullptr), "Vulkan instance extension count failed");
        std::vector<VkExtensionProperties> available(available_count);
        check(vkEnumerateInstanceExtensionProperties(nullptr, &available_count, available.data()), "Vulkan instance extensions failed");
        auto required_names = [](const std::vector<VkExtensionProperties>& found, uint32_t length, VkExtensionProperties* required) {
            std::vector<const char*> names;
            for (uint32_t index = 0; index < length; ++index) {
                const char* name = required[index].extensionName;
                if (std::none_of(found.begin(), found.end(), [name](const auto& entry) { return std::string(entry.extensionName) == name; })) throw std::runtime_error(std::string("Required Vulkan extension missing: ") + name);
                names.push_back(name);
            }
            return names;
        };
        auto names = required_names(available, needed_count, needed);
        VkApplicationInfo application{}; application.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
        application.pApplicationName = "Popcorn SR video"; application.apiVersion = VK_API_VERSION_1_3;
        VkInstanceCreateInfo instance_info{}; instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
        instance_info.pApplicationInfo = &application; instance_info.enabledExtensionCount = names.size(); instance_info.ppEnabledExtensionNames = names.data();
        check(vkCreateInstance(&instance_info, nullptr, &instance), "Vulkan instance creation failed");
        check(vkEnumeratePhysicalDevices(instance, &available_count, nullptr), "Vulkan device count failed");
        std::vector<VkPhysicalDevice> devices(available_count);
        check(vkEnumeratePhysicalDevices(instance, &available_count, devices.data()), "Vulkan devices failed");
        VkPhysicalDeviceProperties properties{};
        for (auto candidate : devices) {
            vkGetPhysicalDeviceProperties(candidate, &properties);
            if (properties.vendorID == 0x10de) { physical = candidate; break; }
        }
        if (!physical || properties.apiVersion < VK_API_VERSION_1_3) throw std::runtime_error("NVIDIA Vulkan 1.3 device required");
        NVSDK_NGX_FeatureRequirement requirement{};
        ngx_check(NVSDK_NGX_VULKAN_GetFeatureRequirements(instance, physical, &discovery, &requirement), "Frame Generation requirement check failed");
        if (requirement.FeatureSupported != NVSDK_NGX_FeatureSupportResult_Supported) throw std::runtime_error("Frame Generation unsupported on this device/runtime");
        ngx_check(NVSDK_NGX_VULKAN_GetFeatureDeviceExtensionRequirements(instance, physical, &discovery, &needed_count, &needed), "NGX device discovery failed");
        check(vkEnumerateDeviceExtensionProperties(physical, nullptr, &available_count, nullptr), "Vulkan device extension count failed");
        available.resize(available_count);
        check(vkEnumerateDeviceExtensionProperties(physical, nullptr, &available_count, available.data()), "Vulkan device extensions failed");
        names = required_names(available, needed_count, needed);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &available_count, nullptr);
        std::vector<VkQueueFamilyProperties> queues(available_count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &available_count, queues.data());
        uint32_t family = available_count;
        for (uint32_t index = 0; index < available_count; ++index) if ((queues[index].queueFlags & (VK_QUEUE_COMPUTE_BIT | VK_QUEUE_GRAPHICS_BIT)) == (VK_QUEUE_COMPUTE_BIT | VK_QUEUE_GRAPHICS_BIT)) { family = index; break; }
        if (family == available_count) throw std::runtime_error("Vulkan graphics/compute queue required");
        VkPhysicalDeviceVulkan11Features f11{}; f11.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES;
        VkPhysicalDeviceVulkan12Features f12{}; f12.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES;
        VkPhysicalDeviceVulkan13Features f13{}; f13.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES;
        VkPhysicalDeviceOpticalFlowFeaturesNV optical{}; optical.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_OPTICAL_FLOW_FEATURES_NV;
        f11.pNext = &f12; f12.pNext = &f13;
        if (std::any_of(names.begin(), names.end(), [](const char* name) { return std::string(name) == VK_NV_OPTICAL_FLOW_EXTENSION_NAME; })) f13.pNext = &optical;
        VkPhysicalDeviceFeatures2 capabilities{}; capabilities.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2; capabilities.pNext = &f11;
        vkGetPhysicalDeviceFeatures2(physical, &capabilities);
        float priority = 1.0f;
        VkDeviceQueueCreateInfo queue{}; queue.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue.queueFamilyIndex = family; queue.queueCount = 1; queue.pQueuePriorities = &priority;
        VkDeviceCreateInfo device_info{}; device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.pNext = &capabilities; device_info.queueCreateInfoCount = 1; device_info.pQueueCreateInfos = &queue;
        device_info.enabledExtensionCount = names.size(); device_info.ppEnabledExtensionNames = names.data();
        check(vkCreateDevice(physical, &device_info, nullptr, &device), "Vulkan device creation failed");
        ngx_check(NVSDK_NGX_VULKAN_Init_with_ProjectID(project, NVSDK_NGX_ENGINE_TYPE_CUSTOM, "PopcornSR", data.c_str(), instance, physical, device, vkGetInstanceProcAddr, vkGetDeviceProcAddr, &common), "NGX Vulkan initialization failed");
        initialized = initialized_once = true;
        ngx_check(NVSDK_NGX_VULKAN_GetCapabilityParameters(&parameters), "NGX capabilities failed");
        int supported = 0;
        ngx_check(parameters->Get(NVSDK_NGX_Parameter_FrameGeneration_Available, &supported), "Frame Generation availability missing");
        if (!supported) throw std::runtime_error("Frame Generation unavailable");
        unsigned int reported_max = 0;
        if (parameters->Get(NVSDK_NGX_DLSSG_Parameter_MultiFrameCountMax, &reported_max) == NVSDK_NGX_Result_Success && reported_max > 0) maximum = reported_max;
        if (generated > maximum) throw std::runtime_error("Requested native multiplier exceeds verified device limit");
        count = generated;
        frames = std::make_unique<Frames>(physical, device, family, width, height, count);
        frames->commands.begin();
        NVSDK_NGX_DLSSG_Create_Params creation{};
        creation.Width = creation.RenderWidth = width; creation.Height = creation.RenderHeight = height;
        creation.NativeBackbufferFormat = VK_FORMAT_R8G8B8A8_UNORM;
        ngx_check(NGX_VK_CREATE_DLSSG(frames->commands.handle, 1, 1, &feature, parameters, &creation), "Frame Generation creation failed");
        frames->commands.finish();
    }
};
}

#define POPCORN_API extern "C" __attribute__((visibility("default")))
POPCORN_API int popcorn_dlssg_abi_version() { return 1; }
POPCORN_API const char* popcorn_dlssg_error() { return error.c_str(); }
POPCORN_API void* popcorn_dlssg_create(uint32_t width, uint32_t height, uint32_t count, const char* runtime, const char* scratch) {
    std::lock_guard<std::mutex> guard(api_lock); error.clear();
    try {
        auto processor = std::make_unique<DLSSG>(); processor->initialize(width, height, count, runtime, scratch);
        return processor.release();
    } catch (const std::exception& failure) { error = failure.what(); return nullptr; }
}
POPCORN_API unsigned int popcorn_dlssg_max_frames(void* handle) { return handle ? static_cast<DLSSG*>(handle)->maximum : 0; }
POPCORN_API int popcorn_dlssg_process(void* handle, const unsigned char* rgba, const float* motion, unsigned char* output, int reset, unsigned int index, unsigned char* disabled) {
    std::lock_guard<std::mutex> guard(api_lock); error.clear();
    try {
        if (!handle || !rgba || !motion || !output || !disabled) throw std::runtime_error("Frame Generation buffers required");
        auto& processor = *static_cast<DLSSG*>(handle);
        if (index != processor.next_index) throw std::runtime_error("Native intermediate frames must be evaluated in order");
        *disabled = processor.frames->process(processor.feature, processor.parameters, rgba, motion, output, reset != 0, index);
        processor.next_index = index == processor.count ? 1 : index + 1;
        return 0;
    } catch (const std::exception& failure) { error = failure.what(); return -1; }
}
POPCORN_API void popcorn_dlssg_destroy(void* handle) { std::lock_guard<std::mutex> guard(api_lock); delete static_cast<DLSSG*>(handle); }
